"""
Job Stats Service.

Redis-based service for tracking background job execution metrics using sliding windows.
"""

from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis

from src.core.config import settings
from src.logger.logger import Logger as logger


# Redis key patterns for job stats
JOB_STATS_EXECUTIONS_KEY = "job_stats:{job_type}:executions:{hour}"
JOB_STATS_FAILURES_KEY = "job_stats:{job_type}:failures:{hour}"
JOB_STATS_DURATIONS_KEY = "job_stats:{job_type}:durations:{hour}"
JOB_ENABLED_CONFIG_KEY = "jobs.{job_type}.enabled"

# TTL for stats: 25 hours (to ensure 24h window is always available)
STATS_TTL_SECONDS = 25 * 60 * 60


class JobStatsService:
    """
    Service for tracking background job execution metrics.

    Uses Redis sliding windows (24h) for tracking:
    - Execution counts per job type
    - Failure counts per job type
    - Execution durations for avg calculation
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
        logger.info("Job stats service using shared Redis pool")

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
                "Job stats service Redis connection established (own pool)"
            )
        except redis.ConnectionError as e:
            logger.warning(
                f"Redis connection failed for job stats service: {e}"
            )
            self._redis = None
            self._enabled = False

    async def disconnect(self) -> None:
        """Close Redis connection pool if we own it."""
        if self._owns_pool and self._pool:
            await self._pool.disconnect()
            logger.info("Job stats service Redis connection pool closed")
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

    def _get_hour_bucket(self, timestamp: Optional[datetime] = None) -> str:
        """Get the hour bucket key for a timestamp."""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        return timestamp.strftime("%Y%m%d%H")

    def _get_executions_key(self, job_type: str, hour: str) -> str:
        """Get Redis key for executions."""
        return JOB_STATS_EXECUTIONS_KEY.format(job_type=job_type, hour=hour)

    def _get_failures_key(self, job_type: str, hour: str) -> str:
        """Get Redis key for failures."""
        return JOB_STATS_FAILURES_KEY.format(job_type=job_type, hour=hour)

    def _get_durations_key(self, job_type: str, hour: str) -> str:
        """Get Redis key for durations."""
        return JOB_STATS_DURATIONS_KEY.format(job_type=job_type, hour=hour)

    async def record_job_execution(
        self,
        job_type: str,
        status: str,
        duration_ms: float,
    ) -> None:
        """
        Record a job execution.

        Args:
            job_type: The job type/name (e.g., 'send_email_task')
            status: 'success' or 'failure'
            duration_ms: Execution duration in milliseconds
        """
        if not await self._is_available():
            return

        assert self._redis is not None

        try:
            now = datetime.now(timezone.utc)
            hour = self._get_hour_bucket(now)
            timestamp = now.timestamp()

            # Record execution
            exec_key = self._get_executions_key(job_type, hour)
            await self._redis.zadd(exec_key, {f"{timestamp}": timestamp})
            await self._redis.expire(exec_key, STATS_TTL_SECONDS)

            # Record failure if applicable
            if status == "failure":
                fail_key = self._get_failures_key(job_type, hour)
                await self._redis.zadd(fail_key, {f"{timestamp}": timestamp})
                await self._redis.expire(fail_key, STATS_TTL_SECONDS)

            # Record duration
            dur_key = self._get_durations_key(job_type, hour)
            await self._redis.zadd(dur_key, {f"{timestamp}:{duration_ms}": timestamp})
            await self._redis.expire(dur_key, STATS_TTL_SECONDS)

        except Exception as e:
            logger.warning(f"Failed to record job execution: {e}")

    async def get_job_stats(
        self,
        job_type: str,
        window_hours: int = 24,
    ) -> dict:
        """
        Get stats for a specific job type.

        Args:
            job_type: The job type to get stats for
            window_hours: Number of hours to look back (default 24)

        Returns:
            Dictionary with execution stats
        """
        if not await self._is_available():
            return self._empty_stats(job_type)

        assert self._redis is not None

        try:
            now = datetime.now(timezone.utc)
            total_executions = 0
            total_failures = 0
            durations = []
            last_execution: Optional[float] = None

            # Iterate through hour buckets
            for hours_ago in range(window_hours):
                hour_dt = datetime.fromtimestamp(
                    now.timestamp() - (hours_ago * 3600), tz=timezone.utc
                )
                hour = self._get_hour_bucket(hour_dt)

                # Get executions for this hour
                exec_key = self._get_executions_key(job_type, hour)
                exec_count = await self._redis.zcard(exec_key)
                total_executions += exec_count

                # Get failures for this hour
                fail_key = self._get_failures_key(job_type, hour)
                fail_count = await self._redis.zcard(fail_key)
                total_failures += fail_count

                # Get durations for this hour
                dur_key = self._get_durations_key(job_type, hour)
                dur_entries = await self._redis.zrange(dur_key, 0, -1, withscores=True)
                for entry, _ in dur_entries:
                    # Entry format: "timestamp:duration_ms"
                    parts = entry.split(":")
                    if len(parts) >= 2:
                        try:
                            durations.append(float(parts[1]))
                        except ValueError:
                            pass

                # Track last execution time from current hour (most recent first)
                if last_execution is None and exec_count > 0:
                    # Get the highest score (most recent timestamp)
                    latest = await self._redis.zrange(exec_key, -1, -1, withscores=True)
                    if latest:
                        last_execution = latest[0][1]

            # Calculate average duration
            avg_duration_ms = sum(durations) / len(durations) if durations else 0.0

            # Calculate failure rate
            failure_rate = (
                (total_failures / total_executions * 100)
                if total_executions > 0
                else 0.0
            )

            return {
                "job_type": job_type,
                "executions_24h": total_executions,
                "failures_24h": total_failures,
                "failure_rate": round(failure_rate, 2),
                "avg_duration_ms": round(avg_duration_ms, 2),
                "last_execution": (
                    datetime.fromtimestamp(last_execution, tz=timezone.utc).isoformat()
                    if last_execution
                    else None
                ),
            }

        except Exception as e:
            logger.error(f"Error getting job stats for {job_type}: {e}")
            return self._empty_stats(job_type)

    def _empty_stats(self, job_type: str) -> dict:
        """Return empty stats structure."""
        return {
            "job_type": job_type,
            "executions_24h": 0,
            "failures_24h": 0,
            "failure_rate": 0.0,
            "avg_duration_ms": 0.0,
            "last_execution": None,
        }

    async def get_all_job_stats(
        self,
        job_types: list[str],
        window_hours: int = 24,
    ) -> list[dict]:
        """
        Get stats for all specified job types.

        Args:
            job_types: List of job types to get stats for
            window_hours: Number of hours to look back (default 24)

        Returns:
            List of stats dictionaries
        """
        stats = []
        for job_type in job_types:
            job_stats = await self.get_job_stats(job_type, window_hours)
            stats.append(job_stats)
        return stats

    async def is_job_disabled(self, job_type: str) -> bool:
        """
        Check if a job type is disabled via SystemConfig.

        Args:
            job_type: The job type to check

        Returns:
            True if disabled, False if enabled (default)
        """
        if not await self._is_available():
            return False  # Default to enabled if Redis unavailable

        assert self._redis is not None

        try:
            # Check Redis cache first for job enabled state
            cache_key = f"job_enabled_cache:{job_type}"
            cached = await self._redis.get(cache_key)
            if cached is not None:
                return cached == "0"  # "0" = disabled, "1" = enabled

            # Not cached - will be populated on next toggle or sync
            return False

        except Exception as e:
            logger.warning(f"Failed to check job disabled status: {e}")
            return False

    async def set_job_enabled_cache(self, job_type: str, enabled: bool) -> None:
        """
        Cache the job enabled state in Redis.

        Args:
            job_type: The job type
            enabled: Whether the job is enabled
        """
        if not await self._is_available():
            return

        assert self._redis is not None

        try:
            cache_key = f"job_enabled_cache:{job_type}"
            await self._redis.set(cache_key, "1" if enabled else "0")
            # Cache for 5 minutes
            await self._redis.expire(cache_key, 300)
        except Exception as e:
            logger.warning(f"Failed to set job enabled cache: {e}")


# Singleton instance
job_stats_service = JobStatsService()
