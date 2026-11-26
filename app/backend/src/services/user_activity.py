"""
User activity tracking service for concurrent user metrics.
Uses Redis HyperLogLog for memory-efficient unique user counting.
"""

import time
from typing import Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.middleware.metrics import update_active_users


class UserActivityService:
    """
    Tracks user activity using Redis HyperLogLog for efficient unique counting.
    Provides metrics for concurrent/active users within configurable time windows.
    """

    def __init__(self):
        self._redis = None
        self._enabled = settings.METRICS_ENABLED

    def set_redis(self, redis_client) -> None:
        """
        Set the Redis client for activity tracking.
        Should be called during application startup.
        """
        self._redis = redis_client

    def _get_window_key(self, org_id: Optional[str] = None) -> str:
        """
        Get the Redis key for the current time window.
        Uses a sliding window based on METRICS_USER_ACTIVITY_WINDOW.
        """
        window_size = settings.METRICS_USER_ACTIVITY_WINDOW
        current_window = int(time.time()) // window_size

        if org_id:
            return f"active_users:{org_id}:{current_window}"
        return f"active_users:global:{current_window}"

    async def record_activity(
        self,
        user_id: str,
        org_id: Optional[str] = None,
    ) -> bool:
        """
        Record user activity for the current time window.
        Uses HyperLogLog for memory-efficient unique counting.

        Args:
            user_id: The user's ID
            org_id: Optional organization ID for per-org tracking

        Returns:
            True if recorded successfully, False otherwise
        """
        if not self._enabled or not self._redis:
            return False

        try:
            window_size = settings.METRICS_USER_ACTIVITY_WINDOW
            ttl = window_size * 2  # Keep for 2 windows

            # Record global activity
            global_key = self._get_window_key()
            await self._redis.pfadd(global_key, user_id)
            await self._redis.expire(global_key, ttl)

            # Record per-organization activity
            if org_id:
                org_key = self._get_window_key(org_id)
                await self._redis.pfadd(org_key, user_id)
                await self._redis.expire(org_key, ttl)

            return True

        except Exception as e:
            logger.warning(f"Failed to record user activity: {e}")
            return False

    async def get_active_user_count(
        self,
        org_id: Optional[str] = None,
    ) -> int:
        """
        Get the count of unique active users in the current window.

        Args:
            org_id: Optional organization ID for per-org count

        Returns:
            Estimated unique user count (HyperLogLog approximation)
        """
        if not self._enabled or not self._redis:
            return 0

        try:
            key = self._get_window_key(org_id)
            count = await self._redis.pfcount(key)
            return count

        except Exception as e:
            logger.warning(f"Failed to get active user count: {e}")
            return 0

    async def get_active_users_multi_org(
        self,
        org_ids: list,
    ) -> dict:
        """
        Get active user counts for multiple organizations.

        Args:
            org_ids: List of organization IDs

        Returns:
            Dict mapping org_id to user count
        """
        if not self._enabled or not self._redis:
            return {}

        result = {}
        for org_id in org_ids:
            result[org_id] = await self.get_active_user_count(org_id)

        return result

    async def update_metrics(self) -> None:
        """
        Update Prometheus metrics with current active user counts.
        Should be called periodically (e.g., every 15 seconds).
        """
        if not self._enabled or not self._redis:
            return

        try:
            # Update global active users
            global_count = await self.get_active_user_count()
            window_label = f"{settings.METRICS_USER_ACTIVITY_WINDOW}s"
            update_active_users(global_count, window_label)

        except Exception as e:
            logger.warning(f"Failed to update user activity metrics: {e}")


# Singleton instance
user_activity_service = UserActivityService()
