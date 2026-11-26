"""
Redis connection pool stress tests.

Drives the websocket-side Redis code paths (RedisRegistry + RedisPubSub)
against a deliberately undersized connection pool so that any leaked
checkout becomes observable. The tests are written to FAIL if a regression
reintroduces a connection leak, and PASS when cleanup is correct.

Failure modes these tests are designed to catch:
- pipe.execute() error paths that don't release the checked-out connection
- pubsub cleanup that leaves the dedicated connection checked out
- sustained concurrent load slowly draining the pool

Uses fakeredis.aioredis which is backed by a real redis.asyncio
ConnectionPool, so max_connections is enforced at the pool layer and
_in_use_connections reflects genuine leaks, not fakeredis quirks.
"""

import asyncio
from uuid import uuid4

import fakeredis.aioredis
import pytest
import redis.asyncio as redis
from redis.asyncio import BlockingConnectionPool, Redis


POOL_SIZE = 5
HIGH_CONCURRENCY = 200
STRESS_DEADLINE_SECONDS = 10.0
# Per-acquire timeout for the blocking pool. A leaked connection will
# manifest as an acquisition that waits this long then raises.
POOL_ACQUIRE_TIMEOUT = 2.0


@pytest.fixture
def bounded_redis(monkeypatch):
    """
    Yield a fakeredis client backed by a BlockingConnectionPool and wired
    into cache_service.

    RedisRegistry fetches its client via `cache_service._redis`, so injecting
    here exercises the production code path. The pool is intentionally small
    to make any leak observable within a small number of operations.

    BlockingConnectionPool is used so that a leak manifests as a hang
    (caught by asyncio.wait_for) rather than an immediate ConnectionError
    — matching how a leak presents in production where requests stack up.
    """
    from src.services.cache import cache_service

    pool = BlockingConnectionPool(
        connection_class=fakeredis.aioredis.FakeConnection,
        max_connections=POOL_SIZE,
        timeout=POOL_ACQUIRE_TIMEOUT,
        decode_responses=True,
    )
    client = Redis(connection_pool=pool)

    original = cache_service._redis
    cache_service._redis = client
    try:
        yield client
    finally:
        cache_service._redis = original


def _in_use(client: redis.Redis) -> int:
    """Number of connections currently checked out from the pool."""
    return len(client.connection_pool._in_use_connections)


async def _assert_pool_drains(client: redis.Redis, timeout: float = 2.0) -> None:
    """
    Wait briefly for checkouts to return, then assert the pool is idle.

    A short grace period absorbs legitimate in-flight operations;
    after that any remaining checkout is a leak.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    while _in_use(client) > 0 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert _in_use(client) == 0, (
        f"Leak detected: {_in_use(client)} connection(s) still checked out "
        f"after all operations completed"
    )


class TestRedisRegistryPoolStress:
    """Stress RedisRegistry under concurrency with a tiny pool."""

    @pytest.mark.asyncio
    async def test_bounded_pool_is_actually_enforced(self, bounded_redis):
        """Sanity check: the small pool really does cap checkouts.

        If this test fails, the other leak-detection tests cannot be trusted
        because the pool wouldn't be bounded in the first place.
        """
        held = []
        for _ in range(POOL_SIZE):
            conn = await bounded_redis.connection_pool.get_connection("_")
            held.append(conn)

        assert _in_use(bounded_redis) == POOL_SIZE

        # The next acquisition must block. Cancel it fast enough that the
        # pool's own acquire-timeout doesn't fire first — we want to prove
        # the pool is waiting, not that it gave up.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                bounded_redis.connection_pool.get_connection("_"),
                timeout=0.3,
            )

        for conn in held:
            await bounded_redis.connection_pool.release(conn)

    @pytest.mark.asyncio
    async def test_concurrent_register_unregister_does_not_leak(
        self, bounded_redis
    ):
        """
        HIGH_CONCURRENCY register+unregister cycles against a POOL_SIZE pool.

        If pipe.execute() — or any surrounding code — leaks a connection per
        call, the pool is drained long before all tasks finish and the gather
        hangs until the deadline. Passes when every connection is released.
        """
        from src.services.websocket.redis_registry import RedisRegistry

        registry = RedisRegistry()
        worker_id = f"stress-worker-{uuid4()}"

        async def cycle() -> None:
            connection_id = str(uuid4())
            user_id = uuid4()
            org_id = uuid4()
            registered = await registry.register_connection(
                connection_id=connection_id,
                user_id=user_id,
                organization_id=org_id,
                worker_id=worker_id,
            )
            assert registered is True
            unregistered = await registry.unregister_connection(connection_id)
            assert unregistered is True

        await asyncio.wait_for(
            asyncio.gather(*[cycle() for _ in range(HIGH_CONCURRENCY)]),
            timeout=STRESS_DEADLINE_SECONDS,
        )

        await _assert_pool_drains(bounded_redis)

    @pytest.mark.asyncio
    async def test_pipeline_execute_failure_releases_connection(
        self, bounded_redis, monkeypatch
    ):
        """
        Force pipe.execute() to raise on every call and verify the pool
        stays healthy. This targets the exact failure mode the investigation
        flagged: an error path that doesn't release its checkout.

        We invoke the registry enough times that a one-connection-per-call
        leak would exhaust the pool several times over.
        """
        from src.services.websocket.redis_registry import RedisRegistry

        registry = RedisRegistry()

        original_pipeline = bounded_redis.pipeline

        def pipeline_with_failing_execute(*args, **kwargs):
            pipe = original_pipeline(*args, **kwargs)
            original_execute = pipe.execute

            async def failing_execute(*a, **kw):
                # Run the real execute first so a connection is actually
                # acquired inside pipeline internals — otherwise we'd only
                # be testing the trivial "no checkout ever happened" path.
                await original_execute(*a, **kw)
                raise redis.RedisError("injected failure after execute")

            pipe.execute = failing_execute
            return pipe

        monkeypatch.setattr(
            bounded_redis, "pipeline", pipeline_with_failing_execute
        )

        # 50 failures through a 5-connection pool: even a small leak
        # percentage would exhaust the pool. All calls must return False
        # (registry swallows RedisError) without leaking.
        for _ in range(50):
            result = await registry.register_connection(
                connection_id=str(uuid4()),
                user_id=uuid4(),
                organization_id=uuid4(),
                worker_id="fail-test-worker",
            )
            assert result is False

        await _assert_pool_drains(bounded_redis)

        # The pool is not merely "counted as empty" — it still works.
        async with asyncio.timeout(1.0):
            pong = await bounded_redis.ping()
        assert pong is True


class TestRedisPubSubCleanup:
    """Verify pub/sub teardown actually releases its dedicated connection."""

    @pytest.mark.asyncio
    async def test_aclose_releases_pubsub_connection(self, bounded_redis):
        """
        PubSub holds one dedicated connection from the moment it subscribes.
        `aclose()` must return that connection to the pool.

        Regression guard: if someone swaps `aclose()` back for a bare
        `unsubscribe()` (which does not close the underlying connection),
        this test catches it.
        """
        pubsub = bounded_redis.pubsub()
        await pubsub.subscribe("test-channel")

        assert _in_use(bounded_redis) >= 1, (
            "PubSub subscribe should hold at least one connection"
        )

        await pubsub.aclose()

        await _assert_pool_drains(bounded_redis)

    @pytest.mark.asyncio
    async def test_unsubscribe_alone_does_not_release_connection(
        self, bounded_redis
    ):
        """
        Document the exact redis-py behaviour that motivated the aclose() fix:
        `unsubscribe()` with no args stops message delivery but keeps the
        dedicated connection checked out. This test will need updating if
        redis-py ever changes that contract.
        """
        pubsub = bounded_redis.pubsub()
        await pubsub.subscribe("test-channel")
        assert _in_use(bounded_redis) >= 1

        await pubsub.unsubscribe()

        # Give any async cleanup a moment; connection should STILL be held.
        await asyncio.sleep(0.05)
        assert _in_use(bounded_redis) >= 1, (
            "Expected unsubscribe() alone to keep the connection checked out; "
            "if redis-py changed this, the aclose() fix may no longer be "
            "strictly necessary and this test should be revisited."
        )

        # Clean up properly so the fixture teardown is clean.
        await pubsub.aclose()

    @pytest.mark.asyncio
    async def test_broken_cleanup_pattern_exhausts_the_pool(self, bounded_redis):
        """
        Reproduction of the production failure mode.

        Using the broken cleanup pattern (`unsubscribe()` with no args, no
        `aclose()`) POOL_SIZE + 1 times must exhaust the pool, because every
        cycle leaks one connection and none are ever returned. The final
        acquisition blocks until the pool's acquire-timeout fires and then
        raises ConnectionError.

        This test PASSES when the broken pattern is broken — i.e. it proves
        exhaustion is reproducible. If redis-py ever starts releasing the
        connection on bare unsubscribe(), this will fail and the fix in
        redis_pubsub.py becomes unnecessary.
        """
        leaked = []
        for i in range(POOL_SIZE):
            pubsub = bounded_redis.pubsub()
            await pubsub.subscribe(f"leak-{i}")
            await pubsub.unsubscribe()  # the bug: does not release the conn
            leaked.append(pubsub)  # keep refs so GC can't mask the leak

        assert _in_use(bounded_redis) == POOL_SIZE, (
            "Expected every leaked pubsub to still hold a connection"
        )

        # Pool is now drained. Any fresh operation must hit the blocking
        # timeout and raise ConnectionError — that IS pool exhaustion.
        with pytest.raises(redis.ConnectionError):
            await bounded_redis.ping()

        # Clean up properly so the fixture teardown doesn't warn.
        for pubsub in leaked:
            await pubsub.aclose()

    @pytest.mark.asyncio
    async def test_many_pubsub_lifecycle_cycles_do_not_exhaust_pool(
        self, bounded_redis
    ):
        """
        Repeatedly subscribe+aclose more times than the pool has slots.
        If any cycle leaks, the Nth subscribe blocks forever on get_connection.
        """
        cycles = POOL_SIZE * 10

        async def cycle(i: int) -> None:
            pubsub = bounded_redis.pubsub()
            await pubsub.subscribe(f"channel-{i}")
            await pubsub.aclose()

        await asyncio.wait_for(
            asyncio.gather(*[cycle(i) for i in range(cycles)]),
            timeout=STRESS_DEADLINE_SECONDS,
        )

        await _assert_pool_drains(bounded_redis)
