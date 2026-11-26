# Super Admin User Impersonation

**ADW ID:** 20260110234549-ccfd0008
**Date:** 2026-01-11
**Specification:** specs/multi-phase/issue-108-adw-20260110234549-ccfd0008-multi-phase.md

## Overview

Enables super admins to securely impersonate organization users for support. Special tokens preserve admin identity while presenting target user context. All impersonation actions are audited and traceable to the original admin.

## Implementation

### Backend Changes

**Database & Models:**
- `app/backend/alembic/versions/0001_add_impersonation_session_table.py` - ImpersonationSession table migration
- `app/backend/src/models/impersonation_session.py` - Tracks impersonator, target user, timestamps, IP, user agent
- `app/backend/src/models/audit_log.py` - Added IMPERSONATE_START and IMPERSONATE_END actions

**Core Logic:**
- `app/backend/src/crud/impersonation_session.py` - Session CRUD operations
- `app/backend/src/services/impersonation.py` - Validation and business logic
- `app/backend/src/serialisers/impersonation_session.py` - Pydantic models
- `app/backend/src/api/impersonation.py` - REST endpoints (/admin/impersonate/*)
- `app/backend/src/api/auth.py` - JWT token extension with impersonator_id and impersonation_session_id
- `app/backend/src/api/deps.py` - Impersonation mode detection

**Tests (1,319 lines total):**
- `app/backend/tests/api_tests/test_impersonation.py` - 662 lines
- `app/backend/tests/crud_tests/test_impersonation_session.py` - 311 lines
- `app/backend/tests/service_tests/test_impersonation_service.py` - 346 lines

### Frontend Changes

**State & API:**
- `app/frontend/src/features/impersonation/impersonationApi.ts` - RTK Query endpoints
- `app/frontend/src/features/impersonation/impersonationSlice.ts` - Redux state
- `app/frontend/src/hooks/useImpersonation.ts` - Custom hook
- `app/frontend/src/types/impersonation.ts` - TypeScript types

**UI & Localization:**
- `app/frontend/src/components/ImpersonationBanner.tsx` - Fixed banner with end button
- `app/frontend/src/components/ImpersonationButton.tsx` - Action button
- `app/frontend/src/layouts/RootLayout.tsx` - Banner integration
- `app/frontend/src/pages/admin/UsersPage.tsx` - Impersonate action in user list
- `app/frontend/src/locales/{en,de}/admin.json` - English and German translations

**Tests (699 lines total):**
- `app/frontend/src/tests/ImpersonationBanner.test.tsx` - 329 lines
- `app/frontend/src/tests/impersonationSlice.test.tsx` - 370 lines

### Key Architecture Decisions

1. **Token Design**: JWT tokens include optional `impersonator_id` and `impersonation_session_id` claims preserving admin identity
2. **Security**: Super admins cannot impersonate other super admins, themselves, or users in inactive/soft-deleted organizations
3. **Audit Trail**: IMPERSONATE_START and IMPERSONATE_END actions record admin ID as actor for full traceability
4. **Session Tracking**: Database tracks active sessions with IP, user agent for security auditing
5. **Visual Indicator**: Fixed banner clearly indicates impersonation mode with target user email

## Usage

**Start:** Users page → Click impersonate button → View as target user with banner
**During:** All actions execute as target user, audited with admin's ID
**End:** Click "End Impersonation" button in banner → Return to admin dashboard
**History:** GET /admin/impersonate/history endpoint with filters

## Security Restrictions

- Only super admins (is_admin=True) can impersonate
- Cannot impersonate: self, other super admins, inactive organization users, soft-deleted users

## Testing

```bash
# Backend tests (1,319 lines covering CRUD, services, API, auth, audit logging)
cd app/backend && make test

# Frontend tests (699 lines covering banner, Redux, RTK Query, hooks)
cd app/frontend && npm run test

# Manual E2E: Login as super admin → Users page → Impersonate user → Verify banner and actions → End impersonation → Check audit logs
```

## Future Enhancements

- Time-limited impersonation sessions with auto-expiry
- Impersonation reason/ticket field for compliance tracking
