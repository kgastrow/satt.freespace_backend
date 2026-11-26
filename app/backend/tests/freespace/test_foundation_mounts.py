"""Foundation: /v1 and /mock mounts, mock-mode startup guard (D1, D13, BF-84),
router registration, worker task wrappers."""

from __future__ import annotations

from types import SimpleNamespace
import uuid

from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from src.api import freespace_public
from src.services.freespace.mock_mode import (
    MockModeConfigurationError,
    mock_routes_enabled,
    validate_mock_mode,
)


def _settings(mock: bool, debug: bool, ack: bool) -> SimpleNamespace:
    return SimpleNamespace(
        FREESPACE_MOCK_MODE=mock, DEBUG=debug, FREESPACE_MOCK_MODE_ACKNOWLEDGED=ack
    )


class TestMockGuard:
    @pytest.mark.parametrize(
        "mock,debug,ack",
        [
            (False, False, False),
            (False, True, False),
            (True, True, False),
            (True, False, True),
            (True, True, True),
        ],
    )
    def test_allowed(self, mock, debug, ack):
        validate_mock_mode(_settings(mock, debug, ack))

    def test_refuses_production_mock_mode(self):
        with pytest.raises(MockModeConfigurationError):
            validate_mock_mode(_settings(mock=True, debug=False, ack=False))

    def test_create_application_refuses_to_start(self, monkeypatch):
        import main

        monkeypatch.setattr(main.settings, "FREESPACE_MOCK_MODE", True)
        monkeypatch.setattr(main.settings, "DEBUG", False)
        monkeypatch.setattr(main.settings, "FREESPACE_MOCK_MODE_ACKNOWLEDGED", False)
        with pytest.raises(MockModeConfigurationError):
            main.create_application()

    def test_settings_default_off(self):
        from src.core.config import Settings

        fresh = Settings()
        assert fresh.FREESPACE_MOCK_MODE is False
        assert fresh.FREESPACE_MOCK_MODE_ACKNOWLEDGED is False
        assert mock_routes_enabled(fresh) is False


class TestMountsOnRealApp:
    async def test_mock_routes_absent_when_off(self, client):
        """BT-10: mock mode off -> /mock/* is 404 (not 403)."""
        for method, path in (
            ("POST", "/mock/clock"),
            ("POST", "/mock/sites/x/occupancy"),
        ):
            response = await client.request(method, path)
            assert response.status_code == 404, path

    async def test_v1_mount_serves_placeholder_404(self, client):
        response = await client.get("/v1/definitely-not-a-route")
        assert response.status_code == 404

    def test_no_mock_paths_registered(self):
        import main

        assert not [
            r for r in main.app.routes if getattr(r, "path", "").startswith("/mock")
        ]


class TestIncludeHelper:
    async def _client_for(self, settings, monkeypatch) -> AsyncClient:
        probe = APIRouter(prefix="/mock")

        @probe.get("/probe")
        async def _probe():
            return {"mock": True}

        public_probe = APIRouter()

        @public_probe.get("/ingest/probe")
        async def _public():
            return {"public": True}

        monkeypatch.setattr(freespace_public, "mock_router", probe)
        monkeypatch.setattr(freespace_public, "public_router", public_probe)
        app = FastAPI()
        freespace_public.include_freespace_public_routers(app, settings)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    async def test_mock_router_only_in_mock_mode(self, monkeypatch):
        async with await self._client_for(
            _settings(False, True, False), monkeypatch
        ) as c:
            assert (await c.get("/mock/probe")).status_code == 404
            assert (await c.get("/v1/ingest/probe")).json() == {"public": True}
        async with await self._client_for(
            _settings(True, True, False), monkeypatch
        ) as c:
            assert (await c.get("/mock/probe")).json() == {"mock": True}
            assert (await c.get("/ingest/probe")).status_code == 404  # only under /v1


def test_router_prefixes_and_admin_order():
    """Skeleton routers carry the agreed prefixes; literal-route routers are
    included before freespace_sites (CLAUDE.md rule 13)."""
    from src.api import (
        freespace_events,
        freespace_keys,
        freespace_push,
        freespace_sites,
        freespace_stats,
        freespace_zones,
    )
    from src.api.freespace_public import app_sites, devices, ingest, mock
    from src.api.v1 import v1_router

    assert ingest.router.prefix == "/ingest"
    assert app_sites.router.prefix == "/sites"
    assert devices.router.prefix == "/devices"
    assert mock.router.prefix == "/mock"
    assert freespace_sites.router.prefix == "/admin/sites"
    assert freespace_stats.router.prefix == "/admin/sites"
    assert freespace_zones.router.prefix == "/admin/sites/{site_id}/zones"
    assert freespace_keys.router.prefix == "/admin/sites/{site_id}/ingest-keys"
    assert freespace_keys.app_keys_router.prefix == "/admin/app-keys"
    assert freespace_events.router.prefix == "/admin/sites/{site_id}/events"
    assert freespace_push.router.prefix == "/admin/sites/{site_id}"

    import inspect

    source = inspect.getsource(__import__("src.api.v1", fromlist=["v1_router"]))
    assert source.index("freespace_stats.router)") < source.index(
        "freespace_sites.router)"
    )
    assert v1_router is not None


class TestWorkerWrappers:
    async def test_fanout_task_survives_not_implemented(self, monkeypatch):
        """The wrapper's NotImplementedError guard (kept for safety) still
        returns instead of raising."""
        from src.services.freespace import fanout
        from src.workers.freespace_tasks import fanout_advisory_task

        async def stub(*args, **kwargs):
            raise NotImplementedError("stub")

        monkeypatch.setattr(fanout, "run_fanout", stub)
        result = await fanout_advisory_task(
            {"session_factory": object()}, str(uuid.uuid4())
        )
        assert result["status"] == "not_implemented"

    async def test_engine_tick_delegates(self, monkeypatch):
        from src.services.freespace import evaluator
        from src.services.freespace.evaluator import TickResult
        from src.workers.freespace_tasks import engine_tick

        async def fake_tick(session_factory, clock):
            return TickResult(sites_evaluated=2, fanouts_enqueued=1)

        monkeypatch.setattr(evaluator, "run_engine_tick", fake_tick)
        result = await engine_tick({"session_factory": object()})
        assert result["status"] == "ok"
        assert result["sites_evaluated"] == 2
        assert result["fanouts_enqueued"] == 1

    async def test_fanout_task_reenqueues(self, monkeypatch):
        from src.constants.freespace import FanoutStatus
        from src.services.freespace import fanout
        from src.services.freespace.fanout import FanoutResult
        from src.services.tasks import task_queue
        from src.workers.freespace_tasks import fanout_advisory_task

        event_id = uuid.uuid4()
        calls = []

        async def fake_run(session_factory, eid, **kwargs):
            return FanoutResult(
                event_id=eid, status=FanoutStatus.RUNNING, reenqueue_in_s=12.5
            )

        async def fake_enqueue(name, *args, **kwargs):
            calls.append((name, args, kwargs))
            return "job"

        monkeypatch.setattr(fanout, "run_fanout", fake_run)
        monkeypatch.setattr(task_queue, "enqueue_job", fake_enqueue)
        result = await fanout_advisory_task(
            {"session_factory": object()}, str(event_id)
        )
        assert result["reenqueued"] is True
        assert calls == [
            ("fanout_advisory_task", (str(event_id),), {"_defer_by": 12.5})
        ]

    def test_registered_in_worker(self):
        from src.constants.job_types import JOB_TYPES_BY_CODE
        from src.workers.worker import WorkerSettings

        names = {f.__name__ for f in WorkerSettings.functions}
        assert {"fanout_advisory_task", "engine_tick"} <= names
        assert (
            "engine_tick" in JOB_TYPES_BY_CODE
            and "fanout_advisory_task" in JOB_TYPES_BY_CODE
        )
