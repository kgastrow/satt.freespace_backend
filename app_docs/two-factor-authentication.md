# Two-Factor Authentication (2FA) System

**ADW ID:** 20260114231509-2377a832
**Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-138-adw-20260114231509-2377a832-multi-phase.md

## Overview

TOTP-based 2FA system with multi-tenant support. Super admins control per-organization 2FA availability, org admins set policy (disabled/optional/mandatory), and users configure 2FA with backup codes. When policy changes to mandatory, users get 7-day grace period with notifications before enforcement.

## Architecture

### Database Models
- `app/backend/src/models/organization_two_factor_settings.py`: Policy (disabled/optional/mandatory), grace period, enforcement tracking
- `app/backend/src/models/user_two_factor.py`: User TOTP secrets with verification status
- `app/backend/src/models/user_two_factor_backup_code.py`: Single-use backup codes
- `app/backend/alembic/versions/5c95852e6155_.py`: Migration with partial unique indexes for soft deletes, scoped by `organization_id`

### Backend APIs & Services
- `app/backend/src/crud/organization_two_factor_settings.py`: Org-level CRUD with tenant filtering
- `app/backend/src/crud/user_two_factor.py`: User 2FA CRUD with backup code management
- `app/backend/src/api/organization_two_factor_settings.py`: Admin endpoints (super admin, org admin)
- `app/backend/src/api/two_factor.py`: User-facing setup/management endpoints
- `app/backend/src/serialisers/two_factor.py`: Pydantic schemas
- `app/backend/src/services/two_factor.py`: TOTP generation/verification, QR provisioning, backup codes (using pyotp)
- `app/backend/src/api/auth.py`: Modified login flow returning `requires_2fa` flag with `two_factor_token`; added `POST /auth/verify-2fa` endpoint
- `app/backend/src/serialisers/auth.py`: Extended login response schema
- `app/backend/src/core/response_codes.py`: 2FA-specific response codes
- `app/backend/src/workers/two_factor_tasks.py`: Background job for policy change notifications with grace period enforcement
- `app/backend/src/services/organization_seeding.py`: Auto-creates default 2FA settings for new organizations

### Frontend
- **Admin:** `app/frontend/src/pages/admin/TwoFactorSettingsPage.tsx` - policy management with compliance tracking
- **User Settings:** `app/frontend/src/pages/settings/TwoFactorPage.tsx` - full 2FA management
- **Setup Flow:** `app/frontend/src/components/two-factor/TwoFactorSetup.tsx`, `BackupCodesDisplay.tsx`, `TwoFactorStatus.tsx`
- **Login:** `app/frontend/src/pages/LoginPage.tsx`, `app/frontend/src/components/auth/TwoFactorVerification.tsx` - two-step login with 6-digit code/backup code toggle
- **API:** `app/frontend/src/store/api/twoFactorApi.ts` (RTK Query)
- **State:** `app/frontend/src/features/auth/authSlice.ts`, `app/frontend/src/features/auth/authApi.ts`, `app/frontend/src/types/auth.ts`
- **Navigation:** Added `/admin/two-factor` route with permission gating in `app/frontend/src/router.tsx` and sidebar in `app/frontend/src/components/AppSidebar.tsx`

### Testing
- `app/backend/tests/unit_tests/test_two_factor_auth.py`: 1314 lines covering models, CRUD, API, auth flow, tenant isolation
- `app/backend/tests/api_tests/test_two_factor_api.py`: 758 lines of API integration tests
- Frontend integration tests updated for 2FA flow

### i18n
Translations (en, de, xh, zu, nso) in: `app/frontend/src/locales/*/admin.json`, `*/settings.json`, `*/auth.json`, `*/common.json`

## Key Technical Decisions

- **Multi-tenancy:** All 2FA data scoped by `organization_id` with partial unique indexes for soft deletes
- **TOTP:** RFC 6238 compliant via pyotp, base32 secrets, provisioning URIs for QR code generation
- **Grace Period:** When policy becomes mandatory, `enforcement_start_time = now() + grace_period_days`, users notified
- **Backup Codes:** Cryptographically secure 8-character alphanumeric, bcrypt-hashed at rest, single-use tracked
- **Permissions:** `two_factor:read`, `two_factor:write`, `two_factor:delete` auto-seeded
- **Login Flow:** POST `/auth/login` returns `requires_2fa: true` + `two_factor_token` (JWT); POST `/auth/verify-2fa` verifies TOTP/backup code
- **QR Codes:** Generated frontend from provisioning URI using qrcode.react

## Dependencies

Backend: `pyotp` (RFC 6238 TOTP)
Frontend: `qrcode.react` (QR code generation)

## How to Use

### Super Admin
1. Admin > Organizations
2. Enable 2FA per organization with toggle
3. Org admin can then configure policy

### Organization Admin
1. Admin > Two-Factor Auth (requires `two_factor:read` permission)
2. Select policy: Disabled | Optional | Mandatory
3. Set grace period (default: 7 days)
4. View users without 2FA when mandatory

### User - Setup
1. Settings > Security > Two-Factor Authentication
2. Click "Start Setup"
3. Scan QR code with authenticator (Google Authenticator, Authy, etc.) or manually enter secret
4. Enter 6-digit code from app to verify
5. Save backup codes (download or copy)

### User - Login
1. Enter email and password
2. If 2FA enabled, enter 6-digit code or backup code
3. Complete login

### Backup Codes
1. Settings > Security > Two-Factor Authentication
2. "View" or "Regenerate" backup codes
3. Each code single-use

## Configuration

No additional environment variables. Uses existing:
- Database connection for 2FA data
- Redis/ARQ for background notification jobs
- Existing notification system

## Testing

```bash
# Backend
cd app/backend
make test

# Frontend
cd app/frontend
npm run test
```

Manual checklist:
1. Super admin enables 2FA for organization
2. Org admin sets policy to "optional"
3. User sets up 2FA via Settings
4. User logs out, logs in with 2FA code
5. Org admin changes policy to "mandatory"
6. Users without 2FA receive notification
7. After grace period, users redirected to setup on login
8. Test backup code login flow
9. Test 2FA disable

## Security & Implementation Notes

**Security:**
- TOTP secrets stored encrypted (same as SSO client secrets)
- Backup codes bcrypt-hashed (same as passwords)
- Grace periods use UTC to avoid timezone issues
- Rate limiting should be added to `/auth/verify-2fa` (future enhancement)
- Single-use backup codes prevent reuse

**Multi-tenancy:**
- All 2FA data scoped by `organization_id`
- Partial unique indexes ensure one active setting per org and one active 2FA per user
- Comprehensive tenant isolation tests validate cross-org security

**Known Limitations:**
- Grace period notifications sent once when policy changes; no reminder notifications before enforcement
- No admin override to disable 2FA for specific user in emergency
- Backup codes cannot be regenerated without disabling/re-enabling 2FA (security trade-off)

**Future Enhancements:**
- Hardware security key support (WebAuthn/FIDO2)
- SMS-based 2FA option
- Remember device functionality
- 2FA adoption metrics dashboard
- Recovery codes via email option

**Troubleshooting:**
- Can't login with 2FA code: Ensure device time synchronized (TOTP is time-based); try backup code
- Can't enable 2FA in org: Verify super admin allowed it; check `two_factor:write` permission
- Notifications not sending: Check Redis/ARQ worker status; verify notification preferences configured
