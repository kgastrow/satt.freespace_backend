# Background Jobs with ARQ

Async job processing via ARQ (Asyncio Redis Queue) in `app/backend/src/workers/`.

## Directory Structure

```
app/backend/src/workers/
├── settings.py           # Redis settings, lifecycle hooks, base WorkerSettings
├── worker.py             # Worker entry point with task/cron registration
├── tasks.py              # Core tasks (email, notifications, files, cleanup)
├── payment_tasks.py      # Payment webhooks and reconciliation
├── two_factor_tasks.py   # 2FA enforcement and notifications
├── request_log_cleanup.py# Request log cleanup
└── job_metrics.py        # Prometheus instrumentation decorators
```

## Decision Matrix: ARQ Cron vs CronSchedulerService

| Criteria | ARQ Cron (hardcoded) | CronSchedulerService (DB-driven) |
|----------|---------------------|----------------------------------|
| **Frequency** | Sub-minute (e.g., every 15 sec) | Minute or longer |
| **Admin configurability** | None - code changes only | Full UI control |
| **Schedule changes** | Requires deploy | Live updates |
| **Execution history** | Prometheus only | DB + Prometheus |
| **Use when** | Metrics collection, scheduler itself | Business logic cleanup, notifications |

**Rule of thumb:** Use CronSchedulerService unless you need sub-minute frequency or it's the scheduler itself.

## Job Disable Feature

Jobs can be disabled at runtime via `job_stats_service.is_job_disabled()`. The `instrument_task` and `instrument_cron_task` decorators check this before execution:

```python
# When disabled, job returns immediately:
{"status": "skipped", "reason": "job_disabled"}
```

**How it works:**
- Stores enabled/disabled state in Redis: `job_enabled_cache:{job_type}`
- Cache TTL: 5 minutes
- Default: enabled (if Redis unavailable or cache miss)
- Toggled via admin API which calls `job_stats_service.set_job_enabled_cache()`

## Available Tasks

| Task | Purpose |
|------|---------|
| `send_email_task` | Send generic email |
| `send_otp_email_task` | Send OTP verification email |
| `send_password_reset_email_task` | Send password reset email |
| `send_notification_task` | Process single notification (email/SMS/WhatsApp) |
| `process_bulk_notification_task` | Process bulk notification batch (100/batch) |
| `check_delivery_status_task` | Check delivery status from provider |
| `process_file_upload_task` | Post-upload processing (metadata, thumbnails) |
| `recalculate_usage_task` | Recalculate org file usage stats |
| `cleanup_old_request_logs_task` | Delete old request logs per retention |
| `process_data_export_task` | Generate user data export ZIP |
| `notify_2fa_mandatory_change` | Notify users of mandatory 2FA policy |
| `check_2fa_grace_period_expired` | Check for expired 2FA grace periods |
| `process_payment_webhook_task` | Process payment provider webhook |
| `sync_payment_status_task` | Sync payment status with provider |
| `reconcile_pending_payments_task` | Reconcile pending payments (missed webhooks) |

## Scheduled Jobs (Cron)

**Hardcoded ARQ Crons (sub-minute frequency):**

| Task | Schedule | Purpose |
|------|----------|---------|
| `collect_metrics_task` | Every 15 sec | Collect Prometheus metrics |
| `system_cron_scheduler_task` | Every minute | Check for due cron jobs |
| `reconcile_pending_payments_task` | Every 15 min | Reconcile pending payments |

**Database-Driven Crons (via CronSchedulerService):**

| Code | Default Schedule | Purpose |
|------|------------------|---------|
| `cleanup_expired_otps` | */30 * * * * | Delete expired OTPs |
| `cleanup_expired_refresh_tokens` | 0 * * * * | Delete expired tokens |
| `cleanup_old_notifications` | 0 2 * * * | Delete old notifications |
| `cleanup_deleted_files` | 0 3 * * * | Hard delete files past retention |
| `check_2fa_grace_period` | 0 1 * * * | Check expired 2FA grace periods |
| `cleanup_old_request_logs` | 0 4 * * * | Delete old request logs |

## Configuration and Timeouts

```python
# app/backend/src/workers/settings.py - Base settings
class WorkerSettings:
    redis_settings = get_redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10           # Maximum concurrent jobs
    job_timeout = 300       # 5 minutes default (seconds)
    keep_result = 3600      # 1 hour result retention
    max_tries = 3           # Retry up to 3 times
    poll_delay = 0.5        # Poll every 500ms
    queue_read_limit = 10   # Read up to 10 jobs at once
```

**Per-task timeout override:** Set `_job_timeout` on task function or pass `_job_timeout` kwarg when enqueueing:

```python
# Method 1: Function attribute
async def long_running_task(ctx, data: str):
    ...
long_running_task._job_timeout = 600  # 10 minutes

# Method 2: At enqueue time
await task_queue.enqueue_job("my_task", data, _job_timeout=600)
```

## Task Parameter Serialization

**All task parameters must be JSON-serializable.** ARQ serializes args/kwargs to Redis.

```python
# WRONG - UUID objects aren't JSON-serializable
await task_queue.enqueue_job("process_file_task", file_id=file.id)  # UUID fails!

# CORRECT - Convert to string
await task_queue.enqueue_job("process_file_task", file_id=str(file.id))

# WRONG - datetime objects
await task_queue.enqueue_job("schedule_task", run_at=datetime.now())  # fails!

# CORRECT - ISO string
await task_queue.enqueue_job("schedule_task", run_at=datetime.now().isoformat())
```

**Serializable types:** str, int, float, bool, None, list, dict (with serializable values)

## Defining Tasks

```python
# On-demand task pattern
async def send_email_task(ctx, to: str, subject: str, body: str, html_body: Optional[str] = None):
    """ctx contains session_factory from startup hook."""
    try:
        from src.services.email import email_service
        success = await email_service.send_email(to=to, subject=subject, body=body, html_body=html_body)
        if success:
            return {"status": "sent", "to": to}
        raise Retry(defer=30)  # Retry in 30 seconds
    except Exception:
        raise Retry(defer=60)  # Retry in 60 seconds

# Cron task pattern - use session_factory from context
async def cleanup_expired_otps_task(ctx) -> dict:
    session_factory = ctx.get("session_factory")
    if not session_factory:
        raise RuntimeError("Database session factory not available")

    async with session_factory() as session:
        try:
            # ... cleanup logic with batch processing
            return {"deleted_count": total_deleted}
        except Exception as exc:
            await session.rollback()
            raise
```

## Cron Task Wrapping Pattern

ARQ cron jobs require a specific wrapping pattern. The same wrapper must be used in both `functions` and `cron_jobs` lists:

```python
# worker.py - CORRECT pattern
from src.workers.job_metrics import instrument_cron_task

# Step 1: Create ONE wrapped instance
_cleanup_expired_otps = instrument_cron_task(cleanup_expired_otps_task)

class WorkerSettings(BaseWorkerSettings):
    # Step 2: Use same wrapper in functions (for task lookup)
    functions = [
        _cleanup_expired_otps,  # Same wrapper instance
        # ...
    ]

    # Step 3: Use same wrapper in cron_jobs (for scheduling)
    # NOTE: Do NOT wrap again or wrap here - use the pre-wrapped instance
    cron_jobs = [
        cron(_cleanup_expired_otps, minute={0, 30}),  # Same wrapper instance
    ]
```

**Why this matters:** ARQ `cron()` calls the function directly without looking it up in `functions`. If you use different wrappers, the `functions` version never gets called for cron jobs, and metrics/disable checks won't work.

## Enqueueing Jobs

```python
# app/backend/src/services/tasks.py
from src.services.tasks import task_queue

# Convenience methods
job_id = await task_queue.enqueue_email(to=email, subject="Welcome!", body="...")
job_id = await task_queue.enqueue_otp_email(to=email, otp_code="123456")
job_id = await task_queue.enqueue_password_reset_email(to=email, reset_token=token, reset_url=url)

# Generic method for any task (remember: params must be JSON-serializable!)
job_id = await task_queue.enqueue_job("send_notification_task", notification_id=str(notif.id))
job_id = await task_queue.enqueue_job("process_file_upload_task", file_id=str(file.id))

# Check job status
status = await task_queue.get_job_status(job_id)
# Returns: {"job_id": "...", "status": "complete|queued|in_progress|not_found", "result": ..., "error": ...}
```

## Running the Worker

```bash
# Development
arq src.workers.worker.WorkerSettings
arq src.workers.worker.WorkerSettings --verbose

# Production (systemd)
# /etc/systemd/system/ayzer-webapp-worker.service
[Service]
ExecStart=/opt/ayzer-webapp/backend/venv/bin/arq src.workers.worker.WorkerSettings
```

## Error Handling and Retries

```python
from arq import Retry

async def flaky_task(ctx, data: str) -> dict:
    try:
        result = await external_api_call(data)
        return {"status": "success", "result": result}
    except TemporaryError:
        raise Retry(defer=60)  # Retry in 60 seconds
    except PermanentError as e:
        return {"status": "failed", "error": str(e)}  # Don't retry
```

## Task Instrumentation

All tasks are wrapped with metrics decorators in `worker.py`:

```python
from src.workers.job_metrics import instrument_task, instrument_cron_task

# For on-demand tasks
functions = [instrument_task(send_email_task), ...]

# For cron tasks - wrap once, use in both functions and cron_jobs lists
_cleanup_expired_otps = instrument_cron_task(cleanup_expired_otps_task)
functions = [_cleanup_expired_otps, ...]
```

**What instrumentation provides:**
- Execution duration metrics (Prometheus histogram)
- Success/failure counts (Prometheus counters)
- In-progress job tracking (Prometheus gauge)
- Redis dashboard stats via `job_stats_service.record_job_execution()`
- **Job disable check** via `job_stats_service.is_job_disabled()`

## Best Practices

| Practice | Reason |
|----------|--------|
| Keep tasks idempotent | Tasks may be retried |
| Convert UUIDs to strings | JSON serialization requirement |
| Set appropriate timeouts | Based on expected execution time |
| Return error status vs raise | Graceful failure, no retry |
| Use Retry() for transient failures | Automatic retry with backoff |
| Batch process large datasets | Prevent OOM and lock contention |
| Separate Redis DBs | Cache (0) vs jobs (1) |

### Batch Processing Pattern

For cleanup tasks processing large record sets:

```python
async def cleanup_task(ctx) -> dict:
    BATCH_SIZE = 1000
    total_deleted = 0

    async with session_factory() as session:
        while True:
            result = await session.execute(
                select(Model.id)
                .where(Model.expired_at < now, Model.deleted_time.is_(None))
                .limit(BATCH_SIZE)
            )
            ids = [row[0] for row in result.all()]
            if not ids:
                break

            await session.execute(
                update(Model).where(Model.id.in_(ids)).values(deleted_time=now)
            )
            await session.commit()
            total_deleted += len(ids)

            if len(ids) < BATCH_SIZE:
                break

    return {"deleted_count": total_deleted}
```

## Gotchas

1. **Session factory required**: All tasks needing DB access must get `session_factory` from `ctx`. It's injected by the startup hook.

2. **Cron wrapper reuse**: Pre-wrap cron tasks and use the same wrapper in both `functions` and `cron_jobs` lists.

3. **Job disabled check**: `instrument_task` and `instrument_cron_task` automatically check if jobs are disabled via `job_stats_service.is_job_disabled()`.

4. **Soft deletes**: Use `deleted_time` column for soft deletes. Only `cleanup_deleted_files_task` performs hard deletes (after S3 cleanup).

5. **Retry vs return error**: Use `raise Retry(defer=N)` for transient failures that should retry. Return error dict for permanent failures.

6. **Parameter serialization**: All task parameters must be JSON-serializable. Convert UUIDs, datetimes, and custom objects to strings.

7. **Timeout selection**: Default is 5 minutes. Long-running tasks (exports, bulk operations) should set `_job_timeout` explicitly.
