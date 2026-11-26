# File Management System

S3-based file storage with presigned URLs, usage tracking, quota enforcement, and thumbnail generation. Includes local storage provider for development.

## Key Files

```
app/backend/src/
├── models/
│   ├── file.py                         # File metadata
│   ├── file_usage.py                   # Per-user/org usage stats
│   └── organization_file_settings.py   # Org settings (quotas, allowed types)
├── services/files/
│   ├── base.py                         # Abstract StorageProvider
│   ├── s3_storage.py                   # AWS S3 implementation
│   ├── local_storage.py                # Local filesystem (dev only)
│   ├── file_manager.py                 # Main service
│   ├── usage_tracker.py                # Quota tracking
│   └── validators.py                   # Extension/size/content validation
├── crud/file.py, file_usage.py, file_settings.py
├── api/file.py                         # File endpoints
└── api/file_serve.py                   # Local file serving
```

## Core Principles

1. **Multi-tenancy**: All files scoped by `organization_id`
2. **Presigned URLs**: Never expose raw S3 credentials
3. **Soft deletes**: Set `deleted_time`, hard delete after retention period
4. **Quota enforcement**: Check before generating upload URLs
5. **Magic byte validation**: Verify file content matches extension on upload
6. **Public files**: `is_public=True` bypasses authentication

## Models

### File
| Field | Type | Description |
|-------|------|-------------|
| `organization_id` | UUID (FK) | Required - tenant isolation |
| `uploaded_by_user_id` | UUID (FK) | Who uploaded |
| `original_filename` | String(255) | User's filename |
| `storage_key` | String(512) | S3 key (unique via partial index) |
| `content_type` | String(100) | MIME type |
| `file_extension` | String(20) | Extracted extension |
| `size_bytes` | BigInteger | File size |
| `status` | String(20) | `pending`, `ready`, `failed` (soft delete uses `deleted_time`) |
| `category` | String(50) | `image`, `video`, `document`, `audio`, `other` |
| `extra_data` | JSON | Metadata (dimensions, duration) |
| `media_use` | Enum | `avatar`, `announcement`, `help_article`, `other` |
| `is_public` | Boolean | If true, accessible without authentication |
| `thumbnail_storage_key` | String(512) | Auto-generated thumbnail for images |
| `download_count` | Integer | Incremented on each download URL generation |

### FileUsage
Tracks per-user totals: `total_files`, `total_size_bytes`, plus by category.

### OrganizationFileSettings
| Field | Default | Description |
|-------|---------|-------------|
| `max_file_size_bytes` | 100MB | General upload limit |
| `max_video_size_bytes` | 100MB | Video-specific limit |
| `allowed_extensions` | JSON array | Configurable per-org |
| `user_storage_quota_bytes` | NULL | Per-user limit (NULL=unlimited) |
| `org_storage_quota_bytes` | NULL | Org-wide limit (NULL=unlimited) |
| `signed_url_expiry_seconds` | 3600 | URL validity |
| `deleted_file_retention_days` | 30 | Days before hard delete |

## Storage Provider Interface

```python
class StorageProvider(ABC):
    provider_name: str
    async def upload(file_data, storage_key, content_type, metadata) -> UploadResult
    async def delete(storage_key) -> bool
    async def exists(storage_key) -> bool
    async def generate_download_url(storage_key, expires_in, filename) -> SignedUrlResult
    async def generate_upload_url(storage_key, content_type, expires_in) -> SignedUrlResult
    async def get_file_size(storage_key) -> int | None
    async def download_bytes(storage_key, max_bytes) -> bytes | None
```

### Providers
- **S3StorageProvider**: Production - uses `aioboto3` for async S3 operations
  - Presigned PUT URLs for direct client-to-S3 uploads
  - Presigned GET URLs for downloads
- **LocalStorageProvider**: Development only
  - **No presigned upload URLs** - `generate_upload_url()` returns `/api/v1/files/upload` (method=POST), use direct upload instead
  - Downloads via `/api/v1/files/serve/{storage_key}?token=...` (signed token for auth)
  - Path traversal protection (CWE-22 prevention)

## Storage Key Format

```
{org_id}/{category}/{uuid}_{sanitized_filename}
Example: abc123-uuid/image/a1b2c3d4_profile_photo.jpg
```

Sanitization: alphanumeric + `.`, `_`, `-` only; max 100 chars (extension preserved).

## Upload Flow (Presigned URL)

### 1. Get Upload URL: `POST /api/v1/files/upload-url`
```json
{"filename": "photo.jpg", "content_type": "image/jpeg", "size_bytes": 102400}
```
Server validates extension, size, **checks user and org quotas BEFORE generating URL**; creates pending file record; returns presigned PUT URL.

**Note**: For LocalStorageProvider, the returned URL points to the direct upload endpoint (`/api/v1/files/upload`) since local storage cannot generate presigned PUT URLs. Use direct upload for local development.

### 2. Client Uploads to S3
PUT directly to `upload_url` with `Content-Type` header.

### 3. Complete: `POST /api/v1/files/upload-complete`
```json
{"file_id": "uuid-from-step-1"}
```
Server verifies file in storage, validates content via magic bytes, generates thumbnail for images (see below), updates usage stats, sets status=`ready`.

### Direct Upload: `POST /api/v1/files/upload`
Multipart form upload for smaller files. Performs same validation + thumbnail generation.

## Thumbnail Generation

For image files (category=`image`, content_type starts with `image/`):
1. Full image downloaded from storage
2. Pillow resizes to max 200px (maintains aspect ratio)
3. Converts to WebP format (85% quality)
4. Uploaded with key: `{original_key_prefix}_thumb.webp`
5. `thumbnail_storage_key` stored on File record

Requires `Pillow` library. Gracefully skips if unavailable.

## Download Flow

`GET /api/v1/files/{file_id}/download` returns `{download_url, expires_at, filename}`.

`GET /api/v1/files/{file_id}/thumbnail` returns thumbnail URL (images only).

## FileManager Methods

| Method | Purpose |
|--------|---------|
| `initiate_upload()` | Creates pending file, returns presigned URL |
| `complete_upload()` | Verifies upload, validates content, generates thumbnail, marks ready |
| `upload_direct()` | Server-side upload with validation + thumbnail |
| `get_download_url()` | Returns presigned download URL |
| `get_thumbnail_url()` | Returns presigned thumbnail URL |
| `soft_delete()` | Sets `deleted_time`, updates usage |
| `hard_delete()` | Removes from storage + database |

## Validation

### Default Allowed Extensions
Images: `jpg`, `jpeg`, `png`, `gif`, `webp`, `svg`, `bmp`, `ico`
Videos: `mp4`, `mov`, `avi`, `webm`, `mkv`, `m4v`
Audio: `mp3`, `wav`, `ogg`, `m4a`, `flac`
Documents: `pdf`, `doc`, `docx`, `xls`, `xlsx`, `ppt`, `pptx`, `odt`, `ods`, `odp`, `txt`, `csv`
Other: `zip`, `json`, `xml`, `html`, `css`, `js`

### File Categories
Extensions map to categories for quotas: `image`, `video`, `audio`, `document`, `other`.

## Content Validation (Magic Bytes)

**Security Feature**: Prevents uploading malicious files disguised as safe types.

1. On upload completion, first 2048 bytes are fetched
2. `python-magic` detects actual MIME type
3. Detected type validated against declared extension
4. Invalid files deleted from storage and marked `failed`

**Behavior:**
- Generic types (`application/octet-stream`, empty files): Allowed
- Text types: Permissive matching for text extensions
- Office documents: Accepts zip detection (they're zip-based)
- Detection failure: Logs warning, allows upload (graceful degradation)
- Requires: `python-magic` library

## Background Workers

| Task | Trigger | Purpose |
|------|---------|---------|
| `cleanup_deleted_files_task` | Cron (daily) | Hard delete files past retention period |
| `process_file_upload_task` | On upload | Extract metadata (dimensions, duration) |
| `recalculate_usage_task` | Manual | Recalculate org usage stats |

## API Endpoints

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /api/v1/files/upload` | User | Direct multipart upload |
| `POST /api/v1/files/upload-url` | User | Get presigned upload URL |
| `POST /api/v1/files/upload-complete` | User | Confirm presigned upload |
| `GET /api/v1/files` | User | List user's files |
| `GET /api/v1/files/organization` | Admin | List all org files |
| `GET /api/v1/files/{id}` | User | Get file metadata |
| `GET /api/v1/files/{id}/download` | User | Get download URL |
| `GET /api/v1/files/{id}/thumbnail` | User | Get thumbnail URL |
| `DELETE /api/v1/files/{id}` | User | Soft delete (own files or with permission) |
| `GET /api/v1/files/usage` | User | User's usage stats |
| `GET /api/v1/files/usage/organization` | Admin | Org-wide usage |
| `GET /api/v1/files/settings` | Admin | Get org file settings |
| `PUT /api/v1/files/settings` | Admin | Update org file settings |

## Security Requirements

1. **Presigned URLs**: Configurable expiry via `signed_url_expiry_seconds`
2. **Magic byte validation**: Content must match extension
3. **Size limits**: Enforced before upload URL generated
4. **Quota enforcement**: User and org quotas checked
5. **Multi-tenancy**: Always filter by `organization_id`
6. **File type restrictions**: Configurable per organization
7. **Path traversal protection**: LocalStorageProvider validates containment
8. **Public files**: Only explicitly marked files skip authentication
9. **Delete permissions**: Users can only delete own files unless they have `files:delete_others` or `files:admin`
10. **Frontend URL validation (SEC-F-011)**: Download URLs must be validated before opening

## Frontend Download URL Validation

When opening download URLs in the frontend, validate the URL origin:

```typescript
import { safeOpenDownloadUrl } from '@/lib/url-validation'

const handleDownload = async (fileId: string) => {
  const result = await getDownloadUrl(fileId).unwrap()
  if (!safeOpenDownloadUrl(result.download_url)) {
    toast.error('Invalid download URL')
  }
}
```

Prevents open redirect attacks. Allowed domains configured in `url-validation.ts`.

## Testing Patterns

```python
# Extension validation
result = file_validator.validate_extension("photo.jpg")
assert result.valid and result.category == "image"

# Magic byte content validation
result = file_validator.validate_content_type_by_magic_bytes("test.jpg", file_data)
assert result.valid  # Only if file_data contains actual JPEG bytes

# Multi-tenancy isolation
async def test_cannot_access_other_org_files():
    # User from org_a cannot access files from org_b

# Path traversal protection (local storage)
async def test_path_traversal_blocked():
    # Attempts like "../../../etc/passwd" should raise ValueError
```

## Configuration

### Storage Provider Selection

```python
# Production: S3
from src.services.files.s3_storage import init_s3_storage
s3_provider = init_s3_storage(bucket="my-bucket", region="us-east-1")
file_manager = init_file_manager(s3_provider)

# Development: Local
from src.services.files.local_storage import init_local_storage
local_provider = init_local_storage(storage_path="./storage", base_url="http://localhost:8000")
file_manager = init_file_manager(local_provider)
```

### Environment Variables
| Variable | Description |
|----------|-------------|
| `FILE_STORAGE_PROVIDER` | `s3` or `local` |
| `S3_BUCKET` | S3 bucket name |
| `S3_REGION` | AWS region |
| `S3_ENDPOINT_URL` | Custom S3 endpoint (MinIO, etc.) |
| `LOCAL_STORAGE_PATH` | Directory for local storage |
| `LOCAL_STORAGE_BASE_URL` | Base URL for local file serving |
