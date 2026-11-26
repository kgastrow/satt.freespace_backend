# User Suspension Management

**ADW ID:** 20260114230343-a6dfb30c
**Date:** 2026-01-14
**Specification:** specs/multi-phase/issue-136-adw-20260114230343-a6dfb30c-multi-phase.md

## Overview

Temporarily disable user accounts via org owner/admin/super admin roles. Suspended users cannot authenticate. Includes optional reason tracking, email notifications, and audit logging.

## Implementation

**Backend - Model & Migration:**
- `app/backend/src/models/user.py`: `SuspensionStatus` enum ('active', 'suspended'), fields: `suspension_status`, `suspended_time`, `suspended_by`, `suspension_reason`
- `app/backend/alembic/versions/0d009d25be94_add_user_suspension_fields.py`: Migration

**Backend - CRUD & API:**
- `app/backend/src/crud/user.py`: `suspend_user()`, `unsuspend_user()` with tenant isolation
- `app/backend/src/api/users.py`: POST `/users/{user_id}/suspend`, `/users/{user_id}/unsuspend` with optional email via `notification_dispatcher`
- `app/backend/src/serialisers/user.py`: `SuspendUserRequest`, `SuspendUserResponse`, `UnsuspendUserResponse`
- `app/backend/src/core/response_codes.py`: Suspension response codes

**Backend - Authentication:**
- `app/backend/src/api/auth.py`: Login/token refresh blocked for suspended users (403 `user.suspended`)

**Backend - Testing:**
- `app/backend/tests/unit_tests/test_user_suspension.py`: Suspend/unsuspend, permissions, tenant isolation, auth blocking, audit logging

**Frontend:**
- `app/frontend/src/features/users/usersApi.ts`: `suspendUser`, `unsuspendUser` RTK Query mutations
- `app/frontend/src/pages/admin/UsersPage.tsx`: Suspension badge, suspend/unsuspend actions with dialogs
- `app/frontend/src/locales/*/admin.json`: i18n for all 5 locales (en, de, xh, zu, nso)
- `app/frontend/src/types/generated.ts`: Regenerated types

## Key Technical Details

- **Enum-based status** for type safety
- **Tenant isolation** via `organization_id` filtering
- **Permission-gated** (`users:suspend`, `users:unsuspend`)
- **Protection rules**: Cannot suspend owners or yourself
- **Audit trail** with before/after values, actor, timestamp, IP
- **Soft block**: User record remains, only auth blocked
- **Optional notifications** with reason

## Usage

**Suspend:** `/admin/users` → action menu → "Suspend" → optional reason/notification → confirm

**Unsuspend:** `/admin/users` → action menu on suspended user → "Unsuspend" → confirm

**Effect:** User cannot log in or refresh tokens; receives email if notification checked

## Permissions

Required roles: `users:suspend`, `users:unsuspend` (Owner, Admin, Super Admin)

## Testing

```bash
cd app/backend && make test  # Covers suspend/unsuspend, permissions, tenant isolation, auth blocking
cd app/frontend && npm run test && npm run lint && npm run build
```

Manual: Create user → suspend with reason/notification → verify 403 on login → check audit logs → unsuspend → verify login works
