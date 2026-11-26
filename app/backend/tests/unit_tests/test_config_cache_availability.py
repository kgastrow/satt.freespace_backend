"""
Regression tests for the request-logging config cache.

``get_request_logging_config`` runs on the request-logging path for EVERY
request. It used to gate its Redis read on ``cache_service._enabled``, which is
the configuration switch, not a health signal. Once a single Redis blip latched
``_enabled`` to False, this function fell through to ``_load_config_from_db``
for every request thereafter - a database round trip per request, for the life
of the process, with nothing that could ever turn it back on.

The guard is now ``await cache_service._is_available()``, which honours the
post-error cooldown and re-probes once it expires.
"""

import time as real_time

import pytest
import redis.asyncio as redis

from src.core.config import settings
from src.services import cache as cache_module
from src.services import config_cache as config_cache_module
from src.services.cache import cache_service


class FakeClock:
    """Replaces only the cache module's ``time`` name (see test_cache_availability)."""

    def __init__(self, start: float = 20_000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return real_time.time()

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ping_error: BaseException | None = None

    async def ping(self) -> bool:
        if self.ping_error is not None:
            raise self.ping_error
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        removed = 0
        for key in keys:
            removed += 1 if self.store.pop(key, None) is not None else 0
        return removed


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(cache_module, "time", fake)
    return fake


@pytest.fixture
def live_cache(monkeypatch, clock) -> FakeRedis:
    """Point the cache_service singleton at a fake, healthy Redis."""
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "_enabled", True)
    monkeypatch.setattr(cache_service, "_redis", fake)
    monkeypatch.setattr(cache_service, "_unavailable_until", 0.0)
    return fake


@pytest.fixture
def db_loads(monkeypatch) -> list[int]:
    """Count database loads; the whole point of the cache is to avoid these."""
    calls: list[int] = []

    async def _counted_load():
        calls.append(1)
        return config_cache_module.RequestLoggingConfig(
            enabled=True,
            db_enabled=False,
            max_body_size=1234,
            retention_days=7,
        )

    monkeypatch.setattr(config_cache_module, "_load_config_from_db", _counted_load)
    return calls


@pytest.mark.asyncio
async def test_healthy_cache_serves_without_touching_the_database(live_cache, db_loads):
    """First call warms the cache; subsequent calls must not hit the database."""
    first = await config_cache_module.get_request_logging_config()
    assert first.max_body_size == 1234
    assert len(db_loads) == 1
    assert config_cache_module.REQUEST_LOGGING_CONFIG_KEY in live_cache.store

    for _ in range(5):
        again = await config_cache_module.get_request_logging_config()
        assert again.max_body_size == 1234
    assert len(db_loads) == 1, "cached config must not re-query the database"


@pytest.mark.asyncio
async def test_config_cache_stops_hitting_the_database_once_redis_recovers(
    live_cache, db_loads, clock
):
    """The core regression: a blip must not mean a DB query per request forever."""
    await config_cache_module.get_request_logging_config()
    assert len(db_loads) == 1

    # Redis goes away. The config must still be served - from the database.
    live_cache.ping_error = redis.TimeoutError("no reply within socket_timeout")
    await config_cache_module.get_request_logging_config()
    assert len(db_loads) == 2

    # Still inside the cooldown: database again, and no Redis traffic.
    await config_cache_module.get_request_logging_config()
    assert len(db_loads) == 3

    # Redis recovers and the cooldown expires. The next call re-probes,
    # reads the still-cached value, and the database is left alone.
    live_cache.ping_error = None
    clock.advance(settings.CACHE_UNAVAILABLE_COOLDOWN + 1)

    loads_after_outage = len(db_loads)
    for _ in range(5):
        config = await config_cache_module.get_request_logging_config()
        assert config.max_body_size == 1234
    assert len(db_loads) == loads_after_outage, (
        "config cache never recovered: it is still querying the database "
        "on every call after Redis came back"
    )


@pytest.mark.asyncio
async def test_redis_failure_does_not_escape_to_the_caller(live_cache, db_loads):
    """A hung Redis must degrade to the database, not raise."""
    live_cache.ping_error = OSError("broken pipe")
    config = await config_cache_module.get_request_logging_config()
    assert config.max_body_size == 1234


@pytest.mark.asyncio
async def test_invalidate_is_a_no_op_while_redis_is_down(live_cache):
    """Invalidation must not raise when the backend is unreachable."""
    live_cache.store[config_cache_module.REQUEST_LOGGING_CONFIG_KEY] = "{}"
    live_cache.ping_error = redis.ConnectionError("refused")
    await config_cache_module.invalidate_request_logging_config()


@pytest.mark.asyncio
async def test_cache_disabled_by_configuration_uses_the_database(
    monkeypatch, db_loads, clock
):
    """With caching switched off in config there is no Redis traffic at all."""
    fake = FakeRedis()
    fake.ping_error = AssertionError("must not probe when CACHE_ENABLED is false")
    monkeypatch.setattr(cache_service, "_enabled", False)
    monkeypatch.setattr(cache_service, "_redis", fake)

    config = await config_cache_module.get_request_logging_config()
    assert config.max_body_size == 1234
    assert len(db_loads) == 1
