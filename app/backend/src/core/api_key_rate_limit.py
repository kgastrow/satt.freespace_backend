"""
API Key Rate Limiting Middleware
Enforces per-API-key rate limits based on configured limits using Redis.
Implements sliding window algorithm for accurate rate limiting.
"""

import time
from typing import Optional

from fastapi import HTTPException, status
import redis.asyncio as redis

from src.core.config import settings
from src.logger.logger import Logger as logger


# Default rate limits if none configured
DEFAULT_REQUESTS_PER_MINUTE = 60
DEFAULT_BURST_LIMIT = 10


class ApiKeyRateLimiter:
    """
    Rate limiter for API keys using Redis sliding window algorithm.

    Uses sorted sets in Redis to track individual request timestamps,
    allowing accurate sliding window rate limiting without fixed window edge cases.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None
        self._owns_pool = False
        self._enabled = settings.RATE_LIMIT_ENABLED

    def set_redis(self, client: redis.Redis) -> None:
        """Inject a shared Redis client from RedisPoolManager."""
        if not self._enabled:
            logger.info(
                "API key rate limiting disabled by configuration"
            )
            return
        self._redis = client
        self._owns_pool = False
        logger.info("API key rate limiter using shared Redis pool")

    async def connect(self) -> None:
        """Initialize with own pool (fallback for standalone/test use)."""
        if not self._enabled:
            logger.info(
                "API key rate limiting disabled by configuration"
            )
            return

        if self._redis is not None:
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            self._owns_pool = True
            await self._redis.ping()
            logger.info(
                "API key rate limiter Redis connection "
                "established (own pool)"
            )
        except redis.ConnectionError as e:
            logger.warning(
                f"Redis connection failed for API key rate "
                f"limiting, rate limiting disabled: {e}"
            )
            self._redis = None
            self._enabled = False

    async def disconnect(self) -> None:
        """Close Redis connection pool if we own it."""
        if self._owns_pool and self._pool:
            await self._pool.disconnect()
            logger.info(
                "API key rate limiter Redis connection pool closed"
            )
        self._redis = None

    async def _is_available(self) -> bool:
        """Check if Redis is available."""
        if not self._enabled or not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except redis.ConnectionError:
            return False

    def _get_rate_limit_key(self, api_key_id: str) -> str:
        """Generate Redis key for API key rate limit tracking."""
        return f"rate_limit:api_key:{api_key_id}"

    async def check_rate_limit(
        self,
        api_key_id: str,
        requests_per_minute: int,
        burst_limit: int,
        is_admin: bool = False,
    ) -> tuple[bool, Optional[int], int, int, Optional[int]]:
        """
        Check if API key is within rate limits using sliding window algorithm.

        Args:
            api_key_id: API key ID
            requests_per_minute: Maximum requests allowed per minute
            burst_limit: Maximum burst requests allowed above steady rate
            is_admin: If True, bypass rate limiting (for super admins)

        Returns:
            Tuple of (allowed, retry_after, limit, remaining, reset_timestamp)
            - allowed: True if request is allowed
            - retry_after: Seconds to wait before retry (if not allowed)
            - limit: Total requests per minute limit
            - remaining: Remaining requests in current window
            - reset_timestamp: Unix timestamp when rate limit resets
        """
        # Super admins bypass rate limiting if configured
        if is_admin and getattr(settings, "RATE_LIMIT_BYPASS_ADMIN", False):
            return True, None, requests_per_minute, requests_per_minute, None

        # If Redis unavailable, allow request (graceful degradation)
        if not await self._is_available():
            logger.warning("Redis unavailable, bypassing API key rate limit check")
            return True, None, requests_per_minute, requests_per_minute, None

        # After _is_available() check, _redis is guaranteed to be non-None
        assert self._redis is not None

        try:
            current_time = time.time()
            window_start = current_time - 60  # 60 second sliding window
            key = self._get_rate_limit_key(api_key_id)

            # Remove old entries outside the sliding window
            await self._redis.zremrangebyscore(key, 0, window_start)

            # Count requests in current window
            request_count = await self._redis.zcard(key)

            # Calculate total limit (steady rate + burst)
            total_limit = requests_per_minute + burst_limit

            # Check if limit exceeded
            if request_count >= total_limit:
                # Get oldest request in window to calculate retry-after
                oldest_requests = await self._redis.zrange(key, 0, 0, withscores=True)
                if oldest_requests:
                    oldest_timestamp = oldest_requests[0][1]
                    retry_after = int(oldest_timestamp + 60 - current_time) + 1
                else:
                    retry_after = 60

                return (
                    False,
                    retry_after,
                    total_limit,
                    0,
                    int(current_time + retry_after),
                )

            # Add current request to sorted set
            await self._redis.zadd(key, {str(current_time): current_time})

            # Set expiry on the key (cleanup after 2 minutes)
            await self._redis.expire(key, 120)

            # Calculate remaining requests
            remaining = total_limit - request_count - 1

            # Reset timestamp is 60 seconds from now (end of sliding window)
            reset_timestamp = int(current_time + 60)

            return True, None, total_limit, remaining, reset_timestamp

        except Exception as e:
            logger.error(f"Error checking API key rate limit: {e}")
            # On error, allow request (fail open)
            return True, None, requests_per_minute, requests_per_minute, None

    async def get_rate_limit_info(
        self, api_key_id: str, requests_per_minute: int, burst_limit: int
    ) -> tuple[int, int, Optional[int]]:
        """
        Get current rate limit status without incrementing counter.

        Args:
            api_key_id: API key ID
            requests_per_minute: Maximum requests allowed per minute
            burst_limit: Maximum burst requests allowed

        Returns:
            Tuple of (limit, remaining, reset_timestamp)
        """
        if not await self._is_available():
            return requests_per_minute, requests_per_minute, None

        # After _is_available() check, _redis is guaranteed to be non-None
        assert self._redis is not None

        try:
            current_time = time.time()
            window_start = current_time - 60
            key = self._get_rate_limit_key(api_key_id)

            # Remove old entries
            await self._redis.zremrangebyscore(key, 0, window_start)

            # Count current requests
            request_count = await self._redis.zcard(key)

            total_limit = requests_per_minute + burst_limit
            remaining = max(0, total_limit - request_count)
            reset_timestamp = int(current_time + 60)

            return total_limit, remaining, reset_timestamp

        except Exception as e:
            logger.error(f"Error getting rate limit info: {e}")
            return requests_per_minute, requests_per_minute, None


# Global rate limiter instance
api_key_rate_limiter = ApiKeyRateLimiter()


async def enforce_api_key_rate_limit(
    api_key_id: str,
    api_key_permissions: list[str],
    rate_limits_cache: dict[str, tuple[int, int]],
    is_admin: bool = False,
) -> None:
    """
    Enforce rate limits for an API key based on its permissions.

    Uses the most restrictive rate limit among all permissions the API key has.
    Rate limits are cached in memory to avoid database queries on every request.

    Args:
        api_key_id: API key ID
        api_key_permissions: List of permission codes the API key has
        rate_limits_cache: Dict mapping permission codes to (requests_per_minute, burst_limit)
        is_admin: If True, bypass rate limiting (for super admins)

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded
    """
    # Determine the most restrictive rate limit from all permissions
    min_rpm = DEFAULT_REQUESTS_PER_MINUTE
    min_burst = DEFAULT_BURST_LIMIT

    for permission_code in api_key_permissions:
        if permission_code in rate_limits_cache:
            rpm, burst = rate_limits_cache[permission_code]
            # Use most restrictive limits
            min_rpm = min(min_rpm, rpm)
            min_burst = min(min_burst, burst)

    # Check rate limit
    allowed, retry_after, limit, remaining, reset_ts = (
        await api_key_rate_limiter.check_rate_limit(
            api_key_id, min_rpm, min_burst, is_admin
        )
    )

    if not allowed:
        # Rate limit exceeded - return 429
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_ts) if reset_ts else "",
            "Retry-After": str(retry_after) if retry_after else "60",
        }
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers=headers,
        )


def add_rate_limit_headers(
    limit: int, remaining: int, reset_ts: Optional[int]
) -> dict[str, str]:
    """
    Create rate limit headers to include in successful responses.

    Args:
        limit: Total requests per minute limit
        remaining: Remaining requests in current window
        reset_ts: Unix timestamp when rate limit resets

    Returns:
        Dict of headers to add to response
    """
    headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
    }
    if reset_ts:
        headers["X-RateLimit-Reset"] = str(reset_ts)
    return headers
