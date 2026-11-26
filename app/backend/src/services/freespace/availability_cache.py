"""
5 s Redis cache of the app availability response (BF-32). OWNER: M4.

The cached entry records when (Freespace clock) it was computed. It is served
only while ``0 <= now - computed_at < AVAILABILITY_CACHE_MAX_AGE_S`` on the
SAME clock, so ``ageSeconds`` / ``stale`` are never more than 5 s out of date,
also under the mock clock (which can jump forward or back) where the Redis
TTL alone would not be enough. The Redis TTL only bounds memory.

Fails open: no Redis or any Redis error = cache miss / no-op.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

from src.constants.freespace import (
    AVAILABILITY_CACHE_MAX_AGE_S,
    REDIS_AVAILABILITY_KEY_FMT,
)
from src.logger.logger import Logger as logger
from src.services.freespace.clock import ensure_utc
from src.services.freespace.redis_client import get_redis


def cache_key(site_slug: str) -> str:
    return REDIS_AVAILABILITY_KEY_FMT.format(slug=site_slug)


async def get_cached_availability(
    site_slug: str, now: datetime
) -> dict[str, Any] | None:
    """The cached wire body, or None (miss, too old for ``now``, or no Redis)."""
    redis = get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(cache_key(site_slug))
        if raw is None:
            return None
        entry = json.loads(raw)
        computed_at = ensure_utc(datetime.fromisoformat(entry["computed_at"]))
        age = now - computed_at
        if age < timedelta(0) or age >= timedelta(seconds=AVAILABILITY_CACHE_MAX_AGE_S):
            return None
        body = entry["body"]
        return body if isinstance(body, dict) else None
    except Exception as exc:  # fail open
        logger.debug(f"Freespace availability cache read failed: {exc}")
        return None


async def set_cached_availability(
    site_slug: str, now: datetime, body: dict[str, Any]
) -> None:
    """Store the wire body computed at ``now`` for at most 5 s."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.setex(
            cache_key(site_slug),
            AVAILABILITY_CACHE_MAX_AGE_S,
            json.dumps({"computed_at": now.isoformat(), "body": body}),
        )
    except Exception as exc:  # fail open
        logger.debug(f"Freespace availability cache write failed: {exc}")


async def invalidate_availability_cache(site_slug: str) -> None:
    """Drop the cached body of a site (optional for writers: e.g. after a site
    is unlisted or deleted; snapshots may simply age out within 5 s)."""
    redis = get_redis()
    if redis is None:
        return
    try:
        await redis.delete(cache_key(site_slug))
    except Exception as exc:  # fail open
        logger.debug(f"Freespace availability cache delete failed: {exc}")
