# User Avatar Upload

**ADW ID:** 20260115172949-9e9f2b26
**Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-153-adw-20260115172949-9e9f2b26-multi-phase.md

## Overview

User avatar functionality with upload, display, and removal. Extends User model with Media relationship, provides REST API endpoints with validation, and displays avatars with fallback to user initials. Full i18n support (EN, DE, XH, ZU, NSO).

## Technical Implementation

### Files Modified

**Backend:**
- `app/backend/src/models/user.py`: `avatar_media_id` FK and `avatar` relationship (lazy="selectin")
- `app/backend/alembic/versions/554976d91b1b_add_avatar_media_id_to_user.py`: Schema migration
- `app/backend/src/api/user.py`: POST/DELETE `/users/me/avatar` endpoints
- `app/backend/src/crud/user.py`: `update_user_avatar` function
- `app/backend/src/serialisers/user.py`: `AvatarUploadResponse`, `DeleteAvatarResponse`, `avatar_url` field
- `app/backend/src/core/response_codes.py`: Avatar response codes
- `app/backend/src/models/media.py`: User avatar relationship type hint
- `app/backend/tests/unit_tests/test_user_avatar.py`: Test suite (427 lines)

**Frontend:**
- `app/frontend/src/components/ui/UserAvatar.tsx`: Reusable avatar component (sm/md/lg sizes)
- `app/frontend/src/pages/ProfilePage.tsx`: Upload interface with preview
- `app/frontend/src/components/HeaderUserMenu.tsx`: Avatar integration
- `app/frontend/src/features/user/userApi.ts`: Upload/delete mutations
- `app/frontend/src/features/auth/authSlice.ts`: `avatar_url` type support
- `app/frontend/src/types/auth.ts`: User type extension
- `app/frontend/src/locales/{en,de,xh,zu,nso}/settings.json`: i18n translations

### API Endpoints

**POST `/users/me/avatar`**
- Accepts: multipart file upload
- Validates: image types (JPEG, PNG, GIF, WEBP), file size
- Creates: Media record with `MediaUse.AVATAR`
- Returns: `AvatarUploadResponse` with avatar URL
- Logs: audit trail

**DELETE `/users/me/avatar`**
- Soft-deletes avatar media (sets `deleted_time`)
- Clears user's `avatar_media_id`
- Logs: audit trail

Both endpoints filter by organization_id for multi-tenant isolation.

### Frontend Component

`UserAvatar` component displays uploaded image or falls back to user initials (first letter of first and last name) on:
- Missing avatar
- Load error
- Invalid URL

### Configuration

**Backend:**
- Allowed types: JPEG, PNG, GIF, WEBP (defined in `app/backend/src/api/user.py`)
- Storage: existing `media_upload` service (S3 or base64)
- Size limits: enforced by media_upload service

**Frontend:**
- File size limit: 5MB
- Avatar sizes: sm (24px), md (32px), lg (40px)
- Accepted types: image/jpeg, image/png, image/gif, image/webp

## Testing

**Backend tests:**
```bash
cd app/backend
make test tests/unit_tests/test_user_avatar.py
```

Coverage: model relationships, upload validation, soft delete, multi-tenant isolation, error handling, URL generation.

**Frontend tests:**
```bash
cd app/frontend
npm run test
```

**Manual tests:**
- Upload formats (JPEG, PNG, GIF, WEBP)
- File size validation (>5MB rejection)
- Invalid file types rejection
- Display in header and profile
- Deletion with confirmation
- Initials fallback
- Load error handling
- Multi-tenant isolation

## Architecture Notes

- **Soft Deletes**: Avatar media uses soft delete (`deleted_time`) per project policy
- **Security**: All queries filtered by organization_id; multi-tenant isolation at database level
- **Audit Logging**: Upload/delete operations logged with actor, IP, user agent
- **Reusability**: `UserAvatar` component designed for user lists, comments, etc.
- **Future**: Image preprocessing (resize/crop) and Gravatar integration possible enhancements
