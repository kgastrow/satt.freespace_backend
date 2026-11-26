# User Data Export and Account Deletion

**ADW ID:** 20260115222958-1f49b656 | **Date:** 2026-01-15

GDPR-compliant user data export and account deletion with 30-day grace period. Users can export personal data as ZIP or request account deletion with recovery window.

## Implementation

### Backend
- **Models:** `app/backend/src/models/data_export_request.py` (status: pending|processing|completed|failed|expired), `app/backend/src/models/data_deletion_request.py` (unique per user)
- **CRUD:** `app/backend/src/crud/data_export_request.py`, `app/backend/src/crud/data_deletion_request.py` (multi-tenant filtered by organization_id)
- **API:** `app/backend/src/api/user_data.py` (endpoints for export/deletion with authentication), registered in `app/backend/src/api/__init__.py`
- **Services:**
  - `app/backend/src/services/user_data_export.py` (async ZIP packaging: profile.json, organizations.json, activity.json, files/)
  - `app/backend/src/services/user_data_deletion.py` (soft delete cascade → hard delete after 30 days)
  - `app/backend/src/services/cron_handlers.py` (cleanup_expired_exports at 02:00, process_hard_deletions at 03:00)
- **Jobs:** `app/backend/src/workers/tasks.py` (ARQ async export generation)
- **Serializers:** `app/backend/src/serialisers/data_export.py` (Pydantic v2 validation)
- **Database:** `app/backend/alembic/versions/80f480ef5859_add_data_export_deletion_requests.py`

### Frontend
- **Pages:** `app/frontend/src/pages/settings/DataExportPage.tsx`, `app/frontend/src/pages/settings/DeleteAccountPage.tsx`
- **API:** `app/frontend/src/features/user/userApi.ts` (RTK Query endpoints)
- **i18n:** Translations in all locales (en, de, xh, zu, nso) - mandatory for all user-facing text

### Testing
`app/backend/tests/unit_tests/test_user_data_export_delete.py`: 2000+ lines covering models, CRUD, API, export generation, soft/hard delete, cron jobs, multi-tenancy isolation

## Key Design Decisions

- **Multi-tenancy:** All queries filtered by organization_id
- **Soft delete pattern:** Immediate soft delete with hard delete after 30-day window
- **S3 integration:** Exports stored with 30-day expiration, signed URLs (1-hour validity) for downloads
- **Async processing:** ARQ background tasks prevent request blocking
- **Status enums:** Track lifecycle (export and deletion)
- **Cron scheduling:** Daily low-traffic hour jobs (02:00, 03:00)

## User Workflows

**Export:**
1. Settings → Data Export → "Request Export"
2. Background job generates ZIP (pending → processing → completed)
3. "Download" button with signed URL
4. Expires after 30 days

**Deletion:**
1. Settings → Delete Account → "Delete My Account"
2. Confirmation dialog with text entry
3. Immediate soft delete + logout
4. 30-day recovery window (login to restore)
5. Optional "Cancel Deletion" during window
6. Hard delete after 30 days

**Export Contents:** profile.json, organizations.json, activity.json, files/, README.txt

## Configuration
- S3 bucket: Store export ZIPs (existing config)
- ARQ worker: Background job processing (existing config)
- Cron jobs: Pre-seeded cleanup_expired_exports (02:00) and process_hard_deletions (03:00)

## Testing
```bash
cd app/backend && make test
```

## Security & Compliance
- Authentication required on all endpoints
- Signed URLs with 1-hour validity
- Soft delete cascades to roles, tokens, notifications, files
- Hard delete removes all traces including S3 files
- GDPR: Right to data portability (export) + Right to be forgotten (deletion)
- 30-day grace period balances protection against accidental deletion with GDPR requirements
