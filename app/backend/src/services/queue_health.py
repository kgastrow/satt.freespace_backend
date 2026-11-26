"""
Queue Health Service.

Monitors ARQ job queue health including depth, stuck jobs, and worker status.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import redis.asyncio as redis

from src.constants.queues import (
    ARQ_HEALTH_CHECK_KEY,
    ARQ_IN_PROGRESS_KEY_PREFIX,
    ARQ_IN_PROGRESS_TIMEOUT_SECONDS,
    ARQ_JOB_KEY_PREFIX,
    ARQ_QUEUE_NAME,
)
from src.core.config import settings
from src.logger.logger import Logger as logger


# Default thresholds
DEFAULT_DEPTH_THRESHOLD = 100

# A running job is only observable for as long as arq's in-progress key lives
# (job_timeout + 10 = 310s). A threshold at or above that can never match, so
# the default sits comfortably below the ceiling.
DEFAULT_STUCK_JOB_MINUTES = 4


class QueueHealthService:
    """
    Service for monitoring ARQ job queue health.

    Checks:
    - Queue depth (number of pending jobs)
    - Stuck jobs (jobs in progress for too long)
    - Worker status (heartbeat monitoring)
    """

    DEPTH_THRESHOLD = DEFAULT_DEPTH_THRESHOLD
    STUCK_JOB_MINUTES = DEFAULT_STUCK_JOB_MINUTES

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None
        self._owns_pool = False
        self._enabled = True
        # arq's job payloads are pickled bytes, so they need a client that does
        # not decode responses. Built lazily and cached; the latch stops a
        # failed connection being retried on every scan.
        self._binary_redis: Optional[redis.Redis] = None
        self._binary_pool: Optional[redis.ConnectionPool] = None
        self._binary_unavailable = False

    def set_redis(self, client: redis.Redis) -> None:
        """Inject a shared Redis client from RedisPoolManager (DB 1)."""
        self._redis = client
        self._owns_pool = False
        logger.info("Queue health service using shared Redis pool")

    async def connect(self) -> None:
        """Initialize with own pool (fallback for standalone/test use)."""
        if self._redis is not None:
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                settings.ARQ_REDIS_URL,
                decode_responses=True,
                max_connections=10,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            self._owns_pool = True
            await self._redis.ping()
            logger.info(
                "Queue health service Redis connection " "established (own pool)"
            )
        except redis.ConnectionError as e:
            logger.warning(f"Redis connection failed for queue " f"health service: {e}")
            self._redis = None
            self._enabled = False

    async def disconnect(self) -> None:
        """Close Redis connection pool if we own it."""
        if self._owns_pool and self._pool:
            await self._pool.disconnect()
            logger.info("Queue health service Redis connection pool closed")
        self._redis = None

        if self._binary_pool:
            await self._binary_pool.disconnect()
            self._binary_pool = None
        self._binary_redis = None
        self._binary_unavailable = False

    async def _get_binary_redis(self) -> Optional[redis.Redis]:
        """
        Get a non-decoding Redis client for reading arq's pickled job payloads.

        The shared monitoring client is created with decode_responses=True,
        which mangles pickled bytes on read.
        """
        if self._binary_unavailable:
            return None
        if self._binary_redis is not None:
            return self._binary_redis

        try:
            self._binary_pool = redis.ConnectionPool.from_url(
                settings.ARQ_REDIS_URL,
                decode_responses=False,
                max_connections=2,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            self._binary_redis = redis.Redis(connection_pool=self._binary_pool)
            await self._binary_redis.ping()
            return self._binary_redis
        except Exception as e:
            logger.warning(
                f"Queue health service could not open a binary Redis "
                f"connection; stuck job function names unavailable: {e}"
            )
            self._binary_redis = None
            self._binary_pool = None
            self._binary_unavailable = True
            return None

    async def _get_job_function(self, job_id: str) -> Optional[str]:
        """Resolve a job's function name from its pickled arq job payload."""
        binary = await self._get_binary_redis()
        if binary is None:
            return None

        try:
            from arq.jobs import deserialize_job

            raw = await binary.get(f"{ARQ_JOB_KEY_PREFIX}{job_id}")
            return deserialize_job(raw).function if raw else None
        except Exception as e:
            logger.debug(f"Could not resolve function name for job {job_id}: {e}")
            return None

    async def _is_available(self) -> bool:
        """Check if Redis is available."""
        if not self._enabled or not self._redis:
            return False
        try:
            await self._redis.ping()
            return True
        except redis.ConnectionError:
            return False

    async def get_queue_depth(self) -> int:
        """
        Get the current queue depth (number of pending jobs).

        Returns:
            Number of jobs waiting in the queue
        """
        if not await self._is_available():
            return 0

        assert self._redis is not None

        try:
            # The worker runs on an app-specific queue name, not arq's default.
            return await self._redis.zcard(ARQ_QUEUE_NAME)
        except Exception as e:
            logger.error(f"Error getting queue depth: {e}")
            return 0

    async def get_stuck_jobs(
        self,
        stuck_threshold_minutes: Optional[int] = None,
    ) -> list[dict]:
        """
        Get jobs that have been in progress for too long.

        arq marks a running job with `arq:in-progress:<job_id>`, psetex'd with
        TTL `job_timeout + 10` seconds. The key holds only b"1" - no function
        name, no start time - so elapsed run time is derived from its PTTL.

        An in-progress key alone does not mean the job is still running: when a
        cron job finishes, arq re-expires its in-progress key to
        `keep_cronjob_progress` (60s) to block duplicate runs, which is
        indistinguishable from a long-running job by TTL alone. arq does delete
        `arq:job:<id>` on both the success and failure paths, so the presence of
        the job key is what separates a running job from a finished cron.

        Args:
            stuck_threshold_minutes: Minutes after which a job is considered stuck

        Returns:
            List of stuck job dictionaries with id, start_time, and duration
        """
        if not await self._is_available():
            return []

        assert self._redis is not None

        threshold = stuck_threshold_minutes or self.STUCK_JOB_MINUTES
        threshold_seconds = threshold * 60

        if threshold_seconds >= ARQ_IN_PROGRESS_TIMEOUT_SECONDS:
            logger.warning(
                f"Stuck-job threshold of {threshold} minutes exceeds the "
                f"{ARQ_IN_PROGRESS_TIMEOUT_SECONDS}s lifetime of arq's "
                f"in-progress key; the stuck-job count will always be 0. "
                f"Raise job_timeout first if a longer threshold is needed."
            )

        now = datetime.now(timezone.utc)
        stuck_jobs: list[dict] = []

        try:
            pattern = f"{ARQ_IN_PROGRESS_KEY_PREFIX}*"

            async for key in self._redis.scan_iter(match=pattern, count=100):
                try:
                    job_id = key[len(ARQ_IN_PROGRESS_KEY_PREFIX) :]

                    ttl_ms = await self._redis.pttl(key)
                    if not ttl_ms or ttl_ms <= 0:
                        continue

                    # EXISTS returns an int, so the decoding client is safe here.
                    if not await self._redis.exists(f"{ARQ_JOB_KEY_PREFIX}{job_id}"):
                        # Finished cron holding a shortened in-progress key.
                        continue

                    elapsed_seconds = ARQ_IN_PROGRESS_TIMEOUT_SECONDS - (ttl_ms / 1000)
                    if elapsed_seconds < threshold_seconds:
                        continue

                    # A stuck job with no resolvable name is still a stuck job.
                    function = await self._get_job_function(job_id) or "unknown"

                    stuck_jobs.append(
                        {
                            "job_id": job_id,
                            "function": function,
                            "start_time": (
                                now - timedelta(seconds=elapsed_seconds)
                            ).isoformat(),
                            "duration_minutes": int(elapsed_seconds / 60),
                        }
                    )
                except Exception as e:
                    logger.debug(f"Error checking in-progress job {key}: {e}")
                    continue

            return stuck_jobs
        except Exception as e:
            logger.error(f"Error getting stuck jobs: {e}")
            return []

    async def get_worker_status(self) -> list[dict]:
        """
        Get worker status from arq's heartbeat key.

        arq writes exactly one key per queue, `<queue_name>:health-check`,
        psetex'd with TTL `(health_check_interval + 1) * 1000` ms. Key
        existence is therefore the freshness signal; the value is a
        human-readable info string and must not be parsed as a timestamp.

        With N workers overwriting one key, the only honest report is 0 or 1.

        Returns:
            List of worker status dictionaries (empty or a single entry)
        """
        if not await self._is_available():
            return []

        assert self._redis is not None

        try:
            heartbeat = await self._redis.get(ARQ_HEALTH_CHECK_KEY)
            if heartbeat is None:
                return []

            ttl_ms = await self._redis.pttl(ARQ_HEALTH_CHECK_KEY)

            return [
                {
                    "worker_id": ARQ_HEALTH_CHECK_KEY,
                    "is_online": True,
                    "info": heartbeat,
                    "seconds_to_heartbeat_expiry": (
                        int(ttl_ms / 1000) if ttl_ms and ttl_ms > 0 else None
                    ),
                }
            ]
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return []

    async def get_workers_online_count(self) -> int:
        """
        Get count of workers that are online.

        Returns:
            Number of online workers
        """
        workers = await self.get_worker_status()
        return len([w for w in workers if w.get("is_online", False)])

    async def get_workers_offline_count(self) -> int:
        """
        Get count of workers that are offline.

        Returns:
            Number of offline workers
        """
        workers = await self.get_worker_status()
        return len([w for w in workers if not w.get("is_online", False)])

    async def check_health(
        self,
        depth_threshold: Optional[int] = None,
        stuck_threshold_minutes: Optional[int] = None,
    ) -> dict:
        """
        Perform comprehensive health check on the queue.

        Args:
            depth_threshold: Max acceptable queue depth
            stuck_threshold_minutes: Minutes after which job is stuck

        Returns:
            Dictionary with health status and details
        """
        depth_threshold = depth_threshold or self.DEPTH_THRESHOLD
        stuck_threshold = stuck_threshold_minutes or self.STUCK_JOB_MINUTES

        queue_depth = await self.get_queue_depth()
        stuck_jobs = await self.get_stuck_jobs(stuck_threshold)
        workers = await self.get_worker_status()

        online_workers = len([w for w in workers if w.get("is_online", False)])
        offline_workers = len([w for w in workers if not w.get("is_online", False)])

        # Determine overall health
        issues = []

        if queue_depth > depth_threshold:
            issues.append(
                f"Queue depth ({queue_depth}) exceeds threshold ({depth_threshold})"
            )

        if stuck_jobs:
            issues.append(f"{len(stuck_jobs)} stuck jobs detected")

        # An absent heartbeat produces an empty worker list, so the alarm must
        # be driven off online_workers, not offline_workers.
        if online_workers == 0:
            issues.append("No workers are online")

        is_healthy = len(issues) == 0

        return {
            "is_healthy": is_healthy,
            "issues": issues,
            "queue_depth": queue_depth,
            "depth_threshold": depth_threshold,
            "stuck_jobs_count": len(stuck_jobs),
            "stuck_jobs": stuck_jobs[:10],  # Limit to first 10
            "workers_online": online_workers,
            "workers_offline": offline_workers,
            "total_workers": len(workers),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }


# Singleton instance
queue_health_service = QueueHealthService()
