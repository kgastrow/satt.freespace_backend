"""Foundation: shared interfaces, the evaluator contract, fake FCM, shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Annotated
import uuid

from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from src.api.deps import CurrentUser, require_permission
from src.constants.freespace import (
    PERM_SITE_PUSH_ANNOUNCE,
    PERM_SITES_READ,
    EngineState,
)
from src.database import get_async_session
from src.services.freespace import availability, engine, fanout, fcm, templates
from src.services.freespace.availability import (
    age_seconds,
    meets_pct,
    occupancy_exact_pct,
    occupancy_pct_floor,
    occupancy_ratio,
)
from src.services.freespace.evaluator import enqueue_fanouts, evaluate_site
from src.services.freespace.fcm import (
    FakeFcmClient,
    FcmMessage,
    FcmResultKind,
    FcmSendResult,
    get_fcm_client,
)
from src.services.freespace.loaders import load_snapshot


class TestAvailabilityPrimitives:
    def test_ratio_and_floor(self):
        assert occupancy_ratio(1081, 1200) is not None
        assert occupancy_pct_floor(1081, 1200) == 90
        assert occupancy_pct_floor(1079, 1200) == 89  # 89.9 % shows 89
        assert occupancy_ratio(0, 0) is None and occupancy_pct_floor(5, 0) is None

    def test_meets_pct_is_exact(self):
        assert not meets_pct(899, 1000, 90)  # 89.9 % < 90 %
        assert meets_pct(900, 1000, 90)
        assert meets_pct(1140, 1200, 95.0)
        assert not meets_pct(1, 0, 0)
        assert meets_pct(951, 1000, 90.1 + 5)  # fractional thresholds

    def test_exact_pct_and_age(self, fixed_clock):
        assert occupancy_exact_pct(1140, 1200) == 95.0
        assert age_seconds(None, fixed_clock.now()) is None


def test_shared_interfaces_exist():
    assert callable(availability.top_two) and callable(engine.event_figures)
    assert callable(fanout.run_fanout) and callable(fcm.build_message)
    assert set(templates.ALLOWED_PLACEHOLDERS) == set(templates.DEFAULT_TEMPLATES)
    # M1 filled the default wording: no foundation placeholder text remains.
    for title, body in templates.DEFAULT_TEMPLATES.values():
        assert title.strip() and body.strip()
        assert "TODO" not in title + body


class TestEvaluatorInterface:
    async def test_never_reported_site(self, async_session, fs_site, fixed_clock):
        view = await evaluate_site(async_session, fs_site.id, fixed_clock)
        assert view.state is EngineState.IDLE
        assert view.recommended_zone_slug is None
        assert view.stale is True
        assert view.fanout_event_ids == ()

    async def test_unknown_site(self, async_session, fixed_clock):
        with pytest.raises(LookupError):
            await evaluate_site(async_session, uuid.uuid4(), fixed_clock)

    async def test_enqueue_fanouts(self, monkeypatch):
        from src.services.tasks import task_queue

        calls = []

        async def fake_enqueue(name, *args, **kwargs):
            calls.append((name, args))
            return None  # simulate failure: must not raise

        monkeypatch.setattr(task_queue, "enqueue_job", fake_enqueue)
        ids = [uuid.uuid4(), uuid.uuid4()]
        await enqueue_fanouts(ids)
        assert calls == [("fanout_advisory_task", (str(i),)) for i in ids]


class TestFakeFcm:
    def test_message_target_validation(self):
        with pytest.raises(ValueError):
            FcmMessage(payload={})
        with pytest.raises(ValueError):
            FcmMessage(payload={}, token="t", topic="x")
        body = FcmMessage(payload={"data": {"a": "1"}}, topic="site").to_request_body()
        assert body == {"message": {"data": {"a": "1"}, "topic": "site"}}

    async def test_default_accepts_and_records(self):
        client = FakeFcmClient()
        result = await client.send(FcmMessage(payload={}, token="tok"))
        assert result.kind is FcmResultKind.ACCEPTED and result.message_id
        assert client.sent_tokens == ["tok"]

    async def test_scripted_results(self):
        bad = FcmSendResult(kind=FcmResultKind.TOKEN_INVALID, error_code="UNREGISTERED")
        retry = FcmSendResult(kind=FcmResultKind.RETRYABLE, retry_after_s=3)
        ok = FcmSendResult(kind=FcmResultKind.ACCEPTED)
        client = FakeFcmClient(results_by_token={"dead": bad, "busy": [retry, ok]})
        assert (
            await client.send(FcmMessage(payload={}, token="dead"))
        ).kind is FcmResultKind.TOKEN_INVALID
        assert (
            await client.send(FcmMessage(payload={}, token="busy"))
        ).kind is FcmResultKind.RETRYABLE
        assert (
            await client.send(FcmMessage(payload={}, token="busy"))
        ).kind is FcmResultKind.ACCEPTED
        assert (
            await client.send(FcmMessage(payload={}, token="busy"))
        ).kind is FcmResultKind.ACCEPTED

    def test_fixture_is_installed(self, fake_fcm):
        assert get_fcm_client() is fake_fcm

    def test_unconfigured_real_client(self):
        fcm.set_fcm_client_override(None)
        with pytest.raises(RuntimeError):
            get_fcm_client()


class TestSharedFixtures:
    async def test_snapshot_builder_overwrites(
        self, async_session, fs_site, fs_zones, fs_snapshot, fixed_clock
    ):
        await fs_snapshot(
            fs_site,
            capacity=100,
            occupied=50,
            zones={"b1": {"capacity": 10, "occupied": 9}},
        )
        fixed_clock.advance(30)
        await fs_snapshot(
            fs_site,
            capacity=100,
            occupied=60,
            health="PARTIAL",
            zones={
                "b1": {
                    "capacity": 10,
                    "occupied": 10,
                    "received_at": fixed_clock.now() - timedelta(minutes=5),
                }
            },
        )
        view = await load_snapshot(async_session, fs_site.id)
        assert view.site is not None
        assert view.site.occupied == 60 and view.site.free_usable == 40
        assert view.site.health.value == "PARTIAL"
        assert view.site.received_at == fixed_clock.now()
        assert view.zones["b1"].received_at == fixed_clock.now() - timedelta(minutes=5)


@pytest_asyncio.fixture
async def perm_client(async_session) -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()

    @app.get("/read")
    async def read(
        user: Annotated[CurrentUser, Depends(require_permission(PERM_SITES_READ))]
    ):
        return {"org": user.organization_id}

    @app.get("/announce")
    async def announce(
        user: Annotated[
            CurrentUser, Depends(require_permission(PERM_SITE_PUSH_ANNOUNCE))
        ],
    ):
        return {"ok": True}

    async def _session():
        yield async_session

    app.dependency_overrides[get_async_session] = _session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


class TestRoleTokens:
    async def test_role_matrix(
        self,
        perm_client,
        fs_admin_token,
        fs_operator_token,
        fs_viewer_token,
        fs_no_role_token,
        test_admin_token,
    ):
        def get(path, token):
            return perm_client.get(path, headers={"Authorization": token})

        for token in (
            fs_admin_token,
            fs_operator_token,
            fs_viewer_token,
            test_admin_token,
        ):
            assert (await get("/read", token)).status_code == 200
        assert (await get("/read", fs_no_role_token)).status_code == 403
        assert (await get("/announce", fs_admin_token)).status_code == 200
        assert (
            await get("/announce", test_admin_token)
        ).status_code == 200  # super admin
        assert (await get("/announce", fs_operator_token)).status_code == 403
        assert (await get("/announce", fs_viewer_token)).status_code == 403

    async def test_second_org_token_carries_its_org(
        self, perm_client, fs_second_org_admin_token, second_organization
    ):
        response = await perm_client.get(
            "/read", headers={"Authorization": fs_second_org_admin_token}
        )
        assert response.json() == {"org": str(second_organization.id)}
