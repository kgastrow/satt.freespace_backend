"""Foundation: ingest-key and app-key dependencies (BF-10, D3, §6.2)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
import pytest_asyncio

from src.api.freespace_deps import (
    IngestAuth,
    get_ingest_site,
    invalidate_app_key_cache,
    require_app_key,
)
from src.constants.freespace import REDIS_APP_KEYS_KEY
from src.database import get_async_session
from tests.freespace.conftest import make_app_key, make_ingest_key


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(HTTPException)
    async def _flatten(request: Request, exc: HTTPException):  # mirrors main.py
        detail = exc.detail
        if isinstance(detail, dict):
            return JSONResponse(
                status_code=exc.status_code, content=detail, headers=exc.headers
            )
        return JSONResponse(
            status_code=exc.status_code, content={"detail": detail}, headers=exc.headers
        )

    @app.get("/ingest")
    async def ingest(auth: Annotated[IngestAuth, Depends(get_ingest_site)]):
        return {"site": auth.site.slug, "key": str(auth.key.id)}

    @app.get("/app", dependencies=[Depends(require_app_key)])
    async def app_route():
        return {"ok": True}

    return app


@pytest_asyncio.fixture
async def dep_client(async_session) -> AsyncGenerator[AsyncClient, None]:
    app = _build_app()

    async def _session():
        yield async_session

    app.dependency_overrides[get_async_session] = _session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


class TestIngestKey:
    async def test_valid_key_resolves_site_and_records_use(
        self, dep_client, async_session, fs_site, fs_ingest_key, fixed_clock
    ):
        plaintext, key = fs_ingest_key
        response = await dep_client.get(
            "/ingest", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert response.status_code == 200
        assert response.json() == {"site": fs_site.slug, "key": str(key.id)}
        await async_session.refresh(key)
        assert key.last_used_at.replace(tzinfo=None) == fixed_clock.now().replace(
            tzinfo=None
        )
        assert key.last_used_ip == "127.0.0.1"

    async def test_missing_header(self, dep_client, fs_ingest_key):
        response = await dep_client.get("/ingest")
        assert response.status_code == 401
        assert response.json()["detail_code"] == "ingest.unauthorized"
        assert response.headers["www-authenticate"] == "Bearer"

    async def test_wrong_scheme_and_malformed(self, dep_client, fs_ingest_key):
        plaintext, _ = fs_ingest_key
        for header in (f"Basic {plaintext}", "Bearer", "Bearer has space", plaintext):
            response = await dep_client.get(
                "/ingest", headers={"Authorization": header}
            )
            assert response.status_code == 401, header

    async def test_unknown_key(self, dep_client, fs_site):
        response = await dep_client.get(
            "/ingest", headers={"Authorization": "Bearer fsk_nope"}
        )
        assert response.status_code == 401
        assert response.json()["detail_code"] == "ingest.unauthorized"

    async def test_revoked_key(self, dep_client, async_session, fs_site, fixed_clock):
        plaintext, _ = await make_ingest_key(
            async_session, fs_site, revoked_at=fixed_clock.now()
        )
        response = await dep_client.get(
            "/ingest", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert response.status_code == 401
        assert response.json()["detail_code"] == "ingest.key_revoked"

    async def test_expired_key(self, dep_client, async_session, fs_site, fixed_clock):
        plaintext, _ = await make_ingest_key(
            async_session, fs_site, expires_at=fixed_clock.now() + timedelta(minutes=5)
        )
        headers = {"Authorization": f"Bearer {plaintext}"}
        assert (await dep_client.get("/ingest", headers=headers)).status_code == 200
        fixed_clock.advance(300)
        response = await dep_client.get("/ingest", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail_code"] == "ingest.key_expired"

    async def test_deleted_key_and_deleted_site(
        self, dep_client, async_session, fs_site, fixed_clock
    ):
        deleted_plain, _ = await make_ingest_key(
            async_session, fs_site, name="old", deleted_time=fixed_clock.now()
        )
        assert (
            await dep_client.get(
                "/ingest", headers={"Authorization": f"Bearer {deleted_plain}"}
            )
        ).status_code == 401

        plaintext, _ = await make_ingest_key(async_session, fs_site, name="live")
        fs_site.deleted_time = fixed_clock.now()
        await async_session.commit()
        assert (
            await dep_client.get(
                "/ingest", headers={"Authorization": f"Bearer {plaintext}"}
            )
        ).status_code == 401

    async def test_two_valid_keys_for_one_site(
        self, dep_client, async_session, fs_site
    ):
        """BF-10b: rotation overlaps, both keys work."""
        first, _ = await make_ingest_key(async_session, fs_site, name="old")
        second, _ = await make_ingest_key(async_session, fs_site, name="new")
        for plaintext in (first, second):
            response = await dep_client.get(
                "/ingest", headers={"Authorization": f"Bearer {plaintext}"}
            )
            assert response.json()["site"] == fs_site.slug

    async def test_key_is_bound_to_its_own_site(
        self, dep_client, async_session, fs_site, fs_second_site
    ):
        plaintext, _ = await make_ingest_key(async_session, fs_second_site)
        response = await dep_client.get(
            "/ingest", headers={"Authorization": f"Bearer {plaintext}"}
        )
        assert response.json()["site"] == fs_second_site.slug


class TestAppKey:
    async def test_missing_and_unknown(self, dep_client, fs_app_key):
        missing = await dep_client.get("/app")
        assert missing.status_code == 401
        assert missing.json()["detail_code"] == "app_key.invalid"
        unknown = await dep_client.get(
            "/app", headers={"X-Freespace-App-Key": "fsa_unknown"}
        )
        assert unknown.status_code == 401

    async def test_valid(self, dep_client, fs_app_headers):
        response = await dep_client.get("/app", headers=fs_app_headers)
        assert response.status_code == 200

    async def test_two_keys_valid_at_once(self, dep_client, async_session):
        a, _ = await make_app_key(async_session, name="a")
        b, _ = await make_app_key(async_session, name="b")
        for plaintext in (a, b):
            response = await dep_client.get(
                "/app", headers={"X-Freespace-App-Key": plaintext}
            )
            assert response.status_code == 200

    async def test_valid_set_is_cached_and_invalidated(
        self, dep_client, async_session, fs_redis, fs_app_key, fixed_clock
    ):
        plaintext, row = fs_app_key
        headers = {"X-Freespace-App-Key": plaintext}
        assert (await dep_client.get("/app", headers=headers)).status_code == 200
        assert 0 < await fs_redis.ttl(REDIS_APP_KEYS_KEY) <= 60

        row.revoked_at = fixed_clock.now()
        await async_session.commit()
        # Still accepted from the cache until it expires or is invalidated.
        assert (await dep_client.get("/app", headers=headers)).status_code == 200
        await invalidate_app_key_cache()
        assert (await dep_client.get("/app", headers=headers)).status_code == 401

    async def test_works_without_redis(self, dep_client, fs_app_headers):
        from src.services.freespace import redis_client

        redis_client.set_redis_override(None)
        assert (await dep_client.get("/app", headers=fs_app_headers)).status_code == 200
