"""
Tests that check_db_pool_health_handler reports what it actually observes.

It used to run ``SELECT 1`` and unconditionally return ``pool_healthy: True``.
It never looked at a pool. It returned exactly the same answer against the
application's ``NullPool`` - which holds no connections at all - as it would
against a saturated QueuePool, so a monitor watching this field could not
distinguish "healthy" from "there is no pool" from "the pool is exhausted".
"""

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from src.services.cron.health import _describe_pool, check_db_pool_health_handler


class _FakeQueuePool:
    """A saturated bounded pool."""

    _max_overflow = 1

    def status(self) -> str:
        return "Pool size: 2 Connections in pool: 0 Current Overflow: 1"

    def size(self) -> int:
        return 2

    def checkedin(self) -> int:
        return 0

    def checkedout(self) -> int:
        return 3

    def overflow(self) -> int:
        return 1


class _FakeEngine:
    def __init__(self, pool) -> None:
        self.pool = pool


class _FakeSession:
    """Enough of AsyncSession for the handler: a bind and an execute."""

    def __init__(self, pool) -> None:
        self._engine = _FakeEngine(pool)

    def get_bind(self, *args, **kwargs):
        return self._engine

    async def execute(self, statement):
        class _Result:
            @staticmethod
            def scalar():
                return 1

        return _Result()


@pytest.mark.asyncio
async def test_reports_the_real_pool_class_of_the_bound_engine(async_session):
    """The handler names the pool it is actually looking at."""
    result = await check_db_pool_health_handler(async_session, {})

    assert result["status"] == "completed"
    assert result["connection_test"] == "passed"
    # The test suite binds a StaticPool; the handler must say so rather than
    # inventing QueuePool statistics.
    assert result["pool_class"] == "StaticPool"
    assert "pool_status" in result


@pytest.mark.asyncio
async def test_nullpool_is_reported_as_unpooled_not_as_healthy_pool():
    """A NullPool holds nothing - claiming a healthy pool would be a lie."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=NullPool)
    try:
        session = _FakeSession(engine.pool)
        result = await check_db_pool_health_handler(session, {})

        assert result["pool_class"] == "NullPool"
        assert result["pooled"] is False
        # NullPool exposes no counters, so none must be fabricated.
        for key in ("size", "checkedout", "pool_capacity", "pool_exhausted"):
            assert key not in result
        # The connection test still passed, and that is all it claims.
        assert result["connection_test"] == "passed"
        assert result["pool_healthy"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_exhausted_pool_is_reported_unhealthy():
    """The failure this handler exists to catch, and previously could not."""
    result = await check_db_pool_health_handler(_FakeSession(_FakeQueuePool()), {})

    assert result["pooled"] is True
    assert result["size"] == 2
    assert result["checkedout"] == 3
    assert result["overflow"] == 1
    assert result["pool_capacity"] == 3
    assert result["pool_exhausted"] is True
    assert result["pool_healthy"] is False
    assert result["alerts"], "exhaustion must raise an alert, not pass silently"


@pytest.mark.asyncio
async def test_healthy_bounded_pool_is_reported_healthy():
    class _Roomy(_FakeQueuePool):
        def checkedout(self) -> int:
            return 1

        def overflow(self) -> int:
            return 0

    result = await check_db_pool_health_handler(_FakeSession(_Roomy()), {})

    assert result["pool_exhausted"] is False
    assert result["pool_healthy"] is True
    assert result["alerts"] == []


@pytest.mark.asyncio
async def test_connection_failure_still_reports_the_pool_state():
    """A failed probe must not lose the pool diagnostics."""

    class _BrokenSession(_FakeSession):
        async def execute(self, statement):
            raise RuntimeError("connection gone")

    result = await check_db_pool_health_handler(_BrokenSession(_FakeQueuePool()), {})

    assert result["status"] == "error"
    assert result["connection_test"] == "failed"
    assert result["pool_healthy"] is False
    assert result["pool_class"] == "_FakeQueuePool"


def test_describe_pool_is_defensive_about_odd_binds():
    """A bind with no pool must degrade, not raise, inside a cron handler."""

    class _NoBind:
        def get_bind(self, *args, **kwargs):
            raise RuntimeError("no bind")

    stats = _describe_pool(_NoBind())
    assert stats["pooled"] is False
    assert "pool_error" in stats

    class _NoPool:
        def get_bind(self, *args, **kwargs):
            return object()

    assert _describe_pool(_NoPool())["pooled"] is False
