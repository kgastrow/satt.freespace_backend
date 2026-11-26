"""
Metrics API serializers.
Pydantic models for system metrics response validation.
"""

from pydantic import BaseModel


class RequestMetrics(BaseModel):
    """Metrics for HTTP requests."""

    total: int
    rate_per_minute: float
    error_rate: float
    avg_latency_ms: float


class DatabaseMetrics(BaseModel):
    """Metrics for database connection pool."""

    pool_size: int
    connections_in_use: int
    connections_available: int


class CacheMetrics(BaseModel):
    """Metrics for cache operations."""

    hit_rate: float
    connected: bool


class UserMetrics(BaseModel):
    """Metrics for user activity."""

    active_count: int


class JobMetrics(BaseModel):
    """Metrics for background jobs."""

    pending: int
    in_progress: int
    failed_total: int
    queue_depth: int
    stuck_jobs_count: int
    workers_online: int


class SystemMetrics(BaseModel):
    """Metrics for system resources."""

    cpu_percent: float
    memory_percent: float
    uptime_seconds: float


class StorageMetrics(BaseModel):
    """Metrics for local file storage."""

    used_bytes: int
    total_bytes: int | None  # None if not configured
    usage_percent: float | None  # None if total not configured
    file_count: int
    media_count: int


class SecurityMetrics(BaseModel):
    """Metrics for security events."""

    failed_logins_24h: int
    failed_2fa_24h: int
    api_key_failures_24h: int
    brute_force_events: int


class NotificationMetrics(BaseModel):
    """Metrics for notification delivery."""

    email_success_rate: float
    sms_success_rate: float
    total_sent_24h: int
    total_failed_24h: int


class RateLimitMetrics(BaseModel):
    """Metrics for rate limit violations."""

    total_violations: int
    top_endpoints: dict[str, int]  # Top 5 endpoints by violations
    top_ips: dict[str, int]  # Top 5 IPs by violations


class MetricsSummaryResponse(BaseModel):
    """Response schema for aggregated system metrics."""

    requests: RequestMetrics
    database: DatabaseMetrics
    cache: CacheMetrics
    users: UserMetrics
    jobs: JobMetrics
    system: SystemMetrics
    storage: StorageMetrics
    security: SecurityMetrics
    notifications: NotificationMetrics
    rate_limit: RateLimitMetrics
