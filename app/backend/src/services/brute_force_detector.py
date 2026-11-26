"""
Brute Force Detection Service.

Uses Redis to implement sliding window detection for login attempts.
Tracks failures by IP address and triggers alerts when thresholds are exceeded.
"""

import time
from typing import Optional

import redis.asyncio as redis

from src.core.config import settings
from src.logger.logger import Logger as logger


# Default configuration - IP-based
DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_WINDOW_SECONDS = 300  # 5 minutes
DEFAULT_BLOCK_DURATION_SECONDS = 900  # 15 minutes

# Account-based lockout configuration
ACCOUNT_LOCKOUT_THRESHOLD = 5
ACCOUNT_LOCKOUT_WINDOW_SECONDS = 300  # 5 minutes
# Progressive lockout durations: (failure_count_threshold, lockout_seconds)
ACCOUNT_LOCKOUT_TIERS = [
    (5, 60),  # 5 failures  -> 1 minute lockout
    (10, 300),  # 10 failures -> 5 minute lockout
    (15, 900),  # 15 failures -> 15 minute lockout
    (20, 3600),  # 20 failures -> 60 minute lockout
]

# Password reset IP-based rate limiting
PASSWORD_RESET_IP_THRESHOLD = 5  # Max password reset requests per IP
PASSWORD_RESET_IP_WINDOW_SECONDS = 3600  # 1 hour window

# 2FA-specific lockout configuration
TWO_FACTOR_LOCKOUT_THRESHOLD = 5  # Max failed 2FA attempts before lockout
TWO_FACTOR_LOCKOUT_DURATION_SECONDS = 900  # 15 minute lockout


class BruteForceDetector:
    """
    Redis-backed brute force detection using sliding window algorithm.

    Tracks failed authentication attempts per IP address and identifies
    potential brute force attacks when failures exceed the threshold.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None
        self._owns_pool = False
        self._enabled = True

    def set_redis(self, client: redis.Redis) -> None:
        """Inject a shared Redis client from RedisPoolManager."""
        self._redis = client
        self._owns_pool = False
        logger.info("Brute force detector using shared Redis pool")

    async def connect(self) -> None:
        """Initialize with own pool (fallback for standalone/test use)."""
        if self._redis is not None:
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=10,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            self._owns_pool = True
            await self._redis.ping()
            logger.info(
                "Brute force detector Redis connection "
                "established (own pool)"
            )
        except redis.ConnectionError as e:
            logger.warning(
                f"Redis connection failed for brute force "
                f"detection, detection disabled: {e}"
            )
            self._redis = None
            self._enabled = False

    async def disconnect(self) -> None:
        """Close Redis connection pool if we own it."""
        if self._owns_pool and self._pool:
            await self._pool.disconnect()
            logger.info(
                "Brute force detector Redis connection pool closed"
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

    def _get_failure_key(self, ip: str) -> str:
        """Generate Redis key for tracking failures by IP."""
        return f"brute_force:failures:{ip}"

    def _get_block_key(self, ip: str) -> str:
        """Generate Redis key for blocked IPs."""
        return f"brute_force:blocked:{ip}"

    async def record_failure(
        self,
        ip: str,
        failure_type: str = "login",
        threshold: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ) -> bool:
        """
        Record a failed authentication attempt.

        Uses sliding window to track failures within the time window.
        Returns True if threshold is exceeded (potential brute force).

        Args:
            ip: Client IP address
            failure_type: Type of failure (login, 2fa, api_key)
            threshold: Number of failures before alerting (default: 5)
            window_seconds: Time window in seconds (default: 300)

        Returns:
            True if threshold exceeded, False otherwise
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        threshold = threshold or DEFAULT_FAILURE_THRESHOLD
        window_seconds = window_seconds or DEFAULT_WINDOW_SECONDS

        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            key = self._get_failure_key(ip)

            # Use pipeline for atomic operations
            async with self._redis.pipeline() as pipe:
                # Remove old entries outside the sliding window
                await pipe.zremrangebyscore(key, 0, window_start)
                # Add current failure
                await pipe.zadd(key, {f"{current_time}:{failure_type}": current_time})
                # Count failures in window
                await pipe.zcard(key)
                # Set expiry
                await pipe.expire(key, window_seconds + 60)
                results = await pipe.execute()

            failure_count = results[2]

            if failure_count >= threshold:
                logger.warning(
                    f"Brute force threshold exceeded: ip={ip}, "
                    f"failures={failure_count}, threshold={threshold}"
                )
                # Record the event for metrics
                from src.middleware.security_metrics import record_brute_force_event

                record_brute_force_event(ip, "threshold_exceeded")
                return True

            return False

        except Exception as e:
            logger.error(f"Error recording brute force failure: {e}")
            return False

    async def is_blocked(
        self,
        ip: str,
    ) -> bool:
        """
        Check if an IP is currently blocked.

        Args:
            ip: Client IP address

        Returns:
            True if IP is blocked, False otherwise
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            key = self._get_block_key(ip)
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking blocked status: {e}")
            return False

    async def block_ip(
        self,
        ip: str,
        duration_seconds: Optional[int] = None,
        reason: str = "brute_force",
    ) -> bool:
        """
        Block an IP address temporarily.

        Args:
            ip: Client IP address
            duration_seconds: How long to block (default: 15 minutes)
            reason: Reason for blocking

        Returns:
            True if successfully blocked, False otherwise
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        duration = duration_seconds or DEFAULT_BLOCK_DURATION_SECONDS

        try:
            key = self._get_block_key(ip)
            await self._redis.setex(key, duration, reason)

            from src.middleware.security_metrics import record_brute_force_event

            record_brute_force_event(ip, "ip_blocked")

            logger.warning(
                f"IP blocked: ip={ip}, duration={duration}s, reason={reason}"
            )
            return True
        except Exception as e:
            logger.error(f"Error blocking IP: {e}")
            return False

    async def unblock_ip(self, ip: str) -> bool:
        """
        Manually unblock an IP address.

        Args:
            ip: Client IP address

        Returns:
            True if successfully unblocked, False otherwise
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            key = self._get_block_key(ip)
            await self._redis.delete(key)
            logger.info(f"IP unblocked: ip={ip}")
            return True
        except Exception as e:
            logger.error(f"Error unblocking IP: {e}")
            return False

    async def get_failure_count(
        self,
        ip: str,
        window_seconds: Optional[int] = None,
    ) -> int:
        """
        Get the number of failures for an IP in the current window.

        Args:
            ip: Client IP address
            window_seconds: Time window in seconds (default: 300)

        Returns:
            Number of failures in the window
        """
        if not await self._is_available():
            return 0

        assert self._redis is not None

        window_seconds = window_seconds or DEFAULT_WINDOW_SECONDS

        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            key = self._get_failure_key(ip)

            # Remove old entries and count
            await self._redis.zremrangebyscore(key, 0, window_start)
            return await self._redis.zcard(key)
        except Exception as e:
            logger.error(f"Error getting failure count: {e}")
            return 0

    async def get_recent_blocked_ips(self, limit: int = 100) -> list[dict]:
        """
        Get recently blocked IPs.

        Args:
            limit: Maximum number of results

        Returns:
            List of dicts with ip and reason
        """
        if not await self._is_available():
            return []

        assert self._redis is not None

        try:
            # Scan for blocked keys
            blocked_ips = []
            pattern = "brute_force:blocked:*"

            async for key in self._redis.scan_iter(match=pattern, count=limit):
                ip = key.decode().replace("brute_force:blocked:", "")
                reason = await self._redis.get(key)
                ttl = await self._redis.ttl(key)
                blocked_ips.append(
                    {
                        "ip": ip,
                        "reason": reason.decode() if reason else "unknown",
                        "ttl_seconds": ttl if ttl > 0 else 0,
                    }
                )

                if len(blocked_ips) >= limit:
                    break

            return blocked_ips
        except Exception as e:
            logger.error(f"Error getting blocked IPs: {e}")
            return []

    async def clear_failures(self, ip: str) -> bool:
        """
        Clear all failure records for an IP (e.g., after successful login).

        Args:
            ip: Client IP address

        Returns:
            True if cleared, False otherwise
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            key = self._get_failure_key(ip)
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"Error clearing failures: {e}")
            return False

    # ── Account-level lockout methods ──

    def _get_account_failure_key(self, email: str, org_slug: str) -> str:
        """Generate Redis key for tracking failures by account."""
        return f"brute_force:account_failures:{org_slug}:{email.lower()}"

    def _get_account_lock_key(self, email: str, org_slug: str) -> str:
        """Generate Redis key for locked accounts."""
        return f"brute_force:account_locked:{org_slug}:{email.lower()}"

    async def record_account_failure(
        self,
        email: str,
        org_slug: str,
    ) -> bool:
        """
        Record a failed login attempt for an account and apply progressive lockout.

        Returns True if account is now locked.
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            current_time = time.time()
            window_start = current_time - ACCOUNT_LOCKOUT_WINDOW_SECONDS
            key = self._get_account_failure_key(email, org_slug)

            async with self._redis.pipeline() as pipe:
                await pipe.zremrangebyscore(key, 0, window_start)
                await pipe.zadd(key, {f"{current_time}:login": current_time})
                await pipe.zcard(key)
                await pipe.expire(key, ACCOUNT_LOCKOUT_WINDOW_SECONDS + 60)
                results = await pipe.execute()

            failure_count = results[2]

            # Apply progressive lockout based on tiers
            for threshold, duration in reversed(ACCOUNT_LOCKOUT_TIERS):
                if failure_count >= threshold:
                    lock_key = self._get_account_lock_key(email, org_slug)
                    await self._redis.setex(
                        lock_key, duration, f"progressive:{failure_count}"
                    )
                    logger.warning(
                        f"Account locked: email={email}, org={org_slug}, "
                        f"failures={failure_count}, duration={duration}s"
                    )
                    return True

            return False

        except Exception as e:
            logger.error(f"Error recording account failure: {e}")
            return False

    async def is_account_locked(self, email: str, org_slug: str) -> bool:
        """Check if an account is currently locked due to failed attempts."""
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            key = self._get_account_lock_key(email, org_slug)
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking account lock: {e}")
            return False

    async def clear_account_failures(self, email: str, org_slug: str) -> bool:
        """Clear account failure records and lock on successful login."""
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            failure_key = self._get_account_failure_key(email, org_slug)
            lock_key = self._get_account_lock_key(email, org_slug)
            await self._redis.delete(failure_key, lock_key)
            return True
        except Exception as e:
            logger.error(f"Error clearing account failures: {e}")
            return False

    # ── Password reset IP-based rate limiting methods ──

    def _get_password_reset_ip_key(self, ip: str) -> str:
        """Generate Redis key for tracking password reset requests by IP."""
        return f"brute_force:password_reset_ip:{ip}"

    async def record_password_reset_request(self, ip: str) -> bool:
        """
        Record a password reset request from an IP address.

        Returns True if threshold is exceeded (potential abuse).
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            current_time = time.time()
            window_start = current_time - PASSWORD_RESET_IP_WINDOW_SECONDS
            key = self._get_password_reset_ip_key(ip)

            async with self._redis.pipeline() as pipe:
                await pipe.zremrangebyscore(key, 0, window_start)
                await pipe.zadd(key, {f"{current_time}:reset": current_time})
                await pipe.zcard(key)
                await pipe.expire(key, PASSWORD_RESET_IP_WINDOW_SECONDS + 60)
                results = await pipe.execute()

            request_count = results[2]

            if request_count > PASSWORD_RESET_IP_THRESHOLD:
                logger.warning(
                    f"Password reset IP threshold exceeded: ip={ip}, "
                    f"requests={request_count}, threshold={PASSWORD_RESET_IP_THRESHOLD}"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error recording password reset request: {e}")
            return False

    # ── 2FA-specific lockout methods ──

    def _get_2fa_failure_key(self, user_id: str) -> str:
        """Generate Redis key for tracking 2FA failures by user."""
        return f"brute_force:2fa_failures:{user_id}"

    def _get_2fa_lock_key(self, user_id: str) -> str:
        """Generate Redis key for 2FA locked users."""
        return f"brute_force:2fa_locked:{user_id}"

    async def record_2fa_failure(self, user_id: str) -> bool:
        """
        Record a failed 2FA attempt for a user and apply lockout if threshold exceeded.

        Returns True if user is now locked out.
        """
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            current_time = time.time()
            # Use the lockout duration as the window for counting failures
            window_start = current_time - TWO_FACTOR_LOCKOUT_DURATION_SECONDS
            key = self._get_2fa_failure_key(user_id)

            async with self._redis.pipeline() as pipe:
                await pipe.zremrangebyscore(key, 0, window_start)
                await pipe.zadd(key, {f"{current_time}:2fa": current_time})
                await pipe.zcard(key)
                await pipe.expire(key, TWO_FACTOR_LOCKOUT_DURATION_SECONDS + 60)
                results = await pipe.execute()

            failure_count = results[2]

            if failure_count >= TWO_FACTOR_LOCKOUT_THRESHOLD:
                lock_key = self._get_2fa_lock_key(user_id)
                await self._redis.setex(
                    lock_key,
                    TWO_FACTOR_LOCKOUT_DURATION_SECONDS,
                    f"2fa_failures:{failure_count}",
                )
                logger.warning(
                    f"2FA locked: user_id={user_id}, "
                    f"failures={failure_count}, duration={TWO_FACTOR_LOCKOUT_DURATION_SECONDS}s"
                )
                return True

            return False

        except Exception as e:
            logger.error(f"Error recording 2FA failure: {e}")
            return False

    async def is_2fa_locked(self, user_id: str) -> bool:
        """Check if a user is currently locked out due to 2FA failures."""
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            key = self._get_2fa_lock_key(user_id)
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Error checking 2FA lock: {e}")
            return False

    async def get_2fa_lockout_ttl(self, user_id: str) -> int:
        """Get remaining lockout time in seconds for a 2FA-locked user."""
        if not await self._is_available():
            return 0

        assert self._redis is not None

        try:
            key = self._get_2fa_lock_key(user_id)
            ttl = await self._redis.ttl(key)
            return ttl if ttl > 0 else 0
        except Exception as e:
            logger.error(f"Error getting 2FA lockout TTL: {e}")
            return 0

    async def clear_2fa_failures(self, user_id: str) -> bool:
        """Clear 2FA failure records and lock on successful verification."""
        if not await self._is_available():
            return False

        assert self._redis is not None

        try:
            failure_key = self._get_2fa_failure_key(user_id)
            lock_key = self._get_2fa_lock_key(user_id)
            await self._redis.delete(failure_key, lock_key)
            return True
        except Exception as e:
            logger.error(f"Error clearing 2FA failures: {e}")
            return False


# Singleton instance
brute_force_detector = BruteForceDetector()
