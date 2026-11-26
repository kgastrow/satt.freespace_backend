"""
ARQ worker settings and configuration.
Defines task functions, cron jobs, and worker lifecycle hooks.
"""

from urllib.parse import urlparse

from arq.connections import RedisSettings

from src.constants.queues import (
    ARQ_HEALTH_CHECK_INTERVAL_SECONDS,
    ARQ_JOB_TIMEOUT_SECONDS,
    ARQ_QUEUE_NAME,
)
from src.core.config import settings
from src.logger.logger import Logger as logger


def get_redis_settings() -> RedisSettings:
    """
    Parse Redis URL and create RedisSettings for ARQ worker.

    Returns:
        RedisSettings configured from ARQ_REDIS_URL or REDIS_URL
    """
    # Use dedicated ARQ Redis URL if available, otherwise fall back to main REDIS_URL
    redis_url = (
        settings.ARQ_REDIS_URL
        if hasattr(settings, "ARQ_REDIS_URL") and settings.ARQ_REDIS_URL
        else settings.REDIS_URL
    )

    # Parse the Redis URL
    parsed = urlparse(redis_url)

    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int(parsed.path.lstrip("/")) if parsed.path else 0,
        password=parsed.password,
        conn_timeout=5,
        conn_retries=3,
        conn_retry_delay=1,
    )


async def startup(ctx):
    """
    Worker startup hook - initialize async resources.

    Args:
        ctx: ARQ worker context dictionary
    """
    from src.database import AsyncSessionLocal
    from src.services.cache import cache_service
    from src.services.job_stats import job_stats_service
    from src.workers.job_metrics import set_worker_active

    # Initialize cache service
    await cache_service.connect()

    # Initialize job stats service for dashboard metrics
    await job_stats_service.connect()

    # Store session factory in context for tasks to use
    ctx["session_factory"] = AsyncSessionLocal

    # Mark worker as active for metrics
    set_worker_active(True)

    # Initialize file storage (S3 or local fallback) for file-related tasks
    try:
        from src.services.files.file_manager import init_file_manager

        s3_configured = bool(settings.S3_BUCKET and settings.AWS_ACCESS_KEY_ID)

        if s3_configured:
            from src.services.files.s3_storage import init_s3_storage

            storage = init_s3_storage(
                bucket=settings.S3_BUCKET,
                region=settings.S3_REGION,
                access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                enabled=True,
            )
            init_file_manager(storage)
            logger.info("ARQ worker: File manager initialized with S3 storage")
        else:
            from src.services.files.local_storage import init_local_storage

            local_enabled = settings.LOCAL_STORAGE_ENABLED or not s3_configured

            # Backend origin: local_storage appends /api/v1/files/... to this.
            storage = init_local_storage(
                storage_path=settings.LOCAL_STORAGE_PATH,
                base_url=settings.PUBLIC_URL_BACKEND,
                enabled=local_enabled,
            )
            init_file_manager(storage)
            logger.info(
                f"ARQ worker: File manager initialized with local storage at {settings.LOCAL_STORAGE_PATH}"
            )
    except Exception as e:
        logger.warning(f"ARQ worker: Failed to initialize file manager: {e}")

    # Register cron job handlers with the scheduler service
    from src.services.cron_scheduler import cron_scheduler_service

    cron_scheduler_service.register_all_handlers()

    logger.info("ARQ worker started successfully")


async def shutdown(ctx):
    """
    Worker shutdown hook - cleanup resources.

    Args:
        ctx: ARQ worker context dictionary
    """
    from src.services.cache import cache_service
    from src.services.job_stats import job_stats_service
    from src.workers.job_metrics import set_worker_active

    # Mark worker as inactive for metrics
    set_worker_active(False)

    # Cleanup cache service
    await cache_service.disconnect()

    # Cleanup job stats service
    await job_stats_service.disconnect()

    logger.info("ARQ worker shutdown complete")


class WorkerSettings:
    """
    ARQ worker configuration.
    This class is used by the arq CLI to configure the worker.

    IMPORTANT: arq's `get_kwargs` builds the Worker kwargs from
    `settings_cls.__dict__` - the class's OWN attribute dict. Attributes that
    exist only on a base class are dropped without warning and arq's defaults
    apply instead. Any setting added here must also be re-declared on the
    concrete `WorkerSettings` in `src/workers/worker.py`.
    """

    # Redis connection settings
    redis_settings = get_redis_settings()

    # Use app-specific queue name to prevent job stealing by other ARQ workers
    # sharing the same Redis instance
    queue_name = ARQ_QUEUE_NAME

    # Task functions to register (imported in worker.py to avoid circular imports)
    functions: list = []  # Will be populated in worker.py

    # Cron jobs (scheduled tasks)
    cron_jobs: list = []  # Will be populated in worker.py

    # Worker lifecycle hooks
    on_startup = startup
    on_shutdown = shutdown

    # Worker settings
    max_jobs = 10  # Maximum concurrent jobs
    job_timeout = ARQ_JOB_TIMEOUT_SECONDS  # 5 minutes default timeout
    keep_result = 3600  # Keep results for 1 hour
    max_tries = 3  # Retry failed jobs up to 3 times

    # Polling settings
    poll_delay = 0.5  # Poll Redis every 500ms
    queue_read_limit = 10  # Read up to 10 jobs at once

    # Heartbeat. arq's default of 3600s makes the health-check key's TTL an
    # hour, so any liveness check tighter than that reads a live worker as
    # offline.
    health_check_interval = ARQ_HEALTH_CHECK_INTERVAL_SECONDS
