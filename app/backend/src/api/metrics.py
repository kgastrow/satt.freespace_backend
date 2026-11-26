"""
Metrics API endpoint for system monitoring.
Returns aggregated metrics for the admin dashboard.

Security Note: This endpoint exposes system-level information that could aid reconnaissance.
Access should be carefully controlled - only grant 'metrics:read' permission to trusted admin users.
"""

import time
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request
import psutil
from sqlalchemy import func, select

from src.api.deps import CurrentUser, get_session, require_permission
from src.core.config import settings
from src.core.rate_limit import limiter
from src.database import async_engine
from src.logger.logger import Logger
from src.middleware.cache_metrics import CACHE_OPERATIONS_TOTAL
from src.middleware.db_metrics import get_pool_stats
from src.middleware.metrics import (
    APP_START_TIME,
    HTTP_ERRORS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
    INSTANCE_ID,
)
from src.middleware.notification_metrics import (
    calculate_success_rate,
    get_notification_delivery_count,
)
from src.middleware.rate_limit_metrics import (
    get_violations_by_endpoint,
    get_violations_by_ip,
    get_violations_count,
)
from src.middleware.security_metrics import (
    get_2fa_failures_count,
    get_api_key_failures_count,
    get_brute_force_events_count,
    get_failed_logins_count,
)
from src.serialisers.metrics import (
    CacheMetrics,
    DatabaseMetrics,
    JobMetrics,
    MetricsSummaryResponse,
    NotificationMetrics,
    RateLimitMetrics,
    RequestMetrics,
    SecurityMetrics,
    StorageMetrics,
    SystemMetrics,
    UserMetrics,
)
from src.services.cache import cache_service
from src.services.user_activity import user_activity_service
from src.workers.job_metrics import (
    JOBS_COMPLETED_TOTAL,
    JOBS_ENQUEUED_TOTAL,
    JOBS_FAILED_TOTAL,
    JOBS_IN_PROGRESS,
)


router = APIRouter(prefix="/metrics", tags=["metrics"])


def _get_counter_total(counter) -> int:
    """Get total count from a Prometheus Counter across all label combinations."""
    total = 0
    try:
        # Access the internal metrics storage
        for metric in counter.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    total += int(sample.value)
    except Exception as e:
        Logger.debug(f"Failed to read counter metric: {e}")
    return total


def _get_gauge_value(gauge, labels: Optional[dict] = None) -> float:
    """Get value from a Prometheus Gauge."""
    try:
        if labels:
            return gauge.labels(**labels)._value.get()
        # Get first value if no labels specified
        for metric in gauge.collect():
            for sample in metric.samples:
                return sample.value
    except Exception as e:
        Logger.debug(f"Failed to read gauge metric: {e}")
    return 0.0


def _get_histogram_avg(histogram) -> float:
    """Calculate average from a Prometheus Histogram."""
    total_sum = 0.0
    total_count = 0
    try:
        for metric in histogram.collect():
            for sample in metric.samples:
                if sample.name.endswith("_sum"):
                    total_sum += sample.value
                elif sample.name.endswith("_count"):
                    total_count += int(sample.value)
        if total_count > 0:
            return total_sum / total_count
    except Exception as e:
        Logger.debug(f"Failed to calculate histogram average: {e}")
    return 0.0


def _get_counter_by_label(counter, label_name: str, label_values: list) -> int:
    """Get counter total filtered by specific label values."""
    total = 0
    try:
        for metric in counter.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    labels = sample.labels
                    if labels.get(label_name) in label_values:
                        total += int(sample.value)
    except Exception as e:
        Logger.debug(f"Failed to read counter by label: {e}")
    return total


def _calculate_cache_hit_rate() -> float:
    """Calculate cache hit rate from cache operations metrics."""
    hits = 0
    misses = 0
    try:
        for metric in CACHE_OPERATIONS_TOTAL.collect():
            for sample in metric.samples:
                if sample.name.endswith("_total"):
                    result = sample.labels.get("result", "")
                    if result == "hit":
                        hits += int(sample.value)
                    elif result == "miss":
                        misses += int(sample.value)
        total = hits + misses
        if total > 0:
            return round((hits / total) * 100, 2)
    except Exception as e:
        Logger.debug(f"Failed to calculate cache hit rate: {e}")
    return 0.0


def _get_jobs_in_progress() -> int:
    """Get total jobs currently in progress across all instances."""
    total = 0
    try:
        for metric in JOBS_IN_PROGRESS.collect():
            for sample in metric.samples:
                total += int(sample.value)
    except Exception as e:
        Logger.debug(f"Failed to read jobs in progress: {e}")
    return total


def _estimate_pending_jobs() -> int:
    """
    Estimate pending jobs based on enqueued - completed - failed.
    This is an approximation since we don't have direct queue access from the API.
    """
    enqueued = _get_counter_total(JOBS_ENQUEUED_TOTAL)
    completed = _get_counter_total(JOBS_COMPLETED_TOTAL)
    failed = _get_counter_total(JOBS_FAILED_TOTAL)
    in_progress = _get_jobs_in_progress()

    pending = enqueued - completed - failed - in_progress
    return max(0, pending)


@router.get("/summary", response_model=MetricsSummaryResponse)
@limiter.limit(settings.RATE_LIMIT_METRICS)
async def get_metrics_summary(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("metrics:read"))],
    session=Depends(get_session),
) -> MetricsSummaryResponse:
    """
    Get aggregated system metrics summary.

    Requires metrics:read permission.

    Returns metrics for:
    - HTTP requests (total, rate, errors, latency)
    - Database (connection pool stats)
    - Cache (hit rate, connection status)
    - Users (active user count)
    - Jobs (pending, in progress, failed)
    - System (CPU, memory, uptime)
    - Storage (local storage used/available)
    """
    # Request metrics
    total_requests = _get_counter_total(HTTP_REQUESTS_TOTAL)
    total_errors = _get_counter_total(HTTP_ERRORS_TOTAL)
    avg_latency = _get_histogram_avg(HTTP_REQUEST_DURATION_SECONDS)

    # Calculate error rate
    error_rate = 0.0
    if total_requests > 0:
        error_rate = round((total_errors / total_requests) * 100, 2)

    # Estimate requests per minute (rough approximation based on uptime)
    start_time = _get_gauge_value(APP_START_TIME, {"instance_id": INSTANCE_ID})
    uptime_seconds = time.time() - start_time if start_time > 0 else 1
    rate_per_minute = (
        round((total_requests / uptime_seconds) * 60, 2) if uptime_seconds > 0 else 0.0
    )

    request_metrics = RequestMetrics(
        total=total_requests,
        rate_per_minute=rate_per_minute,
        error_rate=error_rate,
        avg_latency_ms=round(avg_latency * 1000, 2),  # Convert to ms
    )

    # Database metrics
    pool_stats = get_pool_stats(async_engine.sync_engine)
    if "error" in pool_stats:
        # Fallback if pool stats aren't available
        database_metrics = DatabaseMetrics(
            pool_size=0, connections_in_use=0, connections_available=0
        )
    else:
        database_metrics = DatabaseMetrics(
            pool_size=pool_stats.get("pool_size", 0),
            connections_in_use=pool_stats.get("checked_out", 0),
            connections_available=pool_stats.get("checked_in", 0),
        )

    # Cache metrics
    cache_hit_rate = _calculate_cache_hit_rate()
    cache_connected = False
    try:
        if cache_service._redis:
            await cache_service._redis.ping()
            cache_connected = True
    except Exception as e:
        Logger.debug(f"Cache connection check failed: {e}")

    cache_metrics = CacheMetrics(hit_rate=cache_hit_rate, connected=cache_connected)

    # User metrics - get active user count from the activity service
    active_user_count = await user_activity_service.get_active_user_count()
    user_metrics = UserMetrics(active_count=active_user_count)

    # Job metrics with queue health
    pending_jobs = _estimate_pending_jobs()
    in_progress_jobs = _get_jobs_in_progress()
    failed_jobs = _get_counter_total(JOBS_FAILED_TOTAL)

    # Get queue health data
    from src.services.queue_health import queue_health_service

    queue_depth = 0
    stuck_jobs_count = 0
    workers_online = 0
    try:
        await queue_health_service.connect()
        queue_depth = await queue_health_service.get_queue_depth()
        stuck_jobs = await queue_health_service.get_stuck_jobs()
        stuck_jobs_count = len(stuck_jobs)
        workers_online = await queue_health_service.get_workers_online_count()
    except Exception as e:
        Logger.debug(f"Queue health check failed: {e}")

    job_metrics = JobMetrics(
        pending=pending_jobs,
        in_progress=in_progress_jobs,
        failed_total=failed_jobs,
        queue_depth=queue_depth,
        stuck_jobs_count=stuck_jobs_count,
        workers_online=workers_online,
    )

    # System metrics using psutil
    cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
    memory = psutil.virtual_memory()
    memory_percent = memory.percent

    system_metrics = SystemMetrics(
        cpu_percent=round(cpu_percent, 2),
        memory_percent=round(memory_percent, 2),
        uptime_seconds=round(uptime_seconds, 0),
    )

    # Storage metrics - query File table (media was merged into files)
    from src.crud.system_config import get_system_config_by_key
    from src.models.file import File

    # Get file storage usage (includes media files)
    file_result = await session.execute(
        select(
            func.coalesce(func.sum(File.size_bytes), 0).label("total_size"),
            func.count(File.id).label("file_count"),
        ).where(File.deleted_time.is_(None))
    )
    file_row = file_result.first()
    file_storage = int(file_row.total_size) if file_row else 0
    file_count = int(file_row.file_count) if file_row else 0

    # Count media files separately (files with media_use set)
    media_result = await session.execute(
        select(func.count(File.id).label("media_count")).where(
            File.deleted_time.is_(None),
            File.media_use.isnot(None),
        )
    )
    media_row = media_result.first()
    media_count = int(media_row.media_count) if media_row else 0

    used_bytes = file_storage

    # Get total allocated bytes from SystemConfig
    total_bytes_config = await get_system_config_by_key(
        session, "local_storage.total_allocated_bytes"
    )
    total_bytes: int | None = None
    usage_percent: float | None = None

    if total_bytes_config and total_bytes_config.value:
        try:
            total_bytes = int(total_bytes_config.value)
            if total_bytes > 0:
                usage_percent = round((used_bytes / total_bytes) * 100, 2)
        except (ValueError, TypeError):
            pass

    storage_metrics = StorageMetrics(
        used_bytes=used_bytes,
        total_bytes=total_bytes,
        usage_percent=usage_percent,
        file_count=file_count,
        media_count=media_count,
    )

    # Security metrics
    security_metrics = SecurityMetrics(
        failed_logins_24h=get_failed_logins_count(),
        failed_2fa_24h=get_2fa_failures_count(),
        api_key_failures_24h=get_api_key_failures_count(),
        brute_force_events=get_brute_force_events_count(),
    )

    # Notification metrics
    email_success_rate = calculate_success_rate("email")
    sms_success_rate = calculate_success_rate("sms")
    email_counts = get_notification_delivery_count("email")
    sms_counts = get_notification_delivery_count("sms")
    total_sent = email_counts.get("sent", 0) + sms_counts.get("sent", 0)
    total_failed = email_counts.get("failed", 0) + sms_counts.get("failed", 0)

    notification_metrics = NotificationMetrics(
        email_success_rate=email_success_rate,
        sms_success_rate=sms_success_rate,
        total_sent_24h=total_sent,
        total_failed_24h=total_failed,
    )

    # Rate limit metrics
    total_violations = get_violations_count()
    violations_by_endpoint = get_violations_by_endpoint()
    violations_by_ip = get_violations_by_ip()

    # Get top 5 endpoints by violations
    top_endpoints = dict(
        sorted(violations_by_endpoint.items(), key=lambda x: x[1], reverse=True)[:5]
    )
    # Get top 5 IPs by violations
    top_ips = dict(
        sorted(violations_by_ip.items(), key=lambda x: x[1], reverse=True)[:5]
    )

    rate_limit_metrics = RateLimitMetrics(
        total_violations=total_violations,
        top_endpoints=top_endpoints,
        top_ips=top_ips,
    )

    return MetricsSummaryResponse(
        requests=request_metrics,
        database=database_metrics,
        cache=cache_metrics,
        users=user_metrics,
        jobs=job_metrics,
        system=system_metrics,
        storage=storage_metrics,
        security=security_metrics,
        notifications=notification_metrics,
        rate_limit=rate_limit_metrics,
    )
