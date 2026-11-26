"""M10 mock / demonstration mode (BF-84, BF-85, BT-10, AT-01 - AT-08 driver)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from sqlalchemy import select

from src.api.freespace_public import mock as mock_module
from src.constants.freespace import EngineState
from src.database import get_async_session
from src.models.site_engine_state import SiteEngineState
from src.models.site_snapshot import SiteSnapshot
from src.services.freespace import evaluator
from src.services.freespace.clock import (
    SystemClock,
    get_clock,
    get_mock_offset_seconds,
    set_clock_override,
)
from tests.freespace.conftest import SITE_SLUG


def _body(occupied: int = 360, measured_at: str | None = None, **extra):
    data = {
        "siteId": SITE_SLUG,
        "site": {
            "capacity": 400,
            "occupied": occupied,
            "freeUsable": 400 - occupied,
            "freeReserved": 0,
            "freeDisabled": 0,
            "unknown": 0,
            "health": "OK",
        },
        "zones": [],
    }
    if measured_at:
        data["measuredAt"] = measured_at
    data.update(extra)
    return data


@pytest_asyncio.fixture
async def mock_client(monkeypatch, async_session) -> AsyncGenerator[AsyncClient, None]:
    """An app instance built with mock mode ON, real clock + Redis offset."""
    import main

    monkeypatch.setattr(main.settings, "FREESPACE_MOCK_MODE", True)
    monkeypatch.setattr(main.settings, "DEBUG", True)
    app = main.create_application()
    set_clock_override(None)  # use the mock-mode Redis-offset clock

    async def override_session():
        yield async_session

    app.dependency_overrides[get_async_session] = override_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ─────────────────────────────────────────────────────────────
# BT-10: mock mode off
# ─────────────────────────────────────────────────────────────


async def test_mock_off_returns_404_not_403(client):
    for method, path in (
        ("GET", "/mock/status"),
        ("POST", "/mock/clock"),
        ("POST", f"/mock/sites/{SITE_SLUG}/occupancy"),
    ):
        response = await client.request(method, path, json={})
        assert response.status_code == 404, path


# ─────────────────────────────────────────────────────────────
# Mock mode on
# ─────────────────────────────────────────────────────────────


async def test_status_reports_mock_mode_and_time(mock_client):
    response = await mock_client.get("/mock/status")
    assert response.status_code == 200
    data = response.json()
    assert data["mockMode"] is True
    assert data["offsetSeconds"] == 0.0
    assert data["mockTime"].endswith("Z")


async def test_clock_advance_moves_get_clock_and_survives_workers(
    mock_client, fs_redis
):
    before = (await get_clock()).now()
    response = await mock_client.post("/mock/clock", json={"seconds": 300})
    assert response.status_code == 200
    data = response.json()
    assert data["offsetSeconds"] == 300.0
    assert data["tick"]["ran"] in (True, False)

    after = (await get_clock()).now()
    assert after - before >= timedelta(seconds=299)

    # A second "worker": a clock built independently from the same Redis key.
    offset = await get_mock_offset_seconds()
    other = SystemClock(timedelta(seconds=offset))
    assert abs((other.now() - after).total_seconds()) < 5

    # Offsets accumulate.
    response = await mock_client.post("/mock/clock", json={"seconds": 60})
    assert response.json()["offsetSeconds"] == 360.0


async def test_clock_reset(mock_client):
    await mock_client.post("/mock/clock", json={"seconds": 600})
    response = await mock_client.post("/mock/clock", json={"reset": True})
    assert response.status_code == 200
    assert response.json()["offsetSeconds"] == 0.0
    assert await get_mock_offset_seconds() == 0.0
    status_ = (await mock_client.get("/mock/status")).json()
    assert status_["offsetSeconds"] == 0.0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"seconds": -5},
        {"seconds": 10, "reset": True},
        {"seconds": 10**9},
        {"seconds": 5, "bogus": 1},
        {"seconds": "abc"},
    ],
)
async def test_clock_rejects_invalid_requests(mock_client, payload):
    response = await mock_client.post("/mock/clock", json=payload)
    assert response.status_code == 422
    assert await get_mock_offset_seconds() == 0.0


async def test_clock_without_redis_is_503(mock_client, monkeypatch):
    monkeypatch.setattr(mock_module, "get_redis", lambda: None)
    response = await mock_client.post("/mock/clock", json={"seconds": 10})
    assert response.status_code == 503
    assert response.json()["detail_code"] == "mock.redis_unavailable"


async def test_clock_runs_engine_tick_inline(mock_client, monkeypatch):
    calls: list[datetime] = []

    async def fake_tick(session_factory, clock):
        calls.append(clock.now())
        async with session_factory() as session:
            assert session is not None
        return evaluator.TickResult(sites_evaluated=3)

    monkeypatch.setattr(evaluator, "run_engine_tick", fake_tick)
    response = await mock_client.post("/mock/clock", json={"seconds": 120})
    assert len(calls) == 1
    tick = response.json()["tick"]
    assert tick["ran"] is True and tick["sitesEvaluated"] == 3


async def test_clock_tolerates_unimplemented_tick(mock_client, monkeypatch):
    async def not_yet(session_factory, clock):
        raise NotImplementedError("M6")

    monkeypatch.setattr(evaluator, "run_engine_tick", not_yet)
    response = await mock_client.post("/mock/clock", json={"seconds": 1})
    assert response.status_code == 200
    assert response.json()["tick"]["ran"] is False


# ─────────────────────────────────────────────────────────────
# Snapshot injection
# ─────────────────────────────────────────────────────────────


async def test_occupancy_defaults_measured_at_and_stores_snapshot(
    mock_client, async_session, fs_site
):
    response = await mock_client.post(
        f"/mock/sites/{SITE_SLUG}/occupancy", json=_body(occupied=360)
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["accepted"] is True
    assert set(data["site"]) >= {"stale", "state"}

    snapshot = (
        await async_session.execute(
            select(SiteSnapshot)
            .where(SiteSnapshot.site_id == fs_site.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert snapshot.occupied == 360
    assert snapshot.capacity == 400


async def test_occupancy_same_stored_state_as_real_intake(
    mock_client, client, async_session, fs_site, fs_ingest_headers
):
    """The mock path and the real intake produce the same snapshot figures."""
    site_id = fs_site.id
    measured = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    mock_resp = await mock_client.post(
        f"/mock/sites/{SITE_SLUG}/occupancy",
        json=_body(occupied=300, measured_at=measured),
    )
    assert mock_resp.status_code == 200, mock_resp.text
    snap = (
        await async_session.execute(
            select(SiteSnapshot)
            .where(SiteSnapshot.site_id == fs_site.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    mock_figures = (snap.capacity, snap.occupied, snap.free_usable, snap.health)

    # Real intake of the same figures yields the same response shape/figures.
    set_clock_override(SystemClock())
    real_resp = await client.post(
        "/v1/ingest/occupancy",
        json=_body(occupied=300, measured_at=measured),
        headers=fs_ingest_headers,
    )
    assert real_resp.status_code == 200, real_resp.text
    assert set(real_resp.json()) == set(mock_resp.json())
    async_session.expire_all()
    snap2 = (
        await async_session.execute(
            select(SiteSnapshot).where(SiteSnapshot.site_id == site_id)
        )
    ).scalar_one()
    assert (snap2.capacity, snap2.occupied, snap2.free_usable, snap2.health) == (
        mock_figures
    )


async def test_occupancy_unknown_site_404(mock_client):
    response = await mock_client.post(
        "/mock/sites/nope/occupancy", json=_body() | {"siteId": "nope"}
    )
    assert response.status_code == 404


async def test_occupancy_body_site_mismatch_403(mock_client, fs_site, fs_second_site):
    response = await mock_client.post(
        f"/mock/sites/{SITE_SLUG}/occupancy", json=_body() | {"siteId": "other"}
    )
    assert response.status_code == 403
    assert response.json()["detail_code"] == "ingest.site_mismatch"


async def test_occupancy_inconsistent_counts_still_validated(mock_client, fs_site):
    body = _body()
    body["site"]["capacity"] = "x"
    response = await mock_client.post(f"/mock/sites/{SITE_SLUG}/occupancy", json=body)
    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────
# Scenario: 90 % then advance 5 minutes
# ─────────────────────────────────────────────────────────────


async def test_scenario_trigger_then_advance_five_minutes(
    mock_client, async_session, fs_site
):
    response = await mock_client.post(
        f"/mock/sites/{SITE_SLUG}/occupancy", json=_body(occupied=360)
    )
    assert response.status_code == 200
    assert response.json()["site"]["state"] in ("PENDING", "ACTIVE", "IDLE")

    await mock_client.post("/mock/clock", json={"seconds": 300})
    # After the tick the stabilisation timer has run out: the site has left IDLE.
    state = (
        await async_session.execute(
            select(SiteEngineState.state)
            .where(SiteEngineState.site_id == fs_site.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert state != EngineState.IDLE.value
