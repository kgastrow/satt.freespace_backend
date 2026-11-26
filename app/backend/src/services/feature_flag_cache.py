"""
Feature flag caching service.
Provides Redis caching for resolved feature flags per organization with 60-second TTL.
Gracefully degrades when Redis is unavailable.
"""

from typing import Optional

from src.logger.logger import Logger as logger
from src.middleware.cache_metrics import (
    record_cache_delete,
    record_cache_error,
    record_cache_hit,
    record_cache_miss,
    record_cache_set,
)
from src.services.cache import cache_service


class FeatureFlagCache:
    """
    Feature flag caching layer.
    Caches resolved feature flags per organization with 60-second TTL.
    """

    FEATURE_FLAG_TTL = 60

    def _get_cache_key(self, org_id: str) -> str:
        """Generate cache key for organization's feature flags."""
        return f"feature_flags:{org_id}"

    async def get_org_feature_flags(self, org_id: str) -> Optional[dict[str, bool]]:
        """
        Get cached resolved feature flags for an organization.
        Returns None on cache miss or Redis unavailable.
        """
        import json
        import time

        import redis.asyncio as redis_module

        if not await cache_service._is_available():
            return None

        start_time = time.time()
        try:
            key = self._get_cache_key(org_id)
            redis = cache_service._redis
            if not redis:
                return None

            data = await redis.get(key)
            duration = time.time() - start_time

            if data:
                record_cache_hit("feature_flags", "get_org_feature_flags", duration)
                return json.loads(data)

            record_cache_miss("feature_flags", "get_org_feature_flags", duration)
            return None

        except (redis_module.RedisError, json.JSONDecodeError) as e:
            logger.warning(f"Cache get_org_feature_flags error: {e}")
            record_cache_error("feature_flags", "get_org_feature_flags")
            return None

    async def set_org_feature_flags(self, org_id: str, flags: dict[str, bool]) -> bool:
        """
        Cache resolved feature flags for an organization with 60-second TTL.
        Returns False if Redis is unavailable.
        """
        import json
        import time

        import redis.asyncio as redis_module

        if not await cache_service._is_available():
            return False

        start_time = time.time()
        try:
            key = self._get_cache_key(org_id)
            redis = cache_service._redis
            if not redis:
                return False

            await redis.setex(key, self.FEATURE_FLAG_TTL, json.dumps(flags))
            record_cache_set("feature_flags", time.time() - start_time)
            return True

        except redis_module.RedisError as e:
            logger.warning(f"Cache set_org_feature_flags error: {e}")
            record_cache_error("feature_flags", "set_org_feature_flags")
            return False

    async def invalidate_org_feature_flags(self, org_id: str) -> bool:
        """
        Invalidate cached feature flags for an organization.
        Should be called when flags or overrides are created/updated/deleted.
        """
        import time

        import redis.asyncio as redis_module

        if not await cache_service._is_available():
            return False

        start_time = time.time()
        try:
            key = self._get_cache_key(org_id)
            redis = cache_service._redis
            if not redis:
                return False

            await redis.delete(key)
            record_cache_delete("feature_flags", time.time() - start_time)
            return True

        except redis_module.RedisError as e:
            logger.warning(f"Cache invalidate_org_feature_flags error: {e}")
            record_cache_error("feature_flags", "invalidate_org_feature_flags")
            return False

    async def invalidate_all_feature_flags(self) -> bool:
        """
        Invalidate cached feature flags for ALL organizations.
        Uses Redis SCAN to find and delete all feature_flags:* keys.
        Should be called when a flag's default_enabled changes or flag is deleted.
        """
        import time

        import redis.asyncio as redis_module

        if not await cache_service._is_available():
            return False

        start_time = time.time()
        try:
            redis = cache_service._redis
            if not redis:
                return False

            # Use SCAN to find all feature_flags:* keys (safer than KEYS for production)
            deleted_count = 0
            cursor = 0
            while True:
                cursor, keys = await redis.scan(
                    cursor, match="feature_flags:*", count=100
                )
                if keys:
                    await redis.delete(*keys)
                    deleted_count += len(keys)
                if cursor == 0:
                    break

            record_cache_delete("feature_flags", time.time() - start_time)
            logger.info(f"Invalidated {deleted_count} feature flag cache entries")
            return True

        except redis_module.RedisError as e:
            logger.warning(f"Cache invalidate_all_feature_flags error: {e}")
            record_cache_error("feature_flags", "invalidate_all_feature_flags")
            return False


# Singleton instance
feature_flag_cache = FeatureFlagCache()
