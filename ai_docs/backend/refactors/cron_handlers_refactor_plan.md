# Cron Handlers Refactor Plan

**Status:** ✅ COMPLETED (2026-02-04)

**Issue:** MEDIUM-001 - `cron_handlers.py` was 750+ lines with 20+ handlers.

**Result:** Handlers split into `src/services/cron/` with 10 modules by category. See `ai_docs/backend/context/cron_scheduler.md` for current structure.

## Proposed Module Structure

```
src/services/cron/
    __init__.py          # Re-exports all handlers for backward compatibility
    _common.py           # Shared utilities, imports, helper functions
    otp.py               # OTP-related cleanup
    tokens.py            # Token cleanup (refresh tokens, API keys)
    notifications.py     # Notification handlers
    storage.py           # S3 and local storage monitoring
    files.py             # File cleanup handlers
    sessions.py          # Session and auth-related handlers
    health.py            # Health monitoring handlers
    maintenance.py       # Maintenance and data lifecycle handlers
    reports.py           # Scheduled reports handler
```

## Handler to Module Mapping

### 1. `cron/otp.py` - OTP Cleanup
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `cleanup_expired_otps_handler` | `cleanup_expired_otps` | `*/30 * * * *` | Remove expired one-time passwords |

**Dependencies:**
- Models: `OTP` (or equivalent)
- CRUD: OTP deletion operations

### 2. `cron/tokens.py` - Token Management
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `cleanup_expired_refresh_tokens_handler` | `cleanup_expired_refresh_tokens` | `0 * * * *` | Remove expired refresh tokens |
| `check_api_key_expiry_handler` | `check_api_key_expiry` | `0 9 * * *` | Notify users of expiring/expired API keys |

**Dependencies:**
- Models: `RefreshToken`, `APIKey`
- Services: `notification_dispatcher`

### 3. `cron/notifications.py` - Notification Handlers
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `cleanup_old_notifications_handler` | `cleanup_old_notifications` | `0 2 * * *` | Remove notifications older than retention period |
| `check_notification_health_handler` | `check_notification_health` | `0 * * * *` | Monitor notification delivery rates |

**Dependencies:**
- Models: `Notification`
- Services: `notification_dispatcher`
- Config: `cleanup.notifications.retention_days`

### 4. `cron/storage.py` - Storage Monitoring
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `check_s3_storage_handler` | `s3_storage_monitor` | `0 2 * * *` | Monitor S3 bucket usage and alert |
| `check_local_storage_handler` | `local_storage_monitor` | `0 2 * * *` | Monitor local storage usage and alert |
| `check_disk_usage_handler` | `disk_usage_monitor` | `30 2 * * *` | Monitor filesystem disk usage |
| `s3_migration_handler` | `s3_migration` | `*/10 * * * *` | Migrate files from local to S3 |

**Dependencies:**
- Services: `s3_storage`, `local_storage`, `notification_dispatcher`
- External: `aioboto3` (optional)
- Config: `s3_storage.total_allocated_bytes`, `s3_storage.warning_threshold_percent`, etc.
- Constants: `MIN_THRESHOLD_PERCENT`, `MAX_THRESHOLD_PERCENT`

### 5. `cron/files.py` - File Cleanup
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `cleanup_deleted_files_handler` | `cleanup_deleted_files` | `0 3 * * *` | Permanently remove soft-deleted files |
| `cleanup_expired_exports_handler` | `cleanup_expired_exports` | `0 2 * * *` | Delete expired data export files |

**Dependencies:**
- Models: `File`, `DataExportRequest`
- Services: `s3_storage`, `file_manager`
- Config: `cleanup.deleted_files.retention_days`

### 6. `cron/sessions.py` - Session and Auth Handlers
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `check_2fa_grace_period_handler` | `check_2fa_grace_period` | `0 1 * * *` | Check for expired 2FA grace periods |
| `check_user_type_expiry_handler` | `check_user_type_expiry` | `0 1 * * *` | Check for expired user type assignments |
| `cleanup_old_request_logs_handler` | `cleanup_old_request_logs` | `0 4 * * *` | Remove old request logs |

**Dependencies:**
- Models: `User`, `UserTypeAssignment`, `RequestLog`
- Services: `notification_dispatcher`
- Config: `request_logs.retention_days`

### 7. `cron/health.py` - Health Monitoring
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `check_brute_force_alerts_handler` | `check_brute_force_alerts` | `*/15 * * * *` | Monitor and alert on brute force attacks |
| `check_queue_health_handler` | `check_queue_health` | `*/10 * * * *` | Monitor job queue depth and workers |
| `check_db_pool_health_handler` | `check_db_pool_health` | `*/5 * * * *` | Monitor database connection pool |

**Dependencies:**
- Services: `brute_force_detector`, `queue_health_service`, `notification_dispatcher`
- External: Redis connections

### 8. `cron/maintenance.py` - Maintenance and Lifecycle
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `process_hard_deletions_handler` | `process_hard_deletions` | `0 3 * * *` | Permanently delete users past grace period |
| `update_geoip_database_handler` | `update_geoip_database` | `0 2 * * 0` | Download/update MaxMind GeoIP database |

**Dependencies:**
- Services: `user_data_deletion`
- Config: `geoip.maxmind.*`
- External: MaxMind API

### 9. `cron/reports.py` - Scheduled Reports
| Handler | Job Code | Schedule | Description |
|---------|----------|----------|-------------|
| `process_scheduled_reports_handler` | `process_scheduled_reports` | `*/5 * * * *` | Generate and send scheduled reports |

**Dependencies:**
- Models: `ReportSchedule`
- Services: `notification_dispatcher`, `email`

## Shared Module: `cron/_common.py`

Contains common imports, utilities, and helper functions used across multiple handler modules.

```python
"""Common utilities for cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger
from src.services.notifications import notification_dispatcher

# Threshold constants
MIN_THRESHOLD_PERCENT = 1
MAX_THRESHOLD_PERCENT = 99


def get_cutoff_date(days: int) -> datetime:
    """Calculate cutoff date for cleanup operations."""
    return datetime.now(timezone.utc) - timedelta(days=days)


async def soft_delete_records(
    session: AsyncSession,
    model: Any,
    records: list[Any],
) -> int:
    """Soft delete a list of records by setting deleted_time."""
    now = datetime.now(timezone.utc)
    count = 0
    for record in records:
        if hasattr(record, 'deleted_time') and record.deleted_time is None:
            record.deleted_time = now
            count += 1
    return count
```

## Re-export Module: `cron/__init__.py`

```python
"""
Cron job handlers.

Re-exports all handlers for backward compatibility with existing imports:
    from src.services.cron_handlers import cleanup_expired_otps_handler
"""

from src.services.cron.otp import cleanup_expired_otps_handler
from src.services.cron.tokens import (
    cleanup_expired_refresh_tokens_handler,
    check_api_key_expiry_handler,
)
from src.services.cron.notifications import (
    cleanup_old_notifications_handler,
    check_notification_health_handler,
)
from src.services.cron.storage import (
    check_s3_storage_handler,
    check_local_storage_handler,
    check_disk_usage_handler,
    s3_migration_handler,
)
from src.services.cron.files import (
    cleanup_deleted_files_handler,
    cleanup_expired_exports_handler,
)
from src.services.cron.sessions import (
    check_2fa_grace_period_handler,
    check_user_type_expiry_handler,
    cleanup_old_request_logs_handler,
)
from src.services.cron.health import (
    check_brute_force_alerts_handler,
    check_queue_health_handler,
    check_db_pool_health_handler,
)
from src.services.cron.maintenance import (
    process_hard_deletions_handler,
    update_geoip_database_handler,
)
from src.services.cron.reports import process_scheduled_reports_handler

__all__ = [
    # OTP
    "cleanup_expired_otps_handler",
    # Tokens
    "cleanup_expired_refresh_tokens_handler",
    "check_api_key_expiry_handler",
    # Notifications
    "cleanup_old_notifications_handler",
    "check_notification_health_handler",
    # Storage
    "check_s3_storage_handler",
    "check_local_storage_handler",
    "check_disk_usage_handler",
    "s3_migration_handler",
    # Files
    "cleanup_deleted_files_handler",
    "cleanup_expired_exports_handler",
    # Sessions
    "check_2fa_grace_period_handler",
    "check_user_type_expiry_handler",
    "cleanup_old_request_logs_handler",
    # Health
    "check_brute_force_alerts_handler",
    "check_queue_health_handler",
    "check_db_pool_health_handler",
    # Maintenance
    "process_hard_deletions_handler",
    "update_geoip_database_handler",
    # Reports
    "process_scheduled_reports_handler",
]
```

## Backward Compatibility

To maintain backward compatibility during the transition:

1. **Keep `cron_handlers.py` as a re-export module** temporarily:
   ```python
   """Legacy module - imports from new location for backward compatibility."""
   from src.services.cron import *  # noqa: F401, F403
   ```

2. **Update `cron_scheduler.py`** to import from new location:
   ```python
   def get_all_cron_handlers() -> dict[str, JobHandler]:
       from src.services.cron import (
           cleanup_expired_otps_handler,
           # ... all other handlers
       )
   ```

3. **Deprecation path:**
   - Phase 1: Create new module structure, keep old imports working
   - Phase 2: Update all internal imports to use new paths
   - Phase 3: Remove `cron_handlers.py` after confirming no external dependencies

## Suggested Extraction Order

Extract handlers in this order to minimize risk and validate the pattern:

1. **`cron/_common.py`** - Create shared utilities first
2. **`cron/__init__.py`** - Set up re-export structure
3. **`cron/otp.py`** - Single simple handler, validates pattern
4. **`cron/tokens.py`** - Two related handlers, tests grouping
5. **`cron/health.py`** - Complex handlers with external dependencies
6. **`cron/storage.py`** - Multiple handlers with shared constants
7. **`cron/notifications.py`** - Two handlers with notification service
8. **`cron/files.py`** - File-related cleanup
9. **`cron/sessions.py`** - Auth-related handlers
10. **`cron/maintenance.py`** - Lifecycle management
11. **`cron/reports.py`** - Scheduled reports

## Testing Strategy

For each extracted module:

1. **Unit tests** should remain in `tests/services/test_cron_handlers.py` initially
2. After extraction, split tests to match module structure:
   ```
   tests/services/cron/
       test_otp.py
       test_tokens.py
       test_notifications.py
       test_storage.py
       test_files.py
       test_sessions.py
       test_health.py
       test_maintenance.py
       test_reports.py
   ```
3. Each test file should verify:
   - Handler returns correct result structure
   - Correct records are affected (tenant isolation if applicable)
   - Error handling returns `{"status": "error", "reason": "..."}`

## Files to Modify

| File | Change |
|------|--------|
| `src/services/cron_handlers.py` | Replace with re-export module |
| `src/services/cron/__init__.py` | Create with all handler exports |
| `src/services/cron/_common.py` | Create with shared utilities |
| `src/services/cron/*.py` | Create handler modules |
| `src/services/cron_scheduler.py` | Update imports (optional, re-exports maintain compatibility) |

## Notes

- **Handler signature must be preserved:** `async def handler(session: AsyncSession, parameters: dict) -> dict`
- **All handlers are stateless** - they receive session and parameters, return results
- **Notification dispatcher** is the most common shared dependency
- **Constants** like threshold percentages should move to `_common.py`
- **Optional imports** (like `aioboto3`) should remain in the storage module with try/except

## Summary by Module

| Module | Handlers | Primary Concern |
|--------|----------|-----------------|
| `otp.py` | 1 | OTP cleanup |
| `tokens.py` | 2 | Token lifecycle |
| `notifications.py` | 2 | Notification cleanup & health |
| `storage.py` | 4 | Storage monitoring & migration |
| `files.py` | 2 | File cleanup |
| `sessions.py` | 3 | Auth & session cleanup |
| `health.py` | 3 | System health monitoring |
| `maintenance.py` | 2 | Data lifecycle & external updates |
| `reports.py` | 1 | Report generation |
| **Total** | **20** | |
