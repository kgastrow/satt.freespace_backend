"""Review round 2, ingest findings.

F5: failed ingest authentications are limited per client IP (429
``ingest.rate_limited`` with ``Retry-After``, no rejection write), and the
rejection sorted set is trimmed/capped on write.
F6: the per-key sliding window is atomic, so concurrent submissions cannot
overshoot the limit.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import uuid

import pytest

from src.core.config import settings
from src.services.freespace import alerts
from src.services.freespace.alerts import (
    REDIS_REJECTION_KEY_PREFIX,
    UNKNOWN_KEY_ID,
    record_ingest_rejection,
)
from src.services.freespace.ingest_rate_limit import (
    REDIS_INGEST_AUTH_FAIL_KEY_FMT,
    auth_failure_limit,
    enforce_ingest_rate_limit,
    parse_limit,
    sliding_window_hit,
)


PING = "/v1/ingest/ping"
BAD = {"Authorization": "Bearer not-a-valid-key"}
UNKNOWN_SET = REDIS_REJECTION_KEY_PREFIX + UNKNOWN_KEY_ID


def _fail_key(ip: str = "127.0.0.1") -> str:
    return REDIS_INGEST_AUTH_FAIL_KEY_FMT.format(ip=ip)


# ─────────────────────────────────────────────────────────────
# F5: per-IP limit on failed ingest authentication
# ─────────────────────────────────────────────────────────────


class TestAuthFailureLimit:
    def test_default_is_30_per_minute(self):
        assert settings.RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES == "30/minute"
        assert auth_failure_limit() == (30, 60)

    async def test_failures_over_budget_get_429_and_no_rejection_write(
        self, client, fs_redis, monkeypatch
    ):
        monkeypatch.setattr(
            settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", "3/minute"
        )
        for _ in range(3):
            assert (await client.get(PING, headers=BAD)).status_code == 401
        assert await fs_redis.zcard(UNKNOWN_SET) == 3

        r = await client.get(PING, headers=BAD)
        assert r.status_code == 429
        assert r.json()["detail_code"] == "ingest.rate_limited"
        assert "detail" in r.json()
        retry = int(r.headers["Retry-After"])
        assert 1 <= retry <= 60
        # Over-budget attempts are not recorded for the alert.
        assert await fs_redis.zcard(UNKNOWN_SET) == 3

        # Missing header is limited too.
        assert (await client.get(PING)).status_code == 429

    async def test_authenticated_requests_unaffected(
        self, client, fs_ingest_headers, monkeypatch
    ):
        monkeypatch.setattr(
            settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", "2/minute"
        )
        for _ in range(3):
            await client.get(PING, headers=BAD)
        assert (await client.get(PING, headers=BAD)).status_code == 429
        # Same IP, valid key: still served.
        for _ in range(5):
            assert (
                await client.get(PING, headers=fs_ingest_headers)
            ).status_code == 200

    async def test_window_slides_with_clock(self, client, fixed_clock, monkeypatch):
        monkeypatch.setattr(
            settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", "2/minute"
        )
        for _ in range(2):
            assert (await client.get(PING, headers=BAD)).status_code == 401
        assert (await client.get(PING, headers=BAD)).status_code == 429
        fixed_clock.advance(61)
        assert (await client.get(PING, headers=BAD)).status_code == 401

    async def test_keyed_per_ip(self, client, async_session, fs_redis, monkeypatch):
        from httpx import ASGITransport, AsyncClient

        from main import app

        monkeypatch.setattr(
            settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", "2/minute"
        )
        for _ in range(2):
            await client.get(PING, headers=BAD)
        assert (await client.get(PING, headers=BAD)).status_code == 429
        # Another peer address has its own budget (``client`` fixture keeps
        # the session override installed on ``app``).
        transport = ASGITransport(app=app, client=("10.9.9.9", 4321))
        async with AsyncClient(transport=transport, base_url="http://test") as other:
            assert (await other.get(PING, headers=BAD)).status_code == 401
        assert await fs_redis.zcard(_fail_key("10.9.9.9")) == 1

    async def test_fails_open_on_redis_error(self, client, fs_redis, monkeypatch):
        monkeypatch.setattr(
            settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", "1/minute"
        )

        async def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(fs_redis, "eval", boom)
        for _ in range(5):
            assert (await client.get(PING, headers=BAD)).status_code == 401


# ─────────────────────────────────────────────────────────────
# F5b: rejection set is bounded on write
# ─────────────────────────────────────────────────────────────


class TestRejectionSetBounded:
    async def test_capped_between_ticks(self, fs_redis, fixed_clock, monkeypatch):
        monkeypatch.setattr(alerts, "REJECTION_COUNTER_MAX_ENTRIES", 5)
        for _ in range(20):
            await record_ingest_rejection(None, fixed_clock.now())
        assert await fs_redis.zcard(UNKNOWN_SET) == 5

    async def test_old_entries_trimmed_on_write(self, fs_redis, fixed_clock):
        for _ in range(4):
            await record_ingest_rejection(None, fixed_clock.now())
        fixed_clock.advance(120)
        await record_ingest_rejection(None, fixed_clock.now())
        assert await fs_redis.zcard(UNKNOWN_SET) == 1
        assert await fs_redis.ttl(UNKNOWN_SET) > 0


# ─────────────────────────────────────────────────────────────
# F6: atomic per-key window
# ─────────────────────────────────────────────────────────────


class TestAtomicWindow:
    async def test_helper_concurrent_hits_respect_limit(self, fs_redis, fixed_clock):
        now = fixed_clock.now().timestamp()
        results = await asyncio.gather(
            *(
                sliding_window_hit(fs_redis, "fs:test:win", now, 12, 60)
                for _ in range(40)
            )
        )
        assert sum(1 for ok, _ in results if ok) == 12
        assert all(1 <= retry <= 60 for ok, retry in results if not ok)
        assert await fs_redis.zcard("fs:test:win") == 12

    async def test_enforce_concurrent_submissions(self, fs_redis, fixed_clock):
        limit, _ = parse_limit(settings.RATE_LIMIT_FREESPACE_INGEST)
        auth = SimpleNamespace(key=SimpleNamespace(id=uuid.uuid4()))
        results = await asyncio.gather(
            *(enforce_ingest_rate_limit(auth, fixed_clock) for _ in range(limit + 20)),
            return_exceptions=True,
        )
        passed = [r for r in results if r is auth]
        limited = [r for r in results if getattr(r, "status_code", None) == 429]
        assert len(passed) == limit
        assert len(limited) == 20
        assert all(1 <= int(e.headers["Retry-After"]) <= 600 for e in limited)
        # Each 429 is counted for the BF-82 alert under the key id.
        key_set = REDIS_REJECTION_KEY_PREFIX + str(auth.key.id)
        assert await fs_redis.zcard(key_set) == 20

    async def test_fails_open_on_redis_error(self, fs_redis, fixed_clock, monkeypatch):
        async def boom(*a, **k):
            raise ConnectionError("down")

        monkeypatch.setattr(fs_redis, "eval", boom)
        auth = SimpleNamespace(key=SimpleNamespace(id=uuid.uuid4()))
        for _ in range(20):
            assert await enforce_ingest_rate_limit(auth, fixed_clock) is auth


@pytest.mark.parametrize("spec", ["", "garbage"])
def test_bad_override_falls_back(spec, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES", spec)
    assert auth_failure_limit() == (30, 60)
