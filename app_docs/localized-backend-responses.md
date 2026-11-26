# Localized Backend Response Messages

**ADW ID:** 20260114104950-a996facb | **Date:** 2026-01-14 | **Spec:** specs/issue-130-adw-20260114104950-a996facb-sdlc_planner-localized-backend-response-messages.md

## Overview

Backend i18n system enabling frontend to display localized error and success messages in 5 languages (EN, DE, XH, ZU, NSO). Backend provides translation codes (`message_code` for success, `detail_code` for errors) alongside English messages; frontend prioritizes codes with graceful fallback to English for debugging.

## Implementation

### Backend Files Modified

**Core Infrastructure:**
- `app/backend/src/core/response_codes.py`: 70+ response codes by domain (auth, user, org, role, file, notification, SSO, OTP, impersonation)
- `app/backend/src/core/exceptions.py`: `create_http_exception()` and `create_success_response()` helpers
- `app/backend/src/serialisers/common.py`: `MessageResponse` base class with `message_code` field
- `app/backend/main.py`: Global exception handler preserves `detail_code`

**API Endpoints (14 files):**
- `auth.py`, `user.py`, `organization.py`, `role.py`, `api_key.py`, `file.py`, `admin.py`, `notification.py`, `impersonation.py`, `organization_sso_settings.py`, `sso.py`, `user_otp.py`, `user_role.py`, `users.py`

**Response Serializers (12 files):**
- `auth.py`, `user.py`, `organization.py`, `role.py`, `api_key.py`, `file.py`, `notification.py`, `admin.py`, `impersonation_session.py`, `user_notification.py`, `user_otp.py`, `user_role.py`

### Frontend Files Modified

**Translation Infrastructure:**
- `app/frontend/src/locales/{en,de,xh,zu,nso}/backend.json`: 121 translation keys per language
- `app/frontend/src/i18n/config.ts`: Load backend namespace
- `app/frontend/src/types/api.ts`: `getErrorMessage()` (prioritizes `detail_code`), `getSuccessMessage()`

**Components (6 files):**
- `login-form.tsx`, `ProfilePage.tsx`, `RegisterPage.tsx`, `ResetPasswordPage.tsx`, `VerifyEmailPage.tsx`, `settings/PasswordPage.tsx`

**Testing:**
- `app/backend/tests/api_tests/test_localized_responses.py`: 726-line test suite validating all endpoints

## Key Design Decisions

1. **Additive Only**: New fields (`message_code`, `detail_code`) don't modify existing fields—fully backwards compatible
2. **Centralized Codes**: `response_codes.py` is single source of truth using dot notation (e.g., `auth.invalid_credentials`)
3. **English Persistence**: Backend logs/responses always include English for developer debugging without translation
4. **Graceful Fallback**: Missing translations fall back to English message from backend
5. **Hierarchical Organization**: Dot notation enables self-documenting codes and clean translation file structure

## Usage

### Backend: Add Translated Response

1. Define code in `app/backend/src/core/response_codes.py`:
```python
"feature.action_completed": "feature.action_completed",
```

2. Use helpers in endpoints:
```python
from src.core.exceptions import create_http_exception, create_success_response

# Error
raise create_http_exception(status_code=404, detail="Not found", detail_code="feature.not_found")

# Success
return create_success_response(message="Done", message_code="feature.action_completed", data=result)
```

3. Update serializer:
```python
class FeatureResponse(BaseModel):
    data: FeatureData
    message: str
    message_code: str
```

### Frontend: Display Localized Message

```tsx
import { useTranslation } from 'react-i18next'
import { getErrorMessage, getSuccessMessage } from '@/types/api'

const { t } = useTranslation(['backend'])

try {
  await apiCall()
} catch (error) {
  toast.error(getErrorMessage(error, t))
}

const response = await apiCall()
toast.success(getSuccessMessage(response, t))
```

### Add Language Support

1. Create `app/frontend/src/locales/{lang}/backend.json`
2. Mirror structure from `en/backend.json` with translations
3. Update i18n config if necessary

## Testing

```bash
# Backend: validate all responses include codes
cd app/backend && uv run pytest tests/api_tests/test_localized_responses.py -v

# Frontend: test translation fallback
cd app/frontend && npm run test

# Manual: change language, trigger operations, verify translations
```

## Limitations & Future Work

**Limitations:**
- Codes are English-centric structure
- Manual translation required for each language
- Backend messages English-only (by design)

**Future:**
- Startup validation for missing codes
- Translation file synchronization automation
- Context metadata for professional translators
- Telemetry tracking for common translations
