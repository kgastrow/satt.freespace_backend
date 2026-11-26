"""
Redis access for Freespace services.

One accessor so every Freespace module reaches Redis the same way and tests
can inject a fake with one call. Resolution order:

1. an override set with ``set_redis_override`` (tests),
2. the shared API pool (``redis_pool_manager.client_db0``),
3. the cache service's client (the ARQ worker connects that one at startup).

Every caller must treat ``None`` and any ``RedisError`` as "Redis unavailable"
and degrade (fail open), never fail the request: the Freespace caches and the
mock clock offset are conveniences, the database is the source of truth.
"""

from __future__ import annotations

from typing import Any


_override: Any = None


def set_redis_override(client: Any) -> None:
    """Use ``client`` (an async Redis-compatible object) for all Freespace
    Redis access; ``None`` restores normal resolution. Tests only."""
    global _override
    _override = client


def get_redis() -> Any:
    """Return an async Redis client, or ``None`` when none is available.

    Typed ``Any`` because callers may receive ``redis.asyncio.Redis`` or a
    fakeredis equivalent; both expose ``get``/``set``/``setex``/``delete``/
    ``incr``/``expire``/``ttl``.
    """
    if _override is not None:
        return _override

    from src.core.redis_pool import redis_pool_manager

    if redis_pool_manager.client_db0 is not None:
        return redis_pool_manager.client_db0

    from src.services.cache import cache_service

    return cache_service._redis
