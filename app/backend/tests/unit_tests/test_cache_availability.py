"""
Regression tests for cache backend availability handling.

Before this, ``AsyncCacheService._is_available`` did two damaging things:

1. It set ``self._enabled = False`` on the first ``redis.ConnectionError``, and
   nothing anywhere set it back to True. One transient blip therefore disabled
   caching for the entire life of the process.
2. It caught ONLY ``redis.ConnectionError``. In redis-py ``TimeoutError``
   subclasses ``RedisError``, not ``ConnectionError``, and the cache client is
   built with ``socket_timeout=1`` - so a Redis that accepts connections but
   stops answering raised out of ``_is_available()``. Because that call sits
   OUTSIDE each operation's ``try``, the exception escaped the cache service
   entirely and surfaced to the caller as a 500.

The replacement is a monotonic cooldown deadline: an error pauses caching for
``settings.CACHE_UNAVAILABLE_COOLDOWN`` seconds, then the next call re-probes
and, on success, caching resumes. ``_enabled`` is configuration only and is
never flipped at runtime.
"""

import asyncio
import time as real_time

import pytest
import redis.asyncio as redis

from src.core.config import settings
from src.services import cache as cache_module
from src.services.cache import AsyncCacheService


class FakeClock:
    """Stand-in for the ``time`` module inside src.services.cache.

    Only the cache module's ``time`` name is replaced, never the real module -
    patching ``time.monotonic`` globally would move the asyncio event loop's
    own clock.
    """

    def __init__(self, start: float = 10_000.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return real_time.time()

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRedis:
    """Minimal async Redis double with programmable failures."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ping_error: BaseException | None = None
        self.op_error: BaseException | None = None
        self.ping_calls = 0
        self.get_calls = 0
        self.set_calls = 0

    async def ping(self) -> bool:
        self.ping_calls += 1
        if self.ping_error is not None:
            raise self.ping_error
        return True

    async def get(self, key: str):
        self.get_calls += 1
        if self.op_error is not None:
            raise self.op_error
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> bool:
        self.set_calls += 1
        if self.op_error is not None:
            raise self.op_error
        self.store[key] = value
        return True

    async def delete(self, *keys: str) -> int:
        if self.op_error is not None:
            raise self.op_error
        removed = 0
        for key in keys:
            removed += 1 if self.store.pop(key, None) is not None else 0
        return removed

    async def sadd(self, key: str, *values: str) -> int:
        if self.op_error is not None:
            raise self.op_error
        return len(values)

    async def smembers(self, key: str) -> set[str]:
        if self.op_error is not None:
            raise self.op_error
        return set()


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(cache_module, "time", fake)
    return fake


@pytest.fixture
def service(clock) -> tuple[AsyncCacheService, FakeRedis]:
    """A cache service wired to a fake client, with caching switched on.

    ``settings.CACHE_ENABLED`` is False under pytest, so enable it explicitly -
    otherwise every one of these tests would pass vacuously.
    """
    svc = AsyncCacheService()
    svc._enabled = True
    fake = FakeRedis()
    svc._redis = fake  # type: ignore[assignment]
    return svc, fake


# ---------------------------------------------------------------------------
# Recovery: a blip must not be permanent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_caching_recovers_after_cooldown(service, clock):
    """One ConnectionError pauses caching; it resumes after the cooldown."""
    svc, fake = service
    await svc.set_user("u1", {"id": "u1"})
    assert fake.store, "precondition: cache writes reach Redis while healthy"

    # Blip.
    fake.ping_error = redis.ConnectionError("connection refused")
    assert await svc.get_user("u1") is None
    assert svc._unavailable_until > clock.now

    # Redis comes back, but we are still inside the cooldown: no traffic is
    # sent, and the caller keeps falling through to the database.
    fake.ping_error = None
    pings_at_pause = fake.ping_calls
    assert await svc.get_user("u1") is None
    assert fake.ping_calls == pings_at_pause, "must not probe during cooldown"

    # Cooldown expires -> re-probe -> caching resumes.
    clock.advance(settings.CACHE_UNAVAILABLE_COOLDOWN + 1)
    assert await svc.get_user("u1") == {"id": "u1"}
    assert svc._unavailable_until == 0.0


@pytest.mark.asyncio
async def test_error_never_disables_the_configuration_flag(service, clock):
    """``_enabled`` is config, not runtime health, and must survive errors."""
    svc, fake = service
    for exc in (
        redis.ConnectionError("refused"),
        redis.TimeoutError("timed out"),
        OSError("socket died"),
    ):
        fake.ping_error = exc
        assert await svc.get_user("u1") is None
        assert svc._enabled is True, f"{type(exc).__name__} latched caching off"
        # Let the next iteration actually reach the probe.
        clock.advance(settings.CACHE_UNAVAILABLE_COOLDOWN + 1)


# ---------------------------------------------------------------------------
# Nothing escapes: the caller sees a miss, never an exception
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        redis.ConnectionError("refused"),
        redis.TimeoutError("no reply within socket_timeout"),
        redis.RedisError("generic redis failure"),
        OSError("broken pipe"),
        asyncio.TimeoutError(),
    ],
    ids=["connection", "redis-timeout", "redis-error", "oserror", "asyncio-timeout"],
)
@pytest.mark.asyncio
async def test_probe_failures_do_not_escape_to_the_caller(service, exc):
    """A failing health probe returns a miss/no-op, it does not raise.

    This is the 500 that a hung Redis used to produce: ``_is_available()`` is
    called outside each operation's ``try``, so anything it raised went
    straight to the request handler.
    """
    svc, fake = service
    fake.ping_error = exc

    assert await svc.get_jwt_claims("token") is None
    assert await svc.set_jwt_claims("token", {"user_id": "u1"}, 2**31) is False
    assert await svc.get_user("u1") is None
    assert await svc.set_user("u1", {"id": "u1"}) is False
    assert await svc.get_user_roles("o1", "u1") is None
    assert await svc.get_user_permissions("o1", "u1") is None
    assert await svc.get_organization("o1") is None
    assert await svc.invalidate_jwt_for_user("u1") == 0
    assert await svc.invalidate_user("u1") is False


@pytest.mark.parametrize(
    "exc",
    [
        redis.TimeoutError("no reply within socket_timeout"),
        OSError("broken pipe"),
        asyncio.TimeoutError(),
    ],
    ids=["redis-timeout", "oserror", "asyncio-timeout"],
)
@pytest.mark.asyncio
async def test_operation_failures_do_not_escape_and_start_a_cooldown(
    service, clock, exc
):
    """A failure DURING an operation degrades gracefully and pauses caching.

    Without the cooldown, every subsequent request would pay the full
    ``socket_timeout`` again against a Redis known to be sick.
    """
    svc, fake = service
    fake.op_error = exc

    assert await svc.get_user("u1") is None
    assert svc._unavailable_until > clock.now
    assert svc._enabled is True

    gets_before = fake.get_calls
    assert await svc.get_user("u1") is None
    assert fake.get_calls == gets_before, "cooldown must stop the retry storm"


@pytest.mark.asyncio
async def test_decode_error_does_not_pause_caching(service, clock):
    """A bad payload is not a sick backend - do not pause the whole cache."""
    svc, fake = service
    fake.store["user:u1"] = "{not json"

    assert await svc.get_user("u1") is None
    assert svc._unavailable_until == 0.0
    # Still serving.
    assert await svc.set_user("u2", {"id": "u2"}) is True


# ---------------------------------------------------------------------------
# connect() failure is also recoverable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_connect_is_recoverable_via_rebuild(monkeypatch, clock):
    """A failed connect() must not disable caching for the process lifetime."""
    svc = AsyncCacheService()
    svc._enabled = True

    fake = FakeRedis()
    fake.ping_error = redis.TimeoutError("redis accepted but never answered")

    class FakePool:
        @staticmethod
        def from_url(*args, **kwargs):
            return FakePool()

        async def disconnect(self):
            return None

    monkeypatch.setattr(cache_module.redis, "ConnectionPool", FakePool)
    monkeypatch.setattr(cache_module.redis, "Redis", lambda **kwargs: fake)

    await svc.connect()

    # Old behaviour: _enabled=False forever. New behaviour: a cooldown.
    assert svc._enabled is True
    assert svc._redis is None
    assert svc._unavailable_until > clock.now

    # Redis recovers; the pool is still held, so the client is rebuilt.
    fake.ping_error = None
    clock.advance(settings.CACHE_UNAVAILABLE_COOLDOWN + 1)
    assert await svc._is_available() is True
    assert svc._redis is fake


@pytest.mark.asyncio
async def test_disconnect_drops_the_pool_so_rebuild_cannot_resurrect_it(
    service, monkeypatch
):
    """An explicit shutdown must not be undone by the health re-probe."""
    svc, fake = service

    class FakePool:
        async def disconnect(self):
            return None

    svc._pool = FakePool()  # type: ignore[assignment]
    svc._owns_pool = True

    await svc.disconnect()

    assert svc._redis is None
    assert svc._pool is None
    assert await svc._is_available() is False


@pytest.mark.asyncio
async def test_disabled_by_configuration_never_probes(clock):
    """CACHE_ENABLED=false must short-circuit before touching Redis."""
    svc = AsyncCacheService()
    svc._enabled = False
    fake = FakeRedis()
    svc._redis = fake  # type: ignore[assignment]

    assert await svc._is_available() is False
    assert fake.ping_calls == 0


@pytest.mark.asyncio
async def test_set_redis_clears_a_previous_cooldown(service, clock):
    """Re-injecting a healthy shared client resumes caching immediately."""
    svc, fake = service
    fake.ping_error = redis.ConnectionError("refused")
    assert await svc.get_user("u1") is None
    assert svc._unavailable_until > clock.now

    fresh = FakeRedis()
    svc.set_redis(fresh)  # type: ignore[arg-type]

    assert svc._unavailable_until == 0.0
    assert await svc._is_available() is True
