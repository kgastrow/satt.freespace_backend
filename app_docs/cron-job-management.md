# Cron Job Management System

**ADW ID:** 20260114230159-b3052827
**Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-135-adw-20260114230159-b3052827-multi-phase.md

Super admin web UI for configuring, scheduling, and monitoring recurring tasks. Supports platform-wide and organization-scoped jobs with JSON parameters, execution history, and cron expression scheduling via croniter + ARQ.

## Technical Implementation

### Backend Files

- `app/backend/src/models/cron_job.py` (new): CronJobDefinition and CronJobExecution models with multi-tenancy
- `app/backend/src/crud/cron_job.py` (new): 592 lines of async CRUD operations
- `app/backend/src/api/cron_jobs.py` (new): 470 lines with 8 REST endpoints (super admin only)
- `app/backend/src/services/cron_scheduler.py` (new): 250 lines scheduler logic with job registry pattern
- `app/backend/src/serialisers/cron_job.py` (new): Pydantic models for validation
- `app/backend/src/workers/tasks.py` (modify): system_cron_scheduler_task runs every minute
- `app/backend/alembic/versions/65f6ac07da38_add_cron_job_tables.py` (new): Database migration
- `app/backend/tests/unit_tests/test_cron_jobs.py` (new): 1,644 lines of tests
- `app/backend/requirements.txt` (modify): Added croniter

### Frontend Files

- `app/frontend/src/pages/admin/CronJobsPage.tsx` (new): 729 lines admin interface
- `app/frontend/src/features/cronJobs/cronJobsApi.ts` (new): RTK Query API slice with 8 hooks
- `app/frontend/src/types/cron-job.ts` (new): TypeScript type definitions
- `app/frontend/src/components/AppSidebar.tsx` (modify): Added "Crons" in Super Admin section
- `app/frontend/src/router.tsx` (modify): Added /admin/cron-jobs with SuperAdminGuard
- `app/frontend/src/locales/*/*.json` (modify): Translations for en, de, xh, zu, nso

### Architecture

**Multi-tenancy**: Jobs are either platform-wide (organization_id = null) or organization-scoped. Unique constraint on (code, organization_id, deleted_time).

**Database schema**:
- `cron_job_definition`: Job configuration, scheduling, execution tracking. Indexes: (is_active, next_run_time), (organization_id, is_active)
- `cron_job_execution`: Execution audit trail. Indexes: (cron_job_id, created_time), (organization_id, created_time), (status)

**Scheduler**: ARQ-based task runs every minute. Queries due jobs (next_run_time <= now), executes registered handlers, records results, calculates next run via croniter.

**Job registry pattern**: Jobs registered by code with handler functions enable extensible execution while maintaining database config.

**Execution tracking**: Each run creates execution record with timestamps, status (pending/running/success/error), result JSON, and error messages.

## Usage

### Creating Jobs

Admin → Crons → "Create Cron Job":
- **Name**: Display name
- **Code**: Unique identifier (lowercase, numbers, underscores)
- **Schedule Expression**: Standard cron syntax (e.g., `0 0 * * *` = daily at midnight)
- **Is Active**: Enable/disable execution
- **Platform Wide**: Toggle platform-wide vs org-scoped
- **Enabled by Default for New Orgs**: Auto-enable for new organizations
- **Parameters**: Optional JSON configuration

### Managing Jobs

- **Edit**: Modify job settings
- **Delete**: Soft-delete (stops execution, preserves history)
- **Toggle**: Quick enable/disable
- **Manual Trigger**: Execute immediately, bypassing schedule
- **View History**: See execution records with timestamps and status

### Monitoring

Data table columns:
- Name & Code
- Schedule (cron expression)
- Status (Active/Inactive badge)
- Last Run timestamp
- Next Run calculated time
- Last Status (Success/Error/Running/Pending)

Execution history shows: start/completion timestamps, duration, status badge, error messages, result data.

## Cron Expression Format

Standard 5-field cron syntax:
```
* * * * *
│ │ │ │ └─ Day of week (0-6)
│ │ │ └─── Month (1-12)
│ │ └───── Day of month (1-31)
│ └─────── Hour (0-23)
└───────── Minute (0-59)
```

Examples:
- `0 0 * * *` - Daily at midnight
- `0 */6 * * *` - Every 6 hours
- `30 2 * * 1` - Every Monday at 2:30 AM
- `0 0 1 * *` - First of month at midnight

## Testing

### Backend

```bash
cd app/backend
make test
```

Test coverage: Model validation, CRUD with multi-tenancy isolation, API endpoints, scheduler service (due job detection, execution, error handling), cron parsing and next run calculation.

### Manual

1. `cd app/backend && make dev`
2. `cd app/frontend && npm run dev`
3. Log in as super admin
4. Navigate to /admin/cron-jobs
5. Create test job with `* * * * *` (every minute) and activate
6. Wait 1 minute and verify execution history

## Key Implementation Details

- **Job registry**: Codes must be registered with handler functions in scheduler service. Currently supports cleanup tasks (expired OTPs, refresh tokens).
- **Platform-wide vs org-scoped**: Platform-wide (organization_id = null) executes once globally; org-scoped can run per-organization or default for new orgs.
- **Scheduler timing**: system_cron_scheduler_task runs every minute via ARQ. Jobs with next_run_time <= now are due.
- **Dynamic recalculation**: Updating schedule_expression immediately recalculates next_run_time via croniter.
- **Soft deletes**: deleted_time set instead of hard delete, preserving execution history.
- **Error tracking**: Failed executions capture error_message in both CronJobExecution and CronJobDefinition.last_run_error_message.
- **Timezone support**: croniter library provides timezone-aware cron parsing.
- **Execution retention**: Records retained indefinitely; consider implementing cleanup task in production.
