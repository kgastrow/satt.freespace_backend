# Impersonation Transparency & Audit Trail

**ADW ID:** 20260113095641-2f9ce557
**Date:** 2026-01-13

## Overview

Adds transparency and accountability to impersonation. When a super admin impersonates a user:
- Target user receives email and in-app notifications at start and end of session
- All actions during impersonation are marked in the audit log with the impersonator's identity
- Users can view their impersonation history in their profile page

## Implementation

### Backend Changes

**Database**: Added `impersonated_by` (UUID, nullable, indexed FK) column to `audit_log` table via migration `app/backend/alembic/versions/946e8fa1b69d_add_impersonated_by_to_audit_log.py`

**Models & Services**:
- `app/backend/src/models/audit_log.py`: Added `impersonated_by` field with FK relationship
- `app/backend/src/services/audit.py`: Records impersonation context from `CurrentUser.impersonator_id`
- `app/backend/src/serialisers/audit_log.py`: Serializes `impersonated_by` in responses
- `app/backend/src/services/notifications/impersonation_notifier.py`: Singleton service with `notify_start()` and `notify_end()` methods; sends email and in-app notifications via existing notification dispatcher (category: "account", urgent priority)
- `app/backend/src/crud/impersonation_session.py`: Added `get_my_impersonation_history()` CRUD function with `organization_id` filtering

**API**:
- `app/backend/src/api/impersonation.py`: Triggers notifications in `ImpersonationService.start()` and `end()` methods
- `GET /api/v1/impersonate/my-history`: Returns paginated impersonation sessions targeting current user with impersonator details

### Frontend Changes

- `app/frontend/src/features/impersonation/impersonationApi.ts`: RTK Query endpoint for history
- `app/frontend/src/types/impersonation.ts`: TypeScript types
- `app/frontend/src/components/profile/ImpersonationHistorySection.tsx`: Conditionally rendered component (only if history exists)
- `app/frontend/src/pages/ProfilePage.tsx`: Integrated history section
- `app/frontend/src/locales/en/settings.json`: i18n strings

## Usage

**End Users**: Profile page → "Account Access History" section shows who accessed account, when, and duration (human-readable format).

**Audit**: Query `audit_log` with `impersonated_by IS NOT NULL`, join with `user` table on `impersonated_by` column for impersonator details.

**Developers**: Audit service automatically captures impersonation context. Notifications sent automatically via `ImpersonationService.start()` and `end()`.

## Key Design Decisions

- `impersonated_by` field is nullable—NULL indicates actions not during impersonation
- Notifications respect existing user preferences (account category)
- History endpoint respects multi-tenancy filtering by `organization_id`
- UI conditionally renders to avoid showing empty history
- Notification content: start includes impersonator name and timestamp; end includes duration

## Testing

```bash
cd app/backend && make test  # Key test: test_impersonation_transparency.py
cd app/frontend && npm run test
```
