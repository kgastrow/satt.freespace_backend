"""
Per-ingest-key rate limit for intake (BF-18, D3). OWNER: M2.

``enforce_ingest_rate_limit`` is a FastAPI dependency that composes with
``get_ingest_site``: it authenticates through that dependency, then counts the
request in a Redis sliding window (sorted set) keyed by ingest key id
(``REDIS_INGEST_RATE_KEY_FMT``). Over the limit (``settings.RATE_LIMIT_FREESPACE_INGEST``,
default 12/minute) it raises 429 ``ingest.rate_limited`` with ``Retry-After``
as a whole number of seconds clamped to 1-600. Rejected requests are not
counted. The trim/count/add runs as one Lua script so concurrent requests
cannot overshoot the limit. Fails open when Redis is unavailable, like the
template limiter.

``check_auth_failure_limit`` applies the same window per client IP to FAILED
ingest authentications (default 30/minute): ``get_ingest_site`` answers 429
instead of 401 once an IP is over it.
"""

from __future__ import annotations

from datetime import datetime
import math
import re
from typing import Annotated, Any, Final
import uuid

from fastapi import Depends, HTTPException, status

from src.api.freespace_deps import IngestAuth, get_ingest_site
from src.constants.freespace import REDIS_INGEST_RATE_KEY_FMT
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger as logger
from src.services.freespace.alerts import record_ingest_rejection
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.redis_client import get_redis


RETRY_AFTER_MIN_S = 1
RETRY_AFTER_MAX_S = 600
_PERIOD_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_DEFAULT_LIMIT = (12, 60)

# Review F5: unauthenticated ingest requests are otherwise unlimited (both
# routes are ``limiter.exempt``). Configured by
# ``settings.RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES``.
_DEFAULT_AUTH_FAILURE_PARSED: Final = (30, 60)
REDIS_INGEST_AUTH_FAIL_KEY_FMT: Final = "freespace:ingest_auth_fail:{ip}"


def parse_limit(
    spec: str, default: tuple[int, int] = _DEFAULT_LIMIT
) -> tuple[int, int]:
    """``"12/minute"`` -> ``(12, 60)``; falls back to ``default`` (12/minute)
    if malformed."""
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d*)\s*(second|minute|hour|day)s?\s*", spec)
    if not match:
        return default
    count = int(match.group(1))
    multiple = int(match.group(2) or 1)
    if count < 1 or multiple < 1:
        return default
    return count, multiple * _PERIOD_SECONDS[match.group(3)]


def clamp_retry_after(seconds: float) -> int:
    """Whole seconds, rounded up, clamped to 1-600 (BF-18)."""
    if not math.isfinite(seconds):
        return 60
    return max(RETRY_AFTER_MIN_S, min(RETRY_AFTER_MAX_S, math.ceil(seconds)))


# Trim + count + add in ONE server-side step, so concurrent submissions cannot
# all pass the count check (review F6). Returns {1, "0"} when the hit was
# counted, {0, "<seconds until a slot frees>"} when over the limit (not
# counted). Floats travel as strings: Lua numbers are truncated to integers in
# Redis replies.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = window
  if oldest[2] then retry = tonumber(oldest[2]) + window - now end
  return {0, tostring(retry)}
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('EXPIRE', key, window + 1)
return {1, '0'}
"""


async def sliding_window_hit(
    redis: Any, key: str, now: float, limit: int, window: int
) -> tuple[bool, int]:
    """Atomically count one hit in the sorted-set window ``key``.

    Returns ``(allowed, retry_after_s)``. A refused hit is not counted.
    Raises whatever the Redis client raises (callers fail open)."""
    allowed, retry = await redis.eval(
        _SLIDING_WINDOW_LUA, 1, key, now, window, limit, f"{now}:{uuid.uuid4().hex}"
    )
    if int(allowed):
        return True, 0
    if isinstance(retry, bytes):
        retry = retry.decode()
    try:
        seconds = float(retry)
    except (TypeError, ValueError):
        seconds = float(window)
    return False, clamp_retry_after(seconds)


def _rate_limited(retry_after: int) -> HTTPException:
    return create_http_exception(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Ingest rate limit exceeded",
        detail_code="ingest.rate_limited",
        headers={"Retry-After": str(retry_after)},
    )


def auth_failure_limit() -> tuple[int, int]:
    """Per-IP budget of FAILED ingest authentications (review F5).

    Read from ``settings.RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES`` at call
    time; an unparseable value falls back to 30/minute."""
    return parse_limit(
        settings.RATE_LIMIT_FREESPACE_INGEST_AUTH_FAILURES,
        default=_DEFAULT_AUTH_FAILURE_PARSED,
    )


async def check_auth_failure_limit(client_ip: str | None, moment: datetime) -> None:
    """Count one failed ingest authentication for ``client_ip``.

    Raises 429 ``ingest.rate_limited`` (with ``Retry-After``) once the IP is
    over its failure budget; the caller must then skip the rejection write.
    Only failures are counted, so authenticated requests are never affected.
    Fails open when Redis is unavailable."""
    redis = get_redis()
    if redis is None:
        return
    limit, window = auth_failure_limit()
    key = REDIS_INGEST_AUTH_FAIL_KEY_FMT.format(ip=client_ip or "unknown")
    try:
        allowed, retry_after = await sliding_window_hit(
            redis, key, moment.timestamp(), limit, window
        )
    except Exception as exc:
        logger.warning(
            f"Freespace ingest auth-failure limit unavailable: {type(exc).__name__}"
        )
        return
    if not allowed:
        raise _rate_limited(retry_after)


async def enforce_ingest_rate_limit(
    auth: Annotated[IngestAuth, Depends(get_ingest_site)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> IngestAuth:
    """Authenticate the ingest key, then enforce its submission budget.

    Use in place of ``get_ingest_site``:
    ``auth: Annotated[IngestAuth, Depends(enforce_ingest_rate_limit)]``.
    """
    redis = get_redis()
    if redis is None:
        return auth
    limit, window = parse_limit(settings.RATE_LIMIT_FREESPACE_INGEST)
    key = REDIS_INGEST_RATE_KEY_FMT.format(key_id=auth.key.id)
    moment = clock.now()
    try:
        allowed, retry_after = await sliding_window_hit(
            redis, key, moment.timestamp(), limit, window
        )
    except Exception as exc:
        logger.warning(f"Freespace ingest rate limit unavailable: {type(exc).__name__}")
        return auth
    if not allowed:
        # 429s write no site_event: count them for the BF-82 alert.
        await record_ingest_rejection(auth.key.id, moment)
        raise _rate_limited(retry_after)
    return auth
