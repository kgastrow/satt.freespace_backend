# Email Change Feature

**ADW ID:** 20260116191421-f34b0fe7 | **Date:** 2026-01-16 | **Spec:** specs/multi-phase/issue-173-adw-20260116191421-f34b0fe7-multi-phase.md

Multi-step email change flow with identity verification (password/2FA), OTP confirmation, session invalidation, and audit logging.

## Files Created

**Backend:**
- `app/backend/src/models/email_change_request.py`: Model with status tracking and OTP management
- `app/backend/src/crud/email_change_request.py`: CRUD operations (182 lines)
- `app/backend/src/api/email_change.py`: API endpoints (503 lines)
- `app/backend/src/serialisers/email_change.py`: Pydantic validation models (91 lines)
- `app/backend/src/services/email_change.py`: Email notification service (209 lines)
- `app/backend/alembic/versions/51d13f621ecb_.py`: Database migration
- `app/backend/tests/unit_tests/test_email_change.py`: Test suite (916 lines)

**Frontend:**
- `app/frontend/src/features/user/emailChangeApi.ts`: RTK Query endpoints (117 lines)
- `app/frontend/src/pages/settings/EmailChangePage.tsx`: Main page (189 lines)
- `app/frontend/src/components/email-change/IdentityVerificationModal.tsx`: Password/2FA modal (263 lines)
- `app/frontend/src/components/email-change/OtpEntryModal.tsx`: OTP modal with resend (218 lines)

**Modified:**
- `app/backend/src/models/__init__.py`, `user.py`, `organization.py`: Relationships
- `app/backend/src/api/v1/__init__.py`: Router registration
- `app/backend/src/api/websocket.py`: WebSocket notifications
- `app/backend/src/core/response_codes.py`: 21 new response codes
- `app/backend/src/crud/refresh_token.py`: Session invalidation
- `app/frontend/src/routes/settingsRoutes.tsx`: /settings/email route
- `app/frontend/src/components/settings/SettingsSidebar.tsx`: Navigation
- `app/frontend/src/locales/{en,de,xh,zu,nso}/settings.json`: Translations (110 lines per language)

## Technical Details

**Database Model:**
- EmailChangeRequest table with `organization_id` foreign key (tenant isolation)
- Status enum: `pending_verification`, `pending_otp`, `completed`, `expired`, `cancelled`
- Identity method tracking: `password`, `totp`, `sms_2fa`
- Hashed OTP with expiry, attempt tracking, and resend count
- Partial unique index: one active request per user
- 1-hour request expiry

**API Endpoints:**
| Endpoint | Method | Rate Limit |
|----------|--------|-----------|
| `/api/v1/users/me/email/change` | POST | 3/day |
| `/api/v1/users/me/email/change/verify` | POST | 5/15min |
| `/api/v1/users/me/email/change/otp` | POST | 3/min |
| `/api/v1/users/me/email/change/resend` | POST | 3/hour, max 3 resends |
| `/api/v1/users/me/email/change` | DELETE | - |
| `/api/v1/users/me/email/change/status` | GET | - |

**Security:**
- 3 max OTP attempts (then cancels request)
- 5 identity verification attempts per 15 minutes
- OTP expires in 10 minutes
- Generic error messages prevent email enumeration
- All refresh tokens invalidated on success
- `email_changed` audit log entry
- Security notifications to old and new emails

**Frontend Features:**
- Zod email validation
- Password/2FA tab toggle
- Auto-submit 6-digit OTP
- Countdown timer for resend
- Full i18n support (en, de, xh, zu, nso)

## User Flow

1. Settings > Change Email
2. Enter new email
3. Verify identity (password or 2FA code)
4. Check new email for OTP
5. Enter OTP (auto-submits at 6 digits, max 3 resends)
6. Success - all sessions invalidated, must log in again

## Configuration & Limits

**In `app/backend/src/api/email_change.py`:**
- `RATE_LIMIT_INITIATE = "3/day"`
- `RATE_LIMIT_IDENTITY_VERIFY = "5/15minutes"`
- `RATE_LIMIT_OTP_VERIFY = "3/minute"`
- `RATE_LIMIT_RESEND = "3/hour"`

**Expiry & Attempts:**
- Request expiry: 1 hour
- OTP expiry: 10 minutes
- Max resends: 3

## Testing

**Backend:** `cd app/backend && make test`
- Model/CRUD with tenant isolation, all endpoints with rate limiting, OTP generation/verification, session invalidation, email notifications, audit logging, error handling

**Frontend:** `cd app/frontend && npm run test`

**Manual:** Start both servers, navigate to http://localhost:5173/settings/email, test complete flow with credentials, verify email delivery, confirm session invalidation.

## Programmatic Usage

```typescript
// Get status
const { data: status } = useGetEmailChangeStatusQuery()
// Returns: { has_pending_request: boolean, status?: string, new_email?: string }

// Cancel
const [cancelEmailChange] = useCancelEmailChangeMutation()
await cancelEmailChange().unwrap()
```

## Architecture & Patterns

- Follows existing PhoneVerification and UserOTP patterns for OTP handling
- Reuses 2FA infrastructure (TOTP/SMS verification)
- OTP codes hashed with bcrypt before storage
- Email enumeration prevented via generic error messages
- Consistent with multi-step verification flows in codebase

## Limitations & Future

**Current Limits:**
- Max 3 requests per 24 hours
- OTP valid for 10 minutes
- 3 max resends per request
- 1-hour request expiry

**Future Enhancements:**
- WebSocket real-time status updates
- Email change history in user settings
- Verification reminder notifications
- Admin override for stuck requests
