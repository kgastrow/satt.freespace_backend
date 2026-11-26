"""M2: per-ingest-key rate limiter (BF-18)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from src.api.freespace_deps import IngestAuth
from src.core.config import settings
from src.database import get_async_session
from src.services.freespace import redis_client
from src.services.freespace.ingest_rate_limit import (
    clamp_retry_after,
    enforce_ingest_rate_limit,
    parse_limit,
)
from tests.freespace.conftest import make_ingest_key


@pytest_asyncio.fixture
async def rl_client(async_session) -> AsyncGenerator[AsyncClient, None]:
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def _flatten(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
        return JSONResponse(
            status_code=exc.status_code, content=detail, headers=exc.headers
        )

    @app.post("/ingest")
    async def ingest(auth: Annotated[IngestAuth, Depends(enforce_ingest_rate_limit)]):
        return {"key": str(auth.key.id)}

    async def _session():
        yield async_session

    app.dependency_overrides[get_async_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def bearer(plain: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {plain}"}


class TestLimiter:
    async def test_13th_request_429(self, rl_client, fs_ingest_key):
        h = bearer(fs_ingest_key[0])
        for _ in range(12):
            assert (await rl_client.post("/ingest", headers=h)).status_code == 200
        r = await rl_client.post("/ingest", headers=h)
        assert r.status_code == 429
        assert r.json()["detail_code"] == "ingest.rate_limited"
        retry = r.headers["Retry-After"]
        assert retry.isdigit() and 1 <= int(retry) <= 600
        assert int(retry) == 60  # clock is frozen: full window remaining

    async def test_window_slides(self, rl_client, fs_ingest_key, fixed_clock):
        h = bearer(fs_ingest_key[0])
        for _ in range(12):
            await rl_client.post("/ingest", headers=h)
        assert (await rl_client.post("/ingest", headers=h)).status_code == 429
        fixed_clock.advance(20)
        r = await rl_client.post("/ingest", headers=h)
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) == 40
        fixed_clock.advance(41)
        assert (await rl_client.post("/ingest", headers=h)).status_code == 200

    async def test_rejected_requests_not_counted(
        self, rl_client, fs_ingest_key, fixed_clock
    ):
        h = bearer(fs_ingest_key[0])
        for _ in range(12):
            await rl_client.post("/ingest", headers=h)
        for _ in range(5):
            assert (await rl_client.post("/ingest", headers=h)).status_code == 429
        fixed_clock.advance(61)
        assert (await rl_client.post("/ingest", headers=h)).status_code == 200

    async def test_separate_keys_separate_budgets(
        self, rl_client, async_session, fs_site, fs_ingest_key
    ):
        other, _ = await make_ingest_key(async_session, fs_site, name="second")
        h1, h2 = bearer(fs_ingest_key[0]), bearer(other)
        for _ in range(12):
            await rl_client.post("/ingest", headers=h1)
        assert (await rl_client.post("/ingest", headers=h1)).status_code == 429
        assert (await rl_client.post("/ingest", headers=h2)).status_code == 200

    async def test_unauthenticated_is_401_not_counted(self, rl_client):
        r = await rl_client.post("/ingest")
        assert r.status_code == 401

    async def test_limit_from_settings(self, rl_client, fs_ingest_key, monkeypatch):
        monkeypatch.setattr(settings, "RATE_LIMIT_FREESPACE_INGEST", "2/minute")
        h = bearer(fs_ingest_key[0])
        assert (await rl_client.post("/ingest", headers=h)).status_code == 200
        assert (await rl_client.post("/ingest", headers=h)).status_code == 200
        assert (await rl_client.post("/ingest", headers=h)).status_code == 429

    async def test_fails_open_without_redis(self, rl_client, fs_ingest_key):
        redis_client.set_redis_override(None)
        from src.core.redis_pool import redis_pool_manager

        if redis_pool_manager.client_db0 is not None:
            pytest.skip("real redis present")
        h = bearer(fs_ingest_key[0])
        for _ in range(15):
            assert (await rl_client.post("/ingest", headers=h)).status_code == 200

    async def test_fails_open_on_redis_error(
        self, rl_client, fs_ingest_key, fs_redis, monkeypatch
    ):
        async def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(fs_redis, "eval", boom)  # atomic Lua window (F6)
        h = bearer(fs_ingest_key[0])
        for _ in range(15):
            assert (await rl_client.post("/ingest", headers=h)).status_code == 200


class TestHelpers:
    def test_parse_limit(self):
        assert parse_limit("12/minute") == (12, 60)
        assert parse_limit("5/second") == (5, 1)
        assert parse_limit("garbage") == (12, 60)

    def test_clamp(self):
        assert clamp_retry_after(0) == 1
        assert clamp_retry_after(0.2) == 1
        assert clamp_retry_after(59.1) == 60
        assert clamp_retry_after(5000) == 600
        assert clamp_retry_after(float("inf")) == 60
        assert clamp_retry_after(float("nan")) == 60
