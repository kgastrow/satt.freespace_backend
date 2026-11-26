# Cron Scheduler Service

Database-driven cron job management with admin UI configuration. **All scheduled tasks must use this system** (except sub-minute frequency jobs).

## Handler Signature

```python
# src/services/cron/<category>.py
async def my_handler(session: AsyncSession, parameters: dict[str, Any]) -> dict[str, Any]:
    # session: Managed by scheduler, auto-committed on success
    # parameters: From CronJobDefinition.parameters JSON column
    # Return: Result dict stored in CronJobExecution.result
    return {"deleted_count": count}
```

## Adding a New Cron Job

### 1. Create Handler (in appropriate `src/services/cron/<category>.py`)

```python
async def my_cleanup_handler(session: AsyncSession, parameters: dict[str, Any]) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=parameters.get("days", 7))
    result = await session.execute(
        select(MyModel).where(MyModel.created_time < cutoff, MyModel.deleted_time.is_(None))
    )
    items = result.scalars().all()
    for item in items:
        item.deleted_time = datetime.now(timezone.utc)
    return {"deleted_count": len(items)}
```

### 2. Register in Handler Registry (`src/services/cron_scheduler.py`)

Add to the `get_all_cron_handlers()` function:

```python
def get_all_cron_handlers() -> dict[str, JobHandler]:
    from src.services.cron_handlers import my_cleanup_handler
    return {
        # ... existing handlers ...
        "my_cleanup": my_cleanup_handler,
    }
```

### 3. Add Seed Data (`scripts/seed_data/cron_jobs.yaml`)

```yaml
- name: My Cleanup Job
  description: Remove old items from MyModel
  code: my_cleanup  # Must match registry key
  schedule_expression: "0 5 * * *"  # Daily at 5 AM
  is_active: true
  is_enabled_by_default_for_new_orgs: true
  parameters: {}  # Or specific params if needed
```

## Cron Expression Format

Standard 5-field: `minute hour day-of-month month day-of-week`

| Expression | Meaning |
|------------|---------|
| `*/30 * * * *` | Every 30 minutes |
| `0 * * * *` | Every hour |
| `0 2 * * *` | Daily 2 AM |
| `0 0 * * 0` | Sunday midnight |

## Platform vs Org-Scoped Jobs

- `organization_id=None` -> Platform-wide (runs once globally)
- `organization_id=UUID` -> Org-scoped (per organization)

All default jobs are platform-wide.

## Key Files

| File | Purpose |
|------|---------|
| `src/services/cron_scheduler.py` | CronSchedulerService, `get_all_cron_handlers()` registry |
| `src/services/cron/` | Handler modules by category |
| `src/services/cron/__init__.py` | Exports all handlers for registry |
| `src/services/cron/_common.py` | Shared utilities (e.g., `soft_delete_expired`) |
| `src/crud/cron_job.py` | CRUD operations |
| `src/models/cron_job.py` | CronJobDefinition, CronJobExecution models |
| `src/workers/tasks.py` | `system_cron_scheduler_task` ARQ trigger |
| `scripts/seed_data/cron_jobs.yaml` | Default job definitions |
| `src/constants/cron_job_config.py` | SystemConfig key mappings for UI |

## Handler Module Categories

| Module | Handlers |
|--------|----------|
| `files.py` | File cleanup, storage quota checks |
| `health.py` | System health, self-recovery |
| `maintenance.py` | Expired soft delete cleanup |
| `notifications.py` | Email digest, stale notification cleanup |
| `otp.py` | OTP expiration cleanup |
| `reports.py` | Report generation |
| `sessions.py` | Session expiration, device cleanup |
| `storage.py` | Storage usage recalculation |
| `tokens.py` | Expired token cleanup |

## Execution Flow

1. ARQ runs `system_cron_scheduler_task` every minute
2. Queries `CronJobDefinition` where `next_run_time <= now` and `is_active=True`
3. Looks up handler by `code` in `get_all_cron_handlers()` registry
4. Creates `CronJobExecution` with status=RUNNING
5. Calls handler; on success records result, on error records error_message
6. Recalculates `next_run_time` using croniter

## Gotchas

- **Handler registration**: Handlers are auto-registered at startup via `cron_scheduler_service.register_all_handlers()` in `main.py` lifespan
- **Session rollback**: Scheduler auto-rolls back on exception, so handlers can throw safely
- **MissingGreenlet prevention**: Job attributes are eagerly captured before handler execution
- **Return `{"status": "error", "reason": "..."}` from handler to mark execution as ERROR without throwing

## When NOT to Use CronSchedulerService

Keep as hardcoded ARQ cron if:
- Job requires sub-minute frequency (e.g., `collect_metrics_task` every 15 seconds)
- Job is the scheduler itself (`system_cron_scheduler_task`)

## Admin UI

Super admins manage jobs at `/admin/cron-jobs`:
- Toggle `is_active`, modify `schedule_expression`
- View execution history and errors
- Job-specific config via SystemConfig (mapped in `cron_job_config.py`)
