# User Onboarding Flows

**ADW ID:** 20260115223026-77515979 | **Date:** 2026-01-16
**Specification:** specs/multi-phase/issue-161-adw-20260115223026-77515979-multi-phase.md

Multi-tenant user onboarding system with configurable step-by-step wizard flows. Supports multiple user types (individual, business, provider) with SMS OTP verification, optional admin review workflows, and real-time WebSocket + email notifications.

## Implementation Summary

### Backend Models & Database
- `app/backend/src/models/user_type.py`: Global user type configuration
- `app/backend/src/models/user_user_type.py`: Junction table tracking user's onboarding status per type
- `app/backend/src/models/onboarding_step.py`: Steps with validation rules (JSONB)
- `app/backend/src/models/user_onboarding_progress.py`: Step completion tracking
- `app/backend/src/models/phone_verification.py`: OTP storage with expiry/attempt tracking
- `app/backend/alembic/versions/971ed57c87c6_*.py`: Migration for all new tables

### CRUD & Services
- `app/backend/src/crud/user_type.py`: User type operations
- `app/backend/src/crud/onboarding_step.py`: Step CRUD with reordering
- `app/backend/src/crud/user_onboarding_progress.py`: Progress tracking (org_id filtered)
- `app/backend/src/crud/phone_verification.py`: OTP lifecycle management
- `app/backend/src/services/onboarding.py`: Core logic (start, submit_step, check_completion)
- `app/backend/src/services/phone_verification.py`: OTP generation (6-digit), SMS sending, verification
- `app/backend/src/services/onboarding_notifications.py`: Event notification triggers

### APIs & Serializers
- `app/backend/src/api/user_type.py`: Super admin user type management
- `app/backend/src/api/onboarding_step.py`: Super admin step configuration
- `app/backend/src/api/onboarding.py`: User-facing onboarding endpoints
- `app/backend/src/api/onboarding_review.py`: Admin review queue (approve/reject)
- `app/backend/src/serialisers/onboarding.py`: Pydantic request/response models

### Frontend Components
- `app/frontend/src/features/onboarding/OnboardingWizard.tsx`: Main container with step navigation
- `app/frontend/src/features/onboarding/OnboardingStep.tsx`: Dynamic form rendering per step
- `app/frontend/src/features/onboarding/PhoneVerificationStep.tsx`: OTP input with countdown timer
- `app/frontend/src/features/onboarding/OnboardingProgressCard.tsx`: Dashboard progress card
- `app/frontend/src/features/onboarding/ReviewSubmissionDialog.tsx`: Admin review modal
- `app/frontend/src/pages/OnboardingPage.tsx`: User onboarding at `/onboarding`
- `app/frontend/src/pages/admin/OnboardingReviewPage.tsx`: Admin queue at `/admin/onboarding-review`
- `app/frontend/src/store/api/onboardingApi.ts`: RTK Query endpoints

### i18n & Testing
- `app/frontend/src/locales/{en,de,xh,zu,nso}/onboarding.json`: Wizard translations
- `app/frontend/src/locales/{en,de,xh,zu,nso}/admin.json`: Admin interface translations
- `app/backend/tests/unit_tests/test_onboarding.py`: 2,561 lines of tests

## Key Technical Decisions

**Multi-tenancy**: All tenant-scoped models (UserUserType, UserOnboardingProgress, PhoneVerification) require `organization_id` filtering. Admins can only review submissions for their organization.

**Phone Verification Security**: OTPs hashed with bcrypt, 5-minute expiry, max 3 verification attempts, rate limiting (3 sends/phone/hour).

**Dynamic Validation**: Steps define `required_fields` and `validation_rules` in JSONB for flexible form generation without schema changes.

**Admin Review Workflow**: User types with `requires_manual_review=True` enter `pending_review` status; others auto-approve. Real-time WebSocket broadcasts to org admins, email notifications for all status changes.

**Authorization**: Super admin routes use `get_current_super_admin`, admin review uses `get_current_user_admin`, user onboarding uses `get_current_user`.

**Data Model**: All models include `deleted_time` field for soft deletes (project pattern).

## Configuration

### Phone Verification
- OTP length: 6 digits
- OTP expiry: 5 minutes
- Max verification attempts: 3
- Rate limit: 3 OTP sends per phone per hour

### User Type Fields
- `requires_onboarding`: Whether this type requires onboarding
- `requires_manual_review`: Whether submissions need admin approval
- `is_default`: Auto-assign to new users
- `display_order`: Sort order in selection UI

### Onboarding Step Fields
- `required_fields`: JSON array of field configurations (name, type, label, validation)
- `validation_rules`: JSON object with custom validation logic
- `requires_verification`: Whether step needs phone verification
- `step_order`: Sequential order within user type

## Usage

### User Flow
1. After email verification, incomplete onboarding redirects to `/onboarding`
2. Select user type → complete steps (SMS OTP may be required)
3. Submit for review → notifications to org admins if manual review enabled
4. Dashboard shows progress card with completion status

### Admin Flow
1. Navigate to `/admin/onboarding-review` (owner/admin role required)
2. View pending submissions with user info and dates
3. Click submission to review data per step in modal
4. Approve (activate user) or reject (with reason) → user receives notification

### Super Admin Flow
1. `/admin/user-types` endpoints: create/update user types
2. `/admin/onboarding-steps` endpoints: define steps with validation rules
3. Toggle `requires_manual_review` to enable/disable review workflow

## Testing

**Backend**: `cd app/backend && make test` - Covers models, CRUD, services, APIs, multi-tenancy isolation, OTP lifecycle, rate limiting, admin review, and notifications.

**Frontend**: `cd app/frontend && npm run test`

**E2E Manual Testing**:
- Complete onboarding flow with phone verification
- Verify WebSocket notifications arrive for admin when submission received
- Test rate limiting (4th OTP send within 1 hour should fail)
- Test max attempts (3 failed verifications should block)
- Verify cross-tenant data isolation

## Database Migration

```bash
cd app/backend
make migrate
```

## Notes

- Feature flags available for gradual rollout (production-ready)
- JSONB fields allow adding validation rules without schema changes
- New user types/steps can be added via API without code changes
- All OTPs hashed with bcrypt; phone verification updates `User.phone_verified`
- Existing users without onboarding requirements unaffected
- WebSocket leverages existing infrastructure for real-time notifications
