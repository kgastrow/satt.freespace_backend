"""
Background job metrics for Prometheus.
Provides decorators and functions to track ARQ job execution.
"""

from functools import wraps
import time
from typing import Any, Callable

from prometheus_client import Counter, Gauge, Histogram

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.middleware.metrics import INSTANCE_ID


# ==================== Job Metrics ====================

JOBS_ENQUEUED_TOTAL = Counter(
    "jobs_enqueued_total",
    "Total jobs enqueued",
    ["job_type"],
)

JOBS_COMPLETED_TOTAL = Counter(
    "jobs_completed_total",
    "Total jobs completed successfully",
    ["job_type"],
)

JOBS_FAILED_TOTAL = Counter(
    "jobs_failed_total",
    "Total jobs that failed",
    ["job_type", "error_type"],
)

JOBS_RETRIED_TOTAL = Counter(
    "jobs_retried_total",
    "Total job retries",
    ["job_type"],
)

JOBS_IN_PROGRESS = Gauge(
    "jobs_in_progress",
    "Jobs currently being processed",
    ["job_type", "instance_id"],
)

JOB_DURATION_SECONDS = Histogram(
    "job_duration_seconds",
    "Job execution duration in seconds",
    ["job_type"],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0],
)

JOB_QUEUE_DEPTH = Gauge(
    "job_queue_depth",
    "Number of jobs waiting in queue",
    ["queue_name"],
)

CRON_JOB_LAST_RUN = Gauge(
    "cron_job_last_run_timestamp",
    "Timestamp of last cron job execution",
    ["job_name"],
)

CRON_JOB_LAST_STATUS = Gauge(
    "cron_job_last_status",
    "Status of last cron job (1=success, 0=failure)",
    ["job_name"],
)

WORKER_ACTIVE = Gauge(
    "worker_active",
    "Whether the worker is active (1) or not (0)",
    ["instance_id"],
)


# ==================== Metric Recording Functions ====================


def record_job_enqueued(job_type: str) -> None:
    """Record that a job was enqueued."""
    if not settings.METRICS_ENABLED:
        return
    JOBS_ENQUEUED_TOTAL.labels(job_type=job_type).inc()


def record_job_completed(job_type: str, duration: float) -> None:
    """Record a successful job completion."""
    if not settings.METRICS_ENABLED:
        return
    JOBS_COMPLETED_TOTAL.labels(job_type=job_type).inc()
    JOB_DURATION_SECONDS.labels(job_type=job_type).observe(duration)


def record_job_failed(job_type: str, error_type: str) -> None:
    """Record a job failure."""
    if not settings.METRICS_ENABLED:
        return
    JOBS_FAILED_TOTAL.labels(job_type=job_type, error_type=error_type).inc()


def record_job_retry(job_type: str) -> None:
    """Record a job retry."""
    if not settings.METRICS_ENABLED:
        return
    JOBS_RETRIED_TOTAL.labels(job_type=job_type).inc()


def update_queue_depth(queue_name: str, depth: int) -> None:
    """Update the queue depth gauge."""
    if not settings.METRICS_ENABLED:
        return
    JOB_QUEUE_DEPTH.labels(queue_name=queue_name).set(depth)


def record_cron_job_run(job_name: str, success: bool) -> None:
    """Record a cron job execution."""
    if not settings.METRICS_ENABLED:
        return
    CRON_JOB_LAST_RUN.labels(job_name=job_name).set(time.time())
    CRON_JOB_LAST_STATUS.labels(job_name=job_name).set(1 if success else 0)


def set_worker_active(active: bool) -> None:
    """Set the worker active status."""
    if not settings.METRICS_ENABLED:
        return
    WORKER_ACTIVE.labels(instance_id=INSTANCE_ID).set(1 if active else 0)


# ==================== Database Recording ====================


async def _record_to_db(
    ctx: dict,
    job_type: str,
    status: str,
    duration_ms: float,
    error_type: str | None = None,
    error_message: str | None = None,
) -> None:
    """Record a background job execution to the database. Never raises."""
    try:
        session_factory = ctx.get("session_factory")
        if session_factory:
            from src.crud.background_job import record_bg_job_execution

            async with session_factory() as session:
                await record_bg_job_execution(
                    session,
                    job_type=job_type,
                    status=status,
                    duration_ms=duration_ms,
                    error_type=error_type,
                    error_message=error_message,
                )
    except Exception as e:
        logger.warning(f"Failed to record bg job execution to DB: {e}")


# ==================== Task Decorator ====================


def instrument_task(func: Callable) -> Callable:
    """
    Decorator to instrument ARQ tasks with metrics.

    Usage:
        @instrument_task
        async def my_task(ctx, arg1, arg2):
            ...

    Tracks:
        - Job execution time
        - Success/failure counts
        - In-progress jobs
        - Records stats to Redis for dashboard
        - Checks if job is disabled before execution
    """

    @wraps(func)
    async def wrapper(ctx, *args, **kwargs) -> Any:
        job_type = func.__name__

        # Check if job is disabled (always check, even if metrics disabled)
        try:
            from src.services.job_stats import job_stats_service

            if await job_stats_service.is_job_disabled(job_type):
                logger.info(f"Job {job_type} is disabled, skipping execution")
                return {"status": "skipped", "reason": "job_disabled"}
        except Exception as e:
            logger.warning(f"Failed to check job disabled status: {e}")

        # Prometheus-only switch. Redis stats and the database execution record
        # are the admin panel's data source and must be written regardless.
        # The per-call record_* helpers check this flag themselves; the raw
        # gauge below has to be guarded explicitly.
        metrics_enabled = settings.METRICS_ENABLED

        if metrics_enabled:
            JOBS_IN_PROGRESS.labels(job_type=job_type, instance_id=INSTANCE_ID).inc()
        start_time = time.perf_counter()

        try:
            result = await func(ctx, *args, **kwargs)
            duration = time.perf_counter() - start_time
            record_job_completed(job_type, duration)

            # Record to Redis for dashboard stats
            try:
                from src.services.job_stats import job_stats_service

                await job_stats_service.record_job_execution(
                    job_type=job_type,
                    status="success",
                    duration_ms=duration * 1000,
                )
            except Exception as e:
                logger.warning(f"Failed to record job stats: {e}")

            # Record to database for persistent stats
            await _record_to_db(ctx, job_type, "success", duration * 1000)

            return result

        except Exception as e:
            error_type = type(e).__name__
            record_job_failed(job_type, error_type)

            # Record failure to Redis for dashboard stats
            duration = time.perf_counter() - start_time
            try:
                from src.services.job_stats import job_stats_service

                await job_stats_service.record_job_execution(
                    job_type=job_type,
                    status="failure",
                    duration_ms=duration * 1000,
                )
            except Exception as stats_err:
                logger.warning(f"Failed to record job stats: {stats_err}")

            # Record to database for persistent stats
            await _record_to_db(
                ctx,
                job_type,
                "failure",
                duration * 1000,
                error_type=error_type,
                error_message=str(e)[:500],
            )

            # Check if this is a retry
            from arq import Retry

            if isinstance(e, Retry):
                record_job_retry(job_type)

            raise

        finally:
            if metrics_enabled:
                JOBS_IN_PROGRESS.labels(
                    job_type=job_type, instance_id=INSTANCE_ID
                ).dec()

    return wrapper


def instrument_cron_task(func: Callable) -> Callable:
    """
    Decorator to instrument cron tasks with metrics.
    Similar to instrument_task but also records cron-specific metrics.

    Usage:
        @instrument_cron_task
        async def cleanup_task(ctx):
            ...

    Tracks:
        - Job execution time
        - Success/failure counts
        - In-progress jobs
        - Records stats to Redis for dashboard
        - Checks if job is disabled before execution
    """

    @wraps(func)
    async def wrapper(ctx, *args, **kwargs) -> Any:
        job_name = func.__name__

        # Check if job is disabled (always check, even if metrics disabled)
        try:
            from src.services.job_stats import job_stats_service

            if await job_stats_service.is_job_disabled(job_name):
                logger.info(f"Cron job {job_name} is disabled, skipping execution")
                return {"status": "skipped", "reason": "job_disabled"}
        except Exception as e:
            logger.warning(f"Failed to check job disabled status: {e}")

        # Prometheus-only switch - see instrument_task.
        metrics_enabled = settings.METRICS_ENABLED

        if metrics_enabled:
            JOBS_IN_PROGRESS.labels(job_type=job_name, instance_id=INSTANCE_ID).inc()
        start_time = time.perf_counter()

        try:
            result = await func(ctx, *args, **kwargs)
            duration = time.perf_counter() - start_time
            record_job_completed(job_name, duration)
            record_cron_job_run(job_name, success=True)

            # Record to Redis for dashboard stats
            try:
                from src.services.job_stats import job_stats_service

                await job_stats_service.record_job_execution(
                    job_type=job_name,
                    status="success",
                    duration_ms=duration * 1000,
                )
            except Exception as e:
                logger.warning(f"Failed to record job stats: {e}")

            # Record to database for persistent stats
            await _record_to_db(ctx, job_name, "success", duration * 1000)

            return result

        except Exception as e:
            error_type = type(e).__name__
            record_job_failed(job_name, error_type)
            record_cron_job_run(job_name, success=False)

            # Record failure to Redis for dashboard stats
            duration = time.perf_counter() - start_time
            try:
                from src.services.job_stats import job_stats_service

                await job_stats_service.record_job_execution(
                    job_type=job_name,
                    status="failure",
                    duration_ms=duration * 1000,
                )
            except Exception as stats_err:
                logger.warning(f"Failed to record job stats: {stats_err}")

            # Record to database for persistent stats
            await _record_to_db(
                ctx,
                job_name,
                "failure",
                duration * 1000,
                error_type=error_type,
                error_message=str(e)[:500],
            )

            raise

        finally:
            if metrics_enabled:
                JOBS_IN_PROGRESS.labels(
                    job_type=job_name, instance_id=INSTANCE_ID
                ).dec()

    return wrapper
