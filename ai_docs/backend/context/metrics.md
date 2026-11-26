# Metrics and Monitoring

Prometheus metrics at `/metrics` endpoint. Config in `app/backend/src/core/config.py`.

## Configuration

```python
METRICS_ENABLED: bool = True
METRICS_ENDPOINT: str = "/metrics"
METRICS_EXCLUDED_PATHS: str = "/metrics,/health,/docs,/redoc,/openapi.json"
METRICS_SLOW_REQUEST_THRESHOLD: float = 1.0  # seconds
METRICS_SLOW_QUERY_THRESHOLD: float = 0.1  # seconds
METRICS_USER_ACTIVITY_WINDOW: int = 300  # 5 minutes
METRICS_INSTANCE_ID: str = ""  # Auto-generated: {hostname}-{pid}
```

## Module Structure

| Module | Path | Purpose |
|--------|------|---------|
| HTTP metrics | `src/middleware/metrics.py` | Request counts, latency, errors |
| DB metrics | `src/middleware/db_metrics.py` | Query instrumentation |
| Cache metrics | `src/middleware/cache_metrics.py` | Hit/miss rates |
| Job metrics | `src/workers/job_metrics.py` | Background job tracking |
| Security metrics | `src/middleware/security_metrics.py` | Auth failures, brute force |
| Rate limit metrics | `src/middleware/rate_limit_metrics.py` | Rate limit violations |
| Notification metrics | `src/middleware/notification_metrics.py` | Delivery tracking |
| User activity | `src/services/user_activity.py` | HyperLogLog user counting |

## HTTP Request Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | method, endpoint, status_code |
| `http_request_duration_seconds` | Histogram | method, endpoint |
| `http_requests_in_progress` | Gauge | method, endpoint |
| `http_request_size_bytes` | Histogram | method, endpoint |
| `http_response_size_bytes` | Histogram | method, endpoint |
| `http_slow_requests_total` | Counter | method, endpoint |
| `http_errors_total` | Counter | method, endpoint, status_code, error_type |
| `exceptions_total` | Counter | exception_type, endpoint |
| `auth_failures_total` | Counter | failure_reason |
| `validation_errors_total` | Counter | endpoint |
| `concurrent_requests` | Gauge | - |
| `active_users_current` | Gauge | window |
| `app_start_time_seconds` | Gauge | instance_id |

```python
from src.middleware import record_auth_failure, record_exception
record_auth_failure("invalid_token")
record_exception("ValueError", "/api/users")
```

## Database Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `db_queries_total` | Counter | operation |
| `db_query_duration_seconds` | Histogram | operation |
| `db_slow_queries_total` | Counter | operation |
| `db_query_errors_total` | Counter | operation, error_type |
| `db_connection_pool_size` | Gauge | pool_name |
| `db_connections_checked_out` | Gauge | pool_name |
| `db_connections_overflow` | Gauge | pool_name |
| `db_connection_checkout_time_seconds` | Histogram | pool_name |
| `db_transactions_total` | Counter | status |

```python
from src.middleware import get_pool_stats
stats = get_pool_stats(engine)  # {"pool_size": 5, "checked_out": 2, "overflow": 0, "checked_in": 3}
```

## Cache Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `cache_operations_total` | Counter | operation, cache_type, result |
| `cache_operation_duration_seconds` | Histogram | operation, cache_type |
| `cache_keys_total` | Gauge | cache_type |
| `cache_memory_bytes` | Gauge | - |
| `cache_connected` | Gauge | - |

Cache types: `jwt`, `user`, `organization`, `roles`

## Background Job Metrics

| Metric | Type | Labels |
|--------|------|--------|
| `jobs_enqueued_total` | Counter | job_type |
| `jobs_completed_total` | Counter | job_type |
| `jobs_failed_total` | Counter | job_type, error_type |
| `jobs_retried_total` | Counter | job_type |
| `jobs_in_progress` | Gauge | job_type, instance_id |
| `job_duration_seconds` | Histogram | job_type |
| `job_queue_depth` | Gauge | queue_name |
| `cron_job_last_run_timestamp` | Gauge | job_name |
| `cron_job_last_status` | Gauge | job_name |
| `worker_active` | Gauge | instance_id |

```python
from src.workers.job_metrics import instrument_task, instrument_cron_task

@instrument_task
async def send_email_task(ctx, to: str, subject: str): ...

@instrument_cron_task
async def cleanup_task(ctx): ...
```

## Security Metrics

**Status: Integrated** - Used in `auth.py`, `deps.py`, `brute_force_detector.py`

| Metric | Type | Labels |
|--------|------|--------|
| `failed_login_attempts_total` | Counter | organization_id, reason |
| `two_factor_failures_total` | Counter | organization_id, reason |
| `api_key_auth_failures_total` | Counter | organization_id, reason |
| `brute_force_events_total` | Counter | ip_address, event_type |

```python
from src.middleware.security_metrics import record_failed_login, record_2fa_failure, record_api_key_failure, record_brute_force_event
record_failed_login(org_id, ip, "invalid_credentials")
record_2fa_failure(org_id, "invalid_code")
record_api_key_failure(org_id, "expired")
record_brute_force_event(ip, "threshold_exceeded")

# Aggregation functions (used in /api/v1/metrics endpoint)
from src.middleware.security_metrics import get_failed_logins_count, get_2fa_failures_count, get_api_key_failures_count, get_brute_force_events_count
```

## Rate Limit Metrics

**Status: Not Integrated** - Module exists but functions are never called

| Metric | Type | Labels |
|--------|------|--------|
| `rate_limit_violations_total` | Counter | organization_id, ip_address, endpoint |
| `rate_limit_requests_total` | Counter | endpoint, allowed |

```python
from src.middleware.rate_limit_metrics import record_rate_limit_violation, record_rate_limit_check
record_rate_limit_violation(org_id, ip, endpoint)
record_rate_limit_check(endpoint, allowed=True)

# Aggregation functions
from src.middleware.rate_limit_metrics import get_violations_count, get_violations_by_endpoint, get_violations_by_ip
```

## Notification Metrics

**Status: Partial** - Aggregation functions used in cron health checks; recording functions not called

| Metric | Type | Labels |
|--------|------|--------|
| `notification_delivery_total` | Counter | channel, status |
| `notification_delivery_duration_seconds` | Histogram | channel |
| `email_delivery_failures_total` | Counter | provider, error_type |
| `sms_delivery_total` | Counter | provider, status |
| `whatsapp_delivery_total` | Counter | provider, status |

```python
from src.middleware.notification_metrics import record_notification_delivery, record_email_failure, record_sms_delivery, record_whatsapp_delivery
record_notification_delivery("email", "sent", duration=0.5)
record_email_failure("smtp", "connection")

# Context manager for tracking delivery time
with track_notification_delivery("email") as tracker:
    result = await send_email(...)
    tracker["status"] = "sent" if result.success else "failed"

# Aggregation functions (used in cron health checks and /api/v1/metrics)
from src.middleware.notification_metrics import get_notification_delivery_count, calculate_success_rate
```

## User Activity Tracking

```python
from src.services.user_activity import user_activity_service
await user_activity_service.record_activity(user_id, org_id)
count = await user_activity_service.get_active_user_count(org_id="...")
```

## Adding New Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

MY_COUNTER = Counter("my_metric_total", "Description", ["label1"])
MY_COUNTER.labels(label1="value").inc()

MY_HISTOGRAM = Histogram("my_duration_seconds", "Description", ["label1"])
MY_HISTOGRAM.labels(label1="value").observe(duration)

MY_GAUGE = Gauge("my_current_value", "Description", ["label1"])
MY_GAUGE.labels(label1="value").set(value)
```

## Gotchas

| Issue | Solution |
|-------|----------|
| High-cardinality labels | Never use user IDs, session IDs, or request IDs as labels |
| Path normalization | Use `get_path_template()` to replace UUIDs/IDs with `{id}` |
| Metrics failures | All recording functions catch exceptions silently - metrics never crash the app |
| NullPool with PgBouncer | Pool stats return zeros when using NullPool (PgBouncer handles pooling) |

## Security Considerations

- Rate limit the `/metrics` endpoint (default: 60/minute) to prevent reconnaissance
- Exclude sensitive paths from request logging
- Organization IDs in security metrics help identify targeted attacks
- IP addresses in brute force metrics enable blocking decisions
