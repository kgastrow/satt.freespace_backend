# Media Thumbnails Feature

**ADW ID:** 20260116194536-e1446e1b
**Date:** 2026-01-16
**Specification:** specs/multi-phase/issue-177-adw-20260116194536-e1446e1b-multi-phase.md

## Summary

Automatic thumbnail generation for uploaded images. 200px max dimension WebP thumbnails are generated and stored alongside originals. Frontend displays thumbnails; full images load only for lightbox/download.

## Implementation

### Backend Files

**Database & Models:**
- `app/backend/alembic/versions/67f805fe9310_.py` - Migration adding thumbnail_url column
- `app/backend/src/models/media.py` - Added nullable thumbnail_url (String, 1024 chars)
- `app/backend/src/serialisers/media.py` - Updated serializers to include thumbnail_url

**Services:**
- `app/backend/src/services/thumbnail.py` - ThumbnailService class (lines 45-123):
  - 200px max dimension, aspect ratio preserved
  - WebP format, 85% quality
  - Handles RGBA/LA/P by converting to RGB with white background
  - Returns ThumbnailGenerationResult with status and binary data

- `app/backend/src/services/media_upload.py` (lines 181-210):
  - Generates thumbnails only for image types
  - Uploads thumbnail to S3 with `_thumb.webp` suffix
  - Base64 storage encodes thumbnail as data URL
  - Cleans up both original and thumbnail on error

**API:**
- `app/backend/src/api/user.py` (lines 189-224):
  - `GET /user/me` returns avatar_url (thumbnail) and full_avatar_url (original)
  - `POST /user/avatar` returns both URLs
  - Helper: `get_media_thumbnail_url` for presigned URLs
  - Fallback to full URL if thumbnail unavailable

- `app/backend/src/api/media.py` - Media download supports thumbnail URLs

**Testing:**
- `app/backend/tests/unit_tests/test_media_thumbnails.py` - 434 lines covering thumbnail generation, S3/base64 storage, avatar endpoints, non-image media, error handling, tenant isolation

**Dependencies:**
- `app/backend/requirements.txt` - Added Pillow

### Frontend Files

- `app/frontend/src/types/auth.ts` - Added full_avatar_url to UserProfileResponse
- `app/frontend/src/features/user/userApi.ts` - Handles both avatar URLs
- `app/frontend/src/features/media/mediaApi.ts` - Includes thumbnail_url
- `app/frontend/src/components/ui/UserAvatar.tsx` - Uses thumbnail by default, accepts optional fullImageUrl prop
- `app/frontend/src/components/AnnouncementCard.tsx` - Displays thumbnails in card view
- `app/frontend/src/components/MediaUploader.tsx` - Shows thumbnail after upload
- `app/frontend/src/locales/*/common.json` - i18n for 5 locales

### Configuration

| Setting | Value | Location |
|---------|-------|----------|
| MAX_THUMBNAIL_DIMENSION | 200px | `thumbnail.py:22` |
| THUMBNAIL_FORMAT | WebP | `thumbnail.py:23` |
| THUMBNAIL_QUALITY | 85% | `thumbnail.py:24` |

**Storage pattern:**
- Original: `{org_id}/image/{uuid}_{filename}`
- Thumbnail: `{org_id}/image/{uuid}_thumb.webp`

## Usage

Backend (automatic during upload):
```python
result = await upload_media(
    session=session,
    file_data=image_file,
    filename="profile.jpg",
    content_type="image/jpeg",
    media_type=MediaType.IMAGE,
    media_use=MediaUse.AVATAR,
    organization_id=org_id
)
# result.thumbnail_url contains S3 URL or base64 data URL
```

Frontend:
```tsx
<UserAvatar avatarUrl={user.avatar_url} fullImageUrl={user.full_avatar_url} />
<AnnouncementCard announcement={announcement} />
<MediaUploader onUploadSuccess={handleUpload} />
```

## Testing

```bash
cd app/backend
make test
pytest tests/unit_tests/test_media_thumbnails.py -v
```

Coverage: thumbnail dimensions, WebP validation, S3/base64 storage, avatar endpoints, non-image media handling, error handling, tenant isolation.

## Key Design Decisions

- **Synchronous generation** during upload for simplicity (consider background jobs for very large images)
- **WebP compression** provides 30-50% reduction vs JPEG/PNG
- **Graceful fallback** if Pillow unavailable or generation fails
- **Multi-tenancy** follows original media patterns
- **Backwards compatible** - existing media without thumbnails fallback to full images
- **Works with both S3 and base64 storage**
