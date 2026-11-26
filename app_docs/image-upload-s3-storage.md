# Image Upload with S3 Storage

**ADW ID:** 20260114225831-672f1348
**Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-134-adw-20260114225831-672f1348-multi-phase.md

## Overview

Image/video uploads with S3-compatible storage backend. Falls back to base64 in database for images when S3 disabled; videos require S3. Multi-tenant support with organization-scoped media. Includes `media_use` enum for future retention policy implementation.

## Files Modified

**Backend:**
- `app/backend/src/models/media.py` - Media model with media_type, media_use, S3/base64 storage fields
- `app/backend/src/crud/media.py` - CRUD with tenant isolation
- `app/backend/src/serialisers/media.py` - Pydantic models (request/response)
- `app/backend/src/api/media.py` - API endpoints
- `app/backend/src/services/media_upload.py` - Upload service (S3/base64 logic)
- `app/backend/src/services/files/s3_storage.py` - S3 availability checks
- `app/backend/src/crud/system_config.py` - S3 config management
- `app/backend/src/serialisers/admin.py` - S3 config serializers
- `app/backend/src/api/admin.py` - S3 config endpoints
- `app/backend/alembic/versions/ad83a6a27c87_add_media_table.py` - Database migration
- `app/backend/tests/unit_tests/test_media.py` - Test suite (1185 lines)

**Frontend:**
- `app/frontend/src/components/MediaUploader.tsx` - Drag-and-drop upload component
- `app/frontend/src/features/media/mediaApi.ts` - RTK Query API slice
- `app/frontend/src/pages/admin/AnnouncementsPage.tsx` - MediaUploader integration
- `app/frontend/src/pages/admin/HelpArticlesPage.tsx` - MediaUploader integration
- `app/frontend/src/locales/*/media.json` - i18n translations (5 locales)

## Key Features

- **Multi-tenant**: All media scoped by `organization_id` in CRUD and endpoints
- **Flexible Storage**: Auto-fallback from S3 to base64 for images; video-only S3 requirement
- **Soft Deletes**: Uses `deleted_time` field
- **Type Safety**: Full TypeScript with auto-generated OpenAPI types
- **Comprehensive Tests**: 1185 lines covering upload scenarios, tenant isolation, S3/base64 fallback, errors

## MediaUploader Component Usage

```tsx
import { MediaUploader } from '@/components/MediaUploader'
import { MediaUse } from '@/features/media/mediaApi'

<MediaUploader
  media_use={MediaUse.ANNOUNCEMENT}
  accept="image"
  maxSize={5 * 1024 * 1024}
  onUploadSuccess={(mediaId, mediaUrl) => {
    // Handle successful upload
  }}
/>
```

## API Endpoints

```
POST   /api/v1/media/upload              - Upload media (multipart/form-data)
GET    /api/v1/media                     - List media (filters: media_type, media_use, limit)
GET    /api/v1/media/{media_id}          - Get media details
GET    /api/v1/media/{media_id}/download - Get download URL
DELETE /api/v1/media/{media_id}          - Delete media (soft delete)
```

## Configuration

**S3 Settings (Super Admin):**
- `storage.s3.enabled` - Enable/disable S3 storage
- `storage.s3.bucket` - Bucket name
- `storage.s3.region` - AWS region
- `storage.s3.endpoint_url` - Custom S3 endpoint

**Endpoints:**
```
GET /api/v1/admin/system-config
PUT /api/v1/admin/system-config
```

**Environment Variables:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` (optional)

## Storage Behavior

| Scenario | Behavior |
|----------|----------|
| S3 Enabled | Images and videos → S3 |
| S3 Disabled, Image | → base64 in content_b64 (max 5MB) |
| S3 Disabled, Video | → Error requiring S3 configuration |

## Testing

**Backend:**
```bash
cd app/backend
make test
```

Tests cover: CRUD ops, tenant isolation, upload scenarios, S3 config, error handling.

**Frontend:**
```bash
cd app/frontend
npm run test
```

**Integration:**
```bash
cd app/backend && make lint && make format
cd app/frontend && npm run build && npm run lint
```

## Architecture Notes

- **Media vs Files**: Media model is distinct from File model. Media = images/videos for content (announcements, articles). Files = general user storage.
- **Retention Policy Ready**: `media_use` enum supports future automated retention policies.
- **Presigned URLs**: S3 URLs expire after 1 hour (configurable).

## Limitations

- Videos require S3 configuration
- Base64 storage capped at 5MB for performance
- No automated orphaned media cleanup
