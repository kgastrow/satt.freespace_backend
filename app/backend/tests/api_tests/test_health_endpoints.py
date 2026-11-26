"""
Tests for /health/live (liveness), /health (Freespace BF-80 service health,
see tests/freespace/test_integration_wiring.py) and /health/detailed.

/health/detailed used to answer HTTP 200 "healthy" straight through a total
Redis failure, and HTTP 200 "unhealthy" through a database failure - so a
monitor watching the status code saw green during an outage. These tests pin
the corrected contract.
"""

from httpx import AsyncClient
import pytest


class _DeadEngine:
    """Stands in for main.async_engine when the database is unreachable."""

    def __init__(self, message: str = "db down"):
        self.message = message

    def connect(self):
        raise RuntimeError(self.message)


class _DeadRedis:
    def __init__(self, message: str = "redis down"):
        self.message = message

    async def ping(self):
        raise RuntimeError(self.message)


# ==================== /health/live : liveness ====================


@pytest.mark.asyncio
async def test_health_is_a_constant(client: AsyncClient):
    """Liveness must not probe dependencies: restarting the app does not fix a
    dead database, it just kills a process that could still serve cached reads."""
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@pytest.mark.asyncio
async def test_health_is_not_cacheable(client: AsyncClient):
    for path in ("/health/live", "/health"):
        response = await client.get(path)

        assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_health_stays_200_when_dependencies_fail(
    client: AsyncClient, monkeypatch
):
    """Even with the database gone, liveness is 200 while the process is up."""
    import main

    monkeypatch.setattr(
        main,
        "async_engine",
        _DeadEngine("connection to server at 10.1.2.3 port 5432 failed"),
    )

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def _no_tick(monkeypatch, async_session):
    """Point /health at the TEST database (it otherwise opens
    ``src.database.AsyncSessionLocal``, i.e. the configured one) and pin the
    tick source to "none recorded", so only the grace window decides."""
    import src.database
    from src.services.freespace import health

    class _Ctx:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    async def none(_factory):
        return None

    monkeypatch.setattr(src.database, "AsyncSessionLocal", lambda: _Ctx())
    monkeypatch.setattr(health, "_last_tick", none)
    return health


@pytest.mark.asyncio
async def test_service_health_within_grace_is_200(
    client: AsyncClient, monkeypatch, async_session
):
    """/health (BF-80): fresh process, no tick yet -> 200, status fields only."""
    health = _no_tick(monkeypatch, async_session)
    health.reset_health_state()
    try:
        response = await client.get("/health")
    finally:
        health.reset_health_state()

    assert response.status_code == 200
    assert set(response.json()) == {"status", "database", "engine"}
    assert response.json()["engine"]["status"] == "no_tick_yet"


@pytest.mark.asyncio
async def test_service_health_after_grace_without_tick_is_503(
    client: AsyncClient, monkeypatch, async_session
):
    from datetime import UTC, datetime, timedelta

    health = _no_tick(monkeypatch, async_session)
    health.reset_health_state(
        datetime.now(UTC) - timedelta(seconds=health.STARTUP_GRACE_S + 60)
    )
    try:
        response = await client.get("/health")
    finally:
        health.reset_health_state()

    assert response.status_code == 503
    assert set(response.json()) == {"status", "database", "engine"}
    assert response.json()["engine"]["status"] == "stale"


# ==================== /health/detailed : readiness ====================


@pytest.mark.asyncio
async def test_detailed_reports_components(client: AsyncClient):
    response = await client.get("/health/detailed")

    assert response.status_code == 200
    body = response.json()
    assert body["components"]["database"] == "ok"
    assert "database_pool" in body["components"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_database_failure_returns_503(client: AsyncClient, monkeypatch):
    """Postgres is the hard dependency: nothing works without it."""
    import main

    monkeypatch.setattr(
        main,
        "async_engine",
        _DeadEngine("connection to server at 10.1.2.3 port 5432 failed"),
    )

    response = await client.get("/health/detailed")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_database_failure_does_not_leak_connection_details(
    client: AsyncClient, monkeypatch
):
    """SQLAlchemy/asyncpg errors carry host, port, user and database name. This
    endpoint is typically reachable unauthenticated, so the text is logged, not
    published."""
    import main

    secret = "connection to server at 10.1.2.3 port 5432 user=appuser db=appdb failed"

    monkeypatch.setattr(main, "async_engine", _DeadEngine(secret))

    response = await client.get("/health/detailed")

    assert response.json()["components"]["database"] == "error"
    assert "10.1.2.3" not in response.text
    assert "appuser" not in response.text


@pytest.mark.asyncio
async def test_redis_failure_degrades_status(client: AsyncClient, monkeypatch):
    """The regression: a Redis failure used to leave status "healthy" and the
    HTTP code 200. Redis is a soft dependency, so it stays 200 - but the body
    must say "degraded"."""
    import main

    monkeypatch.setattr(
        main.cache_service,
        "_redis",
        _DeadRedis("Error 111 connecting to 10.1.2.4:6379"),
    )

    response = await client.get("/health/detailed")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["components"]["redis"] == "error"
    assert "10.1.2.4" not in response.text


@pytest.mark.asyncio
async def test_database_failure_outranks_redis_failure(
    client: AsyncClient, monkeypatch
):
    """A hard failure decides the code even when a soft one is also present."""
    import main

    monkeypatch.setattr(main, "async_engine", _DeadEngine())
    monkeypatch.setattr(main.cache_service, "_redis", _DeadRedis())

    response = await client.get("/health/detailed")

    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_disabled_redis_is_not_a_failure(client: AsyncClient, monkeypatch):
    """ "disabled" is a deliberate configuration, not a fault."""
    import main

    monkeypatch.setattr(main.cache_service, "_redis", None)

    response = await client.get("/health/detailed")

    assert response.status_code == 200
    assert response.json()["components"]["redis"] == "disabled"
