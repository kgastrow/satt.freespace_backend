"""
Async Redis caching service for FastAPI.
Provides JWT claim caching, user/org/role caching with automatic invalidation.
"""

import asyncio
import hashlib
import json
import time
from typing import Any, Optional

import redis.asyncio as redis

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.middleware.cache_metrics import (
    record_cache_delete,
    record_cache_error,
    record_cache_hit,
    record_cache_miss,
    record_cache_set,
    update_cache_connection_status,
    update_cache_memory,
)


class AsyncCacheService:
    """
    Async Redis-based caching service.
    Uses redis.asyncio for non-blocking operations.
    Gracefully degrades to no-cache when Redis is unavailable.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None
        self._owns_pool = False  # Whether we created the pool ourselves
        # Configuration switch only. This is never flipped at runtime: a Redis
        # blip must not disable caching for the life of the process.
        self._enabled = settings.CACHE_ENABLED
        # Runtime health. A Redis error marks the backend unavailable until
        # this monotonic deadline; the first call afterwards re-probes and, on
        # success, caching resumes. Zero means "believed healthy".
        self._unavailable_until: float = 0.0

    def set_redis(self, client: redis.Redis) -> None:
        """
        Inject a shared Redis client from RedisPoolManager.

        This is the preferred initialization path. The pool is owned
        and closed by RedisPoolManager, not by this service.
        """
        if not self._enabled:
            logger.info("Cache disabled by configuration")
            update_cache_connection_status(False)
            return
        self._redis = client
        self._owns_pool = False
        self._unavailable_until = 0.0
        update_cache_connection_status(True)
        logger.info("Cache service using shared Redis pool")

    async def connect(self) -> None:
        """
        Initialize with own Redis pool (fallback for standalone/test use).

        Prefer set_redis() with a shared pool from RedisPoolManager.
        """
        if not self._enabled:
            logger.info("Cache disabled by configuration")
            update_cache_connection_status(False)
            return

        # Skip if already initialized via set_redis()
        if self._redis is not None:
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=settings.REDIS_POOL_SIZE,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            self._owns_pool = True

            # Test connection
            await self._redis.ping()
            logger.info("Async Redis cache connection established (own pool)")
            update_cache_connection_status(True)

            # Update memory metrics
            try:
                info = await self._redis.info("memory")
                update_cache_memory(info.get("used_memory", 0))
            except Exception:
                pass

        except (redis.RedisError, OSError, asyncio.TimeoutError) as e:
            # Do not disable the cache: keep the pool so that the next call
            # past the cooldown rebuilds the client and re-probes.
            self._redis = None
            self._mark_unavailable(e, "connect")

    async def disconnect(self) -> None:
        """Close Redis connection pool if we own it."""
        if self._owns_pool and self._pool:
            await self._pool.disconnect()
            logger.info("Redis connection pool closed")
            # Drop the pool too, so the health re-probe cannot rebuild a
            # client on top of a pool we deliberately tore down.
            self._pool = None
            self._owns_pool = False
        self._redis = None
        update_cache_connection_status(False)

    # ==================== Backend health ====================

    @property
    def _cooldown_seconds(self) -> float:
        """Seconds to stay unavailable after a Redis error before re-probing."""
        return max(1.0, float(settings.CACHE_UNAVAILABLE_COOLDOWN))

    def _mark_unavailable(self, exc: BaseException, op: str) -> None:
        """
        Mark the Redis backend unavailable for a short cooldown.

        Callers fall open and serve from the database in the meantime. The
        cooldown expires on its own, so a transient blip cannot latch caching
        off permanently (which is what ``self._enabled = False`` used to do).
        """
        now = time.monotonic()
        first_failure = now >= self._unavailable_until
        self._unavailable_until = now + self._cooldown_seconds
        if first_failure:
            update_cache_connection_status(False)
            logger.warning(
                f"Redis unavailable during {op}; caching paused for "
                f"{self._cooldown_seconds:.0f}s: {exc}"
            )

    def _mark_available(self) -> None:
        """Clear the cooldown after a successful probe."""
        if self._unavailable_until:
            self._unavailable_until = 0.0
            update_cache_connection_status(True)
            logger.info("Redis reachable again, caching resumed")

    def _note_operation_error(self, exc: BaseException, op: str) -> None:
        """
        Record a per-operation failure.

        A ``RedisError`` (which covers ``ConnectionError`` and ``TimeoutError``)
        means the backend is in trouble, so start a cooldown rather than paying
        a socket timeout on every subsequent request. Decode errors are bad
        payloads, not a sick backend, and are ignored here.
        """
        if isinstance(exc, (redis.RedisError, OSError, asyncio.TimeoutError)):
            self._mark_unavailable(exc, op)

    def _rebuild_client(self) -> bool:
        """Recreate our own client from the pool after a failed connect()."""
        if self._pool is None:
            return False
        self._redis = redis.Redis(connection_pool=self._pool)
        self._owns_pool = True
        return True

    async def _is_available(self) -> bool:
        """
        Check if Redis is available.

        Fails open (returns False, never raises) so that callers degrade to the
        database instead of surfacing a Redis error to the request handler.
        """
        if not self._enabled:
            return False
        if time.monotonic() < self._unavailable_until:
            return False
        if self._redis is None and not self._rebuild_client():
            return False
        assert self._redis is not None
        try:
            await self._redis.ping()
        except (redis.RedisError, OSError, asyncio.TimeoutError) as e:
            self._mark_unavailable(e, "ping")
            return False
        self._mark_available()
        return True

    # ==================== JWT/Session Caching ====================

    def hash_token(self, token: str) -> str:
        """Create a hash of the JWT token for use as cache key."""
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    async def get_jwt_claims(self, token: str) -> Optional[dict[str, Any]]:
        """
        Get cached JWT claims including user context.
        Returns None on cache miss or Redis unavailable.
        """
        if not await self._is_available():
            return None
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"jwt:{self.hash_token(token)}"
            data = await self._redis.get(key)
            duration = time.time() - start_time
            if data:
                record_cache_hit("jwt", "get_jwt_claims", duration)
                return json.loads(data)
            record_cache_miss("jwt", "get_jwt_claims", duration)
            return None
        except (redis.RedisError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_jwt_claims error: {e}")
            record_cache_error("jwt", "get_jwt_claims")
            self._note_operation_error(e, "get_jwt_claims")
            return None

    async def set_jwt_claims(
        self,
        token: str,
        claims: dict[str, Any],
        token_exp: int,
    ) -> bool:
        """
        Cache JWT claims with user context.
        TTL is minimum of (token expiry - now) or configured max.
        """
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"jwt:{self.hash_token(token)}"
            ttl = min(token_exp - int(time.time()), settings.CACHE_JWT_TTL)
            if ttl <= 0:
                return False

            await self._redis.setex(key, ttl, json.dumps(claims))

            # Track for invalidation
            user_id = claims.get("user_id")
            if user_id:
                await self._redis.sadd(f"inv:user:{user_id}", key)  # type: ignore[misc]

            record_cache_set("jwt", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache set_jwt_claims error: {e}")
            record_cache_error("jwt", "set_jwt_claims")
            self._note_operation_error(e, "set_jwt_claims")
            return False

    async def invalidate_jwt_for_user(self, user_id: str) -> int:
        """Invalidate all cached JWT claims for a user."""
        if not await self._is_available():
            return 0
        assert self._redis is not None

        start_time = time.time()
        try:
            inv_key = f"inv:user:{user_id}"
            keys = await self._redis.smembers(inv_key)  # type: ignore[misc]
            if keys:
                await self._redis.delete(*keys, inv_key)
                record_cache_delete("jwt", time.time() - start_time)
                return len(keys)
            return 0
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_jwt error: {e}")
            record_cache_error("jwt", "invalidate_jwt_for_user")
            self._note_operation_error(e, "invalidate_jwt_for_user")
            return 0

    # ==================== Organization Caching ====================

    async def get_organization(self, org_id: str) -> Optional[dict[str, Any]]:
        """Get cached organization data."""
        if not await self._is_available():
            return None
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"org:{org_id}"
            data = await self._redis.get(key)
            duration = time.time() - start_time
            if data:
                record_cache_hit("organization", "get_organization", duration)
                return json.loads(data)
            record_cache_miss("organization", "get_organization", duration)
            return None
        except (redis.RedisError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_organization error: {e}")
            record_cache_error("organization", "get_organization")
            self._note_operation_error(e, "get_organization")
            return None

    async def set_organization(
        self,
        org_id: str,
        org_data: dict[str, Any],
    ) -> bool:
        """Cache organization data with TTL."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"org:{org_id}"
            await self._redis.setex(key, settings.CACHE_ORG_TTL, json.dumps(org_data))
            record_cache_set("organization", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache set_organization error: {e}")
            record_cache_error("organization", "set_organization")
            self._note_operation_error(e, "set_organization")
            return False

    async def invalidate_organization(self, org_id: str) -> bool:
        """Invalidate cached organization data."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            await self._redis.delete(f"org:{org_id}")
            record_cache_delete("organization", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_organization error: {e}")
            record_cache_error("organization", "invalidate_organization")
            self._note_operation_error(e, "invalidate_organization")
            return False

    # ==================== User Caching ====================

    async def get_user(self, user_id: str) -> Optional[dict[str, Any]]:
        """Get cached user data."""
        if not await self._is_available():
            return None
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user:{user_id}"
            data = await self._redis.get(key)
            duration = time.time() - start_time
            if data:
                record_cache_hit("user", "get_user", duration)
                return json.loads(data)
            record_cache_miss("user", "get_user", duration)
            return None
        except (redis.RedisError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_user error: {e}")
            record_cache_error("user", "get_user")
            self._note_operation_error(e, "get_user")
            return None

    async def set_user(
        self,
        user_id: str,
        user_data: dict[str, Any],
    ) -> bool:
        """Cache user data with TTL."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user:{user_id}"
            await self._redis.setex(key, settings.CACHE_USER_TTL, json.dumps(user_data))
            record_cache_set("user", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache set_user error: {e}")
            record_cache_error("user", "set_user")
            self._note_operation_error(e, "set_user")
            return False

    async def invalidate_user(self, user_id: str) -> bool:
        """Invalidate all cached data for a user."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            await self._redis.delete(f"user:{user_id}")
            await self.invalidate_jwt_for_user(user_id)
            record_cache_delete("user", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_user error: {e}")
            record_cache_error("user", "invalidate_user")
            self._note_operation_error(e, "invalidate_user")
            return False

    # ==================== User Roles Caching ====================

    async def get_user_roles(
        self,
        org_id: str,
        user_id: str,
    ) -> Optional[list[str]]:
        """Get cached user roles for an organization."""
        if not await self._is_available():
            return None
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user_roles:{org_id}:{user_id}"
            data = await self._redis.get(key)
            duration = time.time() - start_time
            if data:
                record_cache_hit("roles", "get_user_roles", duration)
                return json.loads(data)
            record_cache_miss("roles", "get_user_roles", duration)
            return None
        except (redis.RedisError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_user_roles error: {e}")
            record_cache_error("roles", "get_user_roles")
            self._note_operation_error(e, "get_user_roles")
            return None

    async def set_user_roles(
        self,
        org_id: str,
        user_id: str,
        roles: list[str],
    ) -> bool:
        """Cache user roles with TTL."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user_roles:{org_id}:{user_id}"
            await self._redis.setex(key, settings.CACHE_ROLES_TTL, json.dumps(roles))
            record_cache_set("roles", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache set_user_roles error: {e}")
            record_cache_error("roles", "set_user_roles")
            self._note_operation_error(e, "set_user_roles")
            return False

    async def invalidate_user_roles(self, org_id: str, user_id: str) -> bool:
        """Invalidate cached roles for a user in an organization."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            await self._redis.delete(f"user_roles:{org_id}:{user_id}")
            await self.invalidate_jwt_for_user(user_id)
            record_cache_delete("roles", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_user_roles error: {e}")
            record_cache_error("roles", "invalidate_user_roles")
            self._note_operation_error(e, "invalidate_user_roles")
            return False

    # ==================== User Permissions Caching ====================

    async def get_user_permissions(
        self,
        org_id: str,
        user_id: str,
    ) -> Optional[list[str]]:
        """Get cached user permissions for an organization."""
        if not await self._is_available():
            return None
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user_perms:{org_id}:{user_id}"
            data = await self._redis.get(key)
            duration = time.time() - start_time
            if data:
                record_cache_hit("permissions", "get_user_permissions", duration)
                return json.loads(data)
            record_cache_miss("permissions", "get_user_permissions", duration)
            return None
        except (redis.RedisError, OSError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_user_permissions error: {e}")
            record_cache_error("permissions", "get_user_permissions")
            self._note_operation_error(e, "get_user_permissions")
            return None

    async def set_user_permissions(
        self,
        org_id: str,
        user_id: str,
        permissions: list[str],
    ) -> bool:
        """Cache user permissions with TTL."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            key = f"user_perms:{org_id}:{user_id}"
            await self._redis.setex(
                key, settings.CACHE_ROLES_TTL, json.dumps(permissions)
            )
            record_cache_set("permissions", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache set_user_permissions error: {e}")
            record_cache_error("permissions", "set_user_permissions")
            self._note_operation_error(e, "set_user_permissions")
            return False

    async def invalidate_user_permissions(self, org_id: str, user_id: str) -> bool:
        """Invalidate cached permissions for a user in an organization."""
        if not await self._is_available():
            return False
        assert self._redis is not None

        start_time = time.time()
        try:
            await self._redis.delete(f"user_perms:{org_id}:{user_id}")
            await self.invalidate_jwt_for_user(user_id)
            record_cache_delete("permissions", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_user_permissions error: {e}")
            record_cache_error("permissions", "invalidate_user_permissions")
            self._note_operation_error(e, "invalidate_user_permissions")
            return False

    async def invalidate_role_permissions(self, role_id: str) -> bool:
        """
        Invalidate cached permissions for a role.
        Note: This doesn't invalidate user caches - that needs to be done separately.
        """
        if not await self._is_available():
            return False

        start_time = time.time()
        try:
            # Role permissions are not directly cached, but we can use this
            # as a hook for future role-level caching if needed
            record_cache_delete("permissions", time.time() - start_time)
            return True
        except (redis.RedisError, OSError) as e:
            logger.warning(f"Cache invalidate_role_permissions error: {e}")
            record_cache_error("permissions", "invalidate_role_permissions")
            self._note_operation_error(e, "invalidate_role_permissions")
            return False


# Singleton instance
cache_service = AsyncCacheService()
