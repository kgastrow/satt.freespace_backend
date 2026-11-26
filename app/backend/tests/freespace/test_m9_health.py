"""M9: GET /health verdict (BF-80)."""

from __future__ import annotations

import pytest
import pytest_asyncio

from src.constants.freespace import REDIS_ENGINE_TICK_KEY
from src.services.freespace import health


class _BrokenSession:
    async def __aenter__(self):
        raise ConnectionError("password=hunter2 host=10.0.0.5")

    async def __aexit__(self, *exc):
        return False


def broken_factory():
    return _BrokenSession()


@pytest_asyncio.fixture
async def factory(async_session):
    class _Ctx:
        async def __aenter__(self):
            return async_session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


@pytest.fixture(autouse=True)
def _reset():
    health.reset_health_state()
    yield
    health.reset_health_state()


@pytest.mark.asyncio
async def test_fresh_start_is_healthy_with_no_tick_note(factory, fixed_clock):
    report = await health.check_health(factory, fixed_clock)
    assert report.healthy
    assert report.engine_status == health.ENGINE_NO_TICK_YET
    assert report.tick_age_s is None
    assert report.to_dict()["engine"]["status"] == "no_tick_yet"


@pytest.mark.asyncio
async def test_no_tick_after_grace_is_unhealthy(factory, fixed_clock):
    await health.check_health(factory, fixed_clock)
    fixed_clock.advance(seconds=health.STARTUP_GRACE_S + 1)
    report = await health.check_health(factory, fixed_clock)
    assert not report.healthy
    assert report.engine_status == health.ENGINE_STALE


@pytest.mark.asyncio
async def test_recent_tick_is_healthy_and_old_tick_is_not(
    factory, fixed_clock, fs_redis
):
    await fs_redis.set(REDIS_ENGINE_TICK_KEY, fixed_clock.now().isoformat())
    fixed_clock.advance(seconds=health.TICK_STALE_AFTER_S)
    report = await health.check_health(factory, fixed_clock)
    assert report.healthy and report.tick_age_s == health.TICK_STALE_AFTER_S
    assert report.engine_status == health.ENGINE_OK

    fixed_clock.advance(seconds=1)
    report = await health.check_health(factory, fixed_clock)
    assert not report.healthy
    assert report.engine_status == health.ENGINE_STALE
    assert report.tick_age_s == health.TICK_STALE_AFTER_S + 1


@pytest.mark.asyncio
async def test_database_down_is_unhealthy_and_leaks_nothing(fixed_clock, fs_redis):
    await fs_redis.set(REDIS_ENGINE_TICK_KEY, fixed_clock.now().isoformat())
    report = await health.check_health(broken_factory, fixed_clock)
    assert not report.healthy
    body = str(report.to_dict())
    assert report.to_dict()["database"] == "unreachable"
    assert "hunter2" not in body and "10.0.0.5" not in body


@pytest.mark.asyncio
async def test_db_fallback_when_redis_has_no_tick(
    factory, fixed_clock, fs_site, async_session
):
    from sqlalchemy import update

    from src.models.site_engine_state import SiteEngineState

    await async_session.execute(
        update(SiteEngineState)
        .where(SiteEngineState.site_id == fs_site.id)
        .values(last_evaluated_at=fixed_clock.now())
    )
    await async_session.commit()
    fixed_clock.advance(seconds=60)
    report = await health.check_health(factory, fixed_clock)
    assert report.healthy and report.tick_age_s == 60


@pytest.mark.asyncio
async def test_report_keys_are_status_only(factory, fixed_clock):
    body = (await health.check_health(factory, fixed_clock)).to_dict()
    assert set(body) == {"status", "database", "engine"}
    assert set(body["engine"]) == {"status", "lastTickAgeSeconds"}


@pytest.mark.asyncio
async def test_injected_grace_window_is_independent_of_the_global_one(
    factory, fixed_clock
):
    """The grace window is injectable: a pinned old start is definitely over,
    and the process-global window is untouched by it."""
    from datetime import timedelta

    old = health.StartupGrace(
        first_check_at=fixed_clock.now() - timedelta(seconds=health.STARTUP_GRACE_S + 1)
    )
    report = await health.check_health(factory, fixed_clock, grace=old)
    assert not report.healthy and report.engine_status == health.ENGINE_STALE
    report = await health.check_health(factory, fixed_clock)
    assert report.healthy and report.engine_status == health.ENGINE_NO_TICK_YET

    health.reset_health_state(fixed_clock.now() - timedelta(seconds=10_000))
    assert not (await health.check_health(factory, fixed_clock)).healthy
