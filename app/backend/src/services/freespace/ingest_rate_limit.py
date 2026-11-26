"""
Per-ingest-key rate limit for intake (BF-18, D3). OWNER: M2.

``enforce_ingest_rate_limit`` is a FastAPI dependency that composes with
``get_ingest_site``: it authenticates through that dependency, then counts the
request in a Redis sliding window (sorted set) keyed by ingest key id
(``REDIS_INGEST_RATE_KEY_FMT``). Over the limit (``settings.RATE_LIMIT_FREESPACE_INGEST``,
default 12/minute) it raises 429 ``ingest.rate_limited`` with ``Retry-After``
as a whole number of seconds clamped to 1-600. Rejected requests are not
counted. Fails open when Redis is unavailable, like the template limiter.
"""

from __future__ import annotations

import math
import re
from typing import Annotated
import uuid

from fastapi import Depends, status

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


def parse_limit(spec: str) -> tuple[int, int]:
    """``"12/minute"`` -> ``(12, 60)``; falls back to 12/minute if malformed."""
    match = re.fullmatch(r"\s*(\d+)\s*/\s*(\d*)\s*(second|minute|hour|day)s?\s*", spec)
    if not match:
        return _DEFAULT_LIMIT
    count = int(match.group(1))
    multiple = int(match.group(2) or 1)
    if count < 1 or multiple < 1:
        return _DEFAULT_LIMIT
    return count, multiple * _PERIOD_SECONDS[match.group(3)]


def clamp_retry_after(seconds: float) -> int:
    """Whole seconds, rounded up, clamped to 1-600 (BF-18)."""
    if not math.isfinite(seconds):
        return 60
    return max(RETRY_AFTER_MIN_S, min(RETRY_AFTER_MAX_S, math.ceil(seconds)))


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
    now = moment.timestamp()
    try:
        await redis.zremrangebyscore(key, "-inf", now - window)
        count = await redis.zcard(key)
        if count >= limit:
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            retry = (oldest[0][1] + window - now) if oldest else window
            retry_after = clamp_retry_after(retry)
            # 429s write no site_event: count them for the BF-82 alert.
            await record_ingest_rejection(auth.key.id, moment)
            raise create_http_exception(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Ingest rate limit exceeded",
                detail_code="ingest.rate_limited",
                headers={"Retry-After": str(retry_after)},
            )
        await redis.zadd(key, {f"{now}:{uuid.uuid4().hex}": now})
        await redis.expire(key, window + 1)
    except Exception as exc:
        if getattr(exc, "status_code", None) == status.HTTP_429_TOO_MANY_REQUESTS:
            raise
        logger.warning(f"Freespace ingest rate limit unavailable: {type(exc).__name__}")
    return auth
