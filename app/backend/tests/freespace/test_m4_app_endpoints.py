"""M4: app endpoints ``GET /v1/sites`` and ``GET /v1/sites/{siteId}/availability``
(BF-30 - BF-32, BF-36, BN-2, AT-01, AT-07, AT-08)."""

from __future__ import annotations

from datetime import timedelta
import json
import re

import pytest
from sqlalchemy import func, select

from src.constants.freespace import Health
from src.core.config import settings
from src.models.site_engine_state import SiteEngineState
from src.models.site_event import SiteEvent
from src.services.freespace import availability_cache as cache_mod
from src.services.freespace.availability_cache import cache_key
from tests.freespace.conftest import FIXED_START, make_site, make_zone


AVAILABILITY = "/v1/sites/absa-alice-lane/availability"
Z_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")


def _at07_zones() -> dict:
    return {
        "b1": {"capacity": 500, "occupied": 490},  # 98 % -> FULL
        "b2": {"capacity": 100, "occupied": 85},  # 85 % -> LIMITED, 15 free
        "b3": {"capacity": 100, "occupied": 50, "health": Health.OFFLINE},
        "b4": {"capacity": 400, "occupied": 220},  # 55 % -> AVAILABLE, 180 free
    }


# ─────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/v1/sites", AVAILABILITY])
async def test_missing_app_key_is_401(client, fs_site, path):
    response = await client.get(path)
    assert response.status_code == 401
    assert "app_key.invalid" in response.text


@pytest.mark.parametrize("path", ["/v1/sites", AVAILABILITY])
async def test_wrong_app_key_is_401(client, fs_site, fs_app_key, path):
    response = await client.get(path, headers={"X-Freespace-App-Key": "fsa_nope"})
    assert response.status_code == 401
    assert "app_key.invalid" in response.text


async def test_revoked_app_key_is_401(client, async_session, fs_site, fs_app_key):
    plaintext, row = fs_app_key
    row.revoked_at = FIXED_START
    await async_session.commit()
    response = await client.get("/v1/sites", headers={"X-Freespace-App-Key": plaintext})
    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# GET /v1/sites (BF-30)
# ─────────────────────────────────────────────────────────────


async def test_site_list_only_listed_live_sites_ordered_by_name(
    client, async_session, test_organization, second_organization, fs_app_headers
):
    await make_site(async_session, test_organization, slug="zeta", name="Zeta Park")
    await make_site(
        async_session,
        second_organization,
        slug="alpha",
        name="Alpha Park",
        managed=False,
        time_zone="Europe/London",
    )
    await make_site(
        async_session, test_organization, slug="hidden", name="Hidden", listed=False
    )
    gone = await make_site(async_session, test_organization, slug="gone", name="Gone")
    gone.deleted_time = FIXED_START
    await async_session.commit()

    response = await client.get("/v1/sites", headers=fs_app_headers)
    assert response.status_code == 200
    assert response.json() == {
        "sites": [
            {
                "id": "alpha",
                "name": "Alpha Park",
                "topic": "freespace-alpha",
                "managed": False,
                "timeZone": "Europe/London",
            },
            {
                "id": "zeta",
                "name": "Zeta Park",
                "topic": "freespace-zeta",
                "managed": True,
                "timeZone": "Africa/Johannesburg",
            },
        ]
    }


async def test_site_list_empty(client, fs_app_headers):
    response = await client.get("/v1/sites", headers=fs_app_headers)
    assert response.status_code == 200
    assert response.json() == {"sites": []}


# ─────────────────────────────────────────────────────────────
# GET /v1/sites/{siteId}/availability (BF-31)
# ─────────────────────────────────────────────────────────────


async def test_availability_full_shape(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, fixed_clock
):
    await fs_snapshot(
        fs_site,
        capacity=1100,
        occupied=935,  # 85 %
        received_at=FIXED_START - timedelta(seconds=14),
        zones=_at07_zones(),
    )
    response = await client.get(AVAILABILITY, headers=fs_app_headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "max-age=5"
    body = response.json()
    assert set(body) == {
        "siteId",
        "asOf",
        "ageSeconds",
        "stale",
        "site",
        "recommendedZoneId",
        "zones",
    }
    assert body["siteId"] == "absa-alice-lane"
    assert body["asOf"] == "2026-11-24T05:44:46Z"
    assert body["ageSeconds"] == 14
    assert body["stale"] is False
    assert body["site"] == {
        "capacity": 1100,
        "occupied": 935,
        "occupancyPct": 85,
        "freeUsable": 165,
    }
    assert body["recommendedZoneId"] == "b4"  # AT-07
    zones = body["zones"]
    assert [z["id"] for z in zones] == ["b1", "b2", "b3", "b4"]
    assert zones[0] == {
        "id": "b1",
        "name": "Basement 1",
        "capacity": 500,
        "free": 10,
        "occupancyPct": 98,
        "status": "FULL",
        "asOf": "2026-11-24T05:44:46Z",
    }
    assert [z["status"] for z in zones] == ["FULL", "LIMITED", "UNKNOWN", "AVAILABLE"]
    for z in zones:
        assert Z_TIME.match(z["asOf"])
    assert Z_TIME.match(body["asOf"])


async def test_availability_floor_89_9_shows_89(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers
):
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=899,
        zones={"b1": {"capacity": 1000, "occupied": 899}},
    )
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["site"]["occupancyPct"] == 89
    assert body["zones"][0]["occupancyPct"] == 89
    assert body["zones"][0]["status"] == "LIMITED"


async def test_availability_at01_site_at_75(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers
):
    await fs_snapshot(
        fs_site,
        capacity=1200,
        occupied=900,
        zones={"b1": {"capacity": 300, "occupied": 225}},
    )
    response = await client.get(AVAILABILITY, headers=fs_app_headers)
    body = response.json()
    assert response.status_code == 200
    assert body["site"]["occupancyPct"] == 75
    assert body["stale"] is False
    assert body["recommendedZoneId"] == "b1"


async def test_never_received_site(client, fs_site, fs_zones, fs_app_headers):
    response = await client.get(AVAILABILITY, headers=fs_app_headers)
    assert response.status_code == 200
    assert response.json() == {
        "siteId": "absa-alice-lane",
        "asOf": None,
        "ageSeconds": None,
        "stale": True,
        "site": None,
        "recommendedZoneId": None,
        "zones": [],
    }


async def test_unknown_site_is_404(client, fs_site, fs_app_headers):
    response = await client.get("/v1/sites/nope/availability", headers=fs_app_headers)
    assert response.status_code == 404
    assert "site.not_found" in response.text


async def test_unlisted_site_is_404(
    client, async_session, test_organization, fs_app_headers
):
    await make_site(async_session, test_organization, slug="hidden", listed=False)
    response = await client.get("/v1/sites/hidden/availability", headers=fs_app_headers)
    assert response.status_code == 404
    assert "site.not_found" in response.text


async def test_deleted_site_is_404(client, async_session, fs_site, fs_app_headers):
    fs_site.deleted_time = FIXED_START
    await async_session.commit()
    response = await client.get(AVAILABILITY, headers=fs_app_headers)
    assert response.status_code == 404


async def test_disabled_and_deleted_zones_hidden_unreported_shown_unknown(
    client, async_session, fs_site, fs_zones, fs_snapshot, fs_app_headers
):
    discovered = await make_zone(
        async_session, fs_site, "b9", display_order=0, enabled=False, discovered=True
    )
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=100,
        zones={
            "b9": {"capacity": 900, "occupied": 0},
            "b1": {"capacity": 100, "occupied": 10},
            "b3": {"capacity": 100, "occupied": 20},
        },
    )
    fs_zones["b3"].deleted_time = FIXED_START
    await async_session.commit()
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert [z["id"] for z in body["zones"]] == ["b1", "b2", "b4"]
    b2 = body["zones"][1]
    assert b2 == {
        "id": "b2",
        "name": "Basement 2",
        "capacity": None,
        "free": None,
        "occupancyPct": None,
        "status": "UNKNOWN",
        "asOf": None,
    }
    assert body["recommendedZoneId"] == "b1"  # never the disabled b9
    assert discovered.slug == "b9"


async def test_display_order_respected(
    client, async_session, fs_site, fs_snapshot, fs_app_headers
):
    await make_zone(async_session, fs_site, "top", display_order=1)
    await make_zone(async_session, fs_site, "b1", display_order=3)
    await make_zone(async_session, fs_site, "a2", display_order=2)
    await make_zone(async_session, fs_site, "a1", display_order=2)
    await fs_snapshot(fs_site, capacity=10, occupied=1)
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert [z["id"] for z in body["zones"]] == ["top", "a1", "a2", "b1"]


async def test_at08_no_ingest_for_three_minutes(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, fixed_clock
):
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=100,
        zones={"b1": {"capacity": 100, "occupied": 10}},
    )
    fixed_clock.advance(180)
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["stale"] is True
    assert body["ageSeconds"] == 180
    assert body["recommendedZoneId"] is None
    assert body["zones"][0]["status"] == "UNKNOWN"
    assert body["zones"][0]["capacity"] == 100  # figures kept, status UNKNOWN


async def test_at08_offline_zone_never_recommended_even_if_stored(
    client, async_session, fs_site, fs_zones, fs_snapshot, fs_app_headers
):
    state = (
        await async_session.execute(
            select(SiteEngineState).where(SiteEngineState.site_id == fs_site.id)
        )
    ).scalar_one()
    state.current_zone_slug = "b1"
    await async_session.commit()
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=100,
        zones={
            "b1": {"capacity": 500, "occupied": 0, "health": Health.OFFLINE},
            "b2": {"capacity": 100, "occupied": 50},
        },
    )
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["zones"][0]["status"] == "UNKNOWN"
    assert body["recommendedZoneId"] == "b2"


async def test_stored_recommendation_is_stickiness_input(
    client, async_session, fs_site, fs_zones, fs_snapshot, fs_app_headers
):
    """D9: with b1 stored, b2 with 4 more free bays does not take over (BT-05)."""
    state = (
        await async_session.execute(
            select(SiteEngineState).where(SiteEngineState.site_id == fs_site.id)
        )
    ).scalar_one()
    state.current_zone_slug = "b1"
    await async_session.commit()
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=100,
        zones={
            "b1": {"capacity": 300, "occupied": 200},  # 100 free
            "b2": {"capacity": 300, "occupied": 196},  # 104 free
        },
    )
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["recommendedZoneId"] == "b1"


async def test_read_writes_nothing(
    client,
    async_session,
    fs_site,
    fs_zones,
    fs_snapshot,
    fs_app_headers,
    fake_fcm,
    monkeypatch,
):
    """BF-32: no evaluation, no push, no engine-state write, no event."""
    from src.services.freespace import evaluator

    async def _boom(*args, **kwargs):
        raise AssertionError("availability read must not evaluate")

    monkeypatch.setattr(evaluator, "evaluate_site", _boom)
    monkeypatch.setattr(evaluator, "enqueue_fanouts", _boom)

    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=950,
        zones={"b1": {"capacity": 300, "occupied": 100}},
    )
    state = (
        await async_session.execute(
            select(SiteEngineState).where(SiteEngineState.site_id == fs_site.id)
        )
    ).scalar_one()
    before = {c.name: getattr(state, c.name) for c in SiteEngineState.__table__.columns}
    events_before = (
        await async_session.execute(select(func.count()).select_from(SiteEvent))
    ).scalar_one()

    for _ in range(3):
        response = await client.get(AVAILABILITY, headers=fs_app_headers)
        assert response.status_code == 200
    assert response.json()["recommendedZoneId"] == "b1"

    await async_session.refresh(state)
    after = {c.name: getattr(state, c.name) for c in SiteEngineState.__table__.columns}
    assert after == before
    assert after["current_zone_slug"] is None  # the read did not persist "b1"
    events_after = (
        await async_session.execute(select(func.count()).select_from(SiteEvent))
    ).scalar_one()
    assert events_after == events_before
    assert fake_fcm.sent == []


async def test_site_id_isolation(
    client, fs_site, fs_second_site, fs_zones, fs_snapshot, fs_app_headers
):
    """Each slug answers with its own site only (D2)."""
    await fs_snapshot(fs_site, capacity=1000, occupied=100)
    other = (
        await client.get(
            "/v1/sites/other-customer-site/availability", headers=fs_app_headers
        )
    ).json()
    assert other["siteId"] == "other-customer-site"
    assert other["asOf"] is None and other["zones"] == []


# ─────────────────────────────────────────────────────────────
# Cache (BF-32)
# ─────────────────────────────────────────────────────────────


async def test_cache_serves_within_5s_and_recomputes_after(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, fixed_clock, fs_redis
):
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=100,
        zones={"b1": {"capacity": 100, "occupied": 10}},
    )
    first = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert first["ageSeconds"] == 0
    assert await fs_redis.get(cache_key("absa-alice-lane")) is not None

    # New data within 5 s: the cached body is served.
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=500,
        zones={"b1": {"capacity": 100, "occupied": 10}},
    )
    fixed_clock.advance(4)
    cached = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert cached == first

    # 5 s after it was computed it is no longer served (ageSeconds/stale fresh).
    fixed_clock.advance(1)
    fresh = await client.get(AVAILABILITY, headers=fs_app_headers)
    assert fresh.headers["cache-control"] == "max-age=5"
    body = fresh.json()
    assert body["site"]["occupied"] == 500
    assert body["ageSeconds"] == 5


async def test_cache_ignored_when_clock_moves_back(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, fixed_clock, fs_redis
):
    await fs_snapshot(fs_site, capacity=1000, occupied=100)
    await client.get(AVAILABILITY, headers=fs_app_headers)
    fixed_clock.set(FIXED_START - timedelta(seconds=1))
    await fs_snapshot(
        fs_site,
        capacity=1000,
        occupied=300,
        received_at=FIXED_START - timedelta(seconds=1),
    )
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["site"]["occupied"] == 300


async def test_cache_stale_flag_never_more_than_5s_late(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, fixed_clock
):
    await fs_snapshot(fs_site, capacity=1000, occupied=100)
    fixed_clock.advance(118)
    assert (await client.get(AVAILABILITY, headers=fs_app_headers)).json()[
        "stale"
    ] is False
    fixed_clock.advance(4)  # 122 s: stale, but cached body (computed at 118) served
    assert (await client.get(AVAILABILITY, headers=fs_app_headers)).json()[
        "stale"
    ] is False
    fixed_clock.advance(1)  # cache is 5 s old: recomputed
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    assert body["stale"] is True and body["ageSeconds"] == 123


class _BrokenRedis:
    async def get(self, *args, **kwargs):
        raise ConnectionError("down")

    async def setex(self, *args, **kwargs):
        raise ConnectionError("down")


@pytest.mark.parametrize("redis", [None, _BrokenRedis()])
async def test_cache_fails_open(
    client, fs_site, fs_zones, fs_snapshot, fs_app_headers, monkeypatch, redis
):
    await fs_snapshot(fs_site, capacity=1000, occupied=100)
    monkeypatch.setattr(cache_mod, "get_redis", lambda: redis)
    response = await client.get(AVAILABILITY, headers=fs_app_headers)
    assert response.status_code == 200
    assert response.json()["site"]["occupied"] == 100


async def test_cache_entry_body_is_wire_body(
    client, fs_site, fs_snapshot, fs_app_headers, fs_redis
):
    await fs_snapshot(fs_site, capacity=10, occupied=1)
    body = (await client.get(AVAILABILITY, headers=fs_app_headers)).json()
    entry = json.loads(await fs_redis.get(cache_key("absa-alice-lane")))
    assert entry["body"] == body
    assert entry["computed_at"].startswith("2026-11-24T05:45:00")


# ─────────────────────────────────────────────────────────────
# Rate limits (BF-36)
# ─────────────────────────────────────────────────────────────


def test_rate_limit_settings():
    assert settings.RATE_LIMIT_FREESPACE_AVAILABILITY == "60/minute"
    assert settings.RATE_LIMIT_FREESPACE_SITES == "30/minute"


async def test_sites_rate_limited_per_ip(client, fs_app_headers):
    if not settings.RATE_LIMIT_ENABLED:
        pytest.skip("rate limiting disabled")
    statuses = [
        (await client.get("/v1/sites", headers=fs_app_headers)).status_code
        for _ in range(31)
    ]
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429


async def test_availability_rate_limited_per_ip(client, fs_site, fs_app_headers):
    if not settings.RATE_LIMIT_ENABLED:
        pytest.skip("rate limiting disabled")
    statuses = [
        (await client.get(AVAILABILITY, headers=fs_app_headers)).status_code
        for _ in range(61)
    ]
    assert statuses[:60] == [200] * 60
    assert statuses[60] == 429
