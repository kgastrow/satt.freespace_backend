"""
File API serializers.
Pydantic models for file management request/response validation.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MediaUse(str, Enum):
    """Context where media/file is used, for categorization and retention policy tracking."""

    AVATAR = "avatar"
    ANNOUNCEMENT = "announcement"
    HELP_ARTICLE = "help_article"
    OTHER = "other"


class FileResponse(BaseModel):
    """Response schema for a single file."""

    id: UUID
    created_time: datetime
    organization_id: UUID
    uploaded_by_user_id: UUID
    original_filename: str
    storage_key: str
    content_type: str
    file_extension: Optional[str] = None
    size_bytes: int
    storage_provider: str
    bucket_name: Optional[str] = None
    status: str
    category: Optional[str] = None
    extra_data: Optional[dict] = None
    download_count: int
    last_accessed_time: Optional[datetime] = None
    # Media-specific fields
    media_use: Optional[MediaUse] = None
    is_public: bool = False  # Whether file can be accessed without authentication
    thumbnail_storage_key: Optional[str] = None
    thumbnail_url: Optional[str] = None  # Computed field for presigned URL

    model_config = ConfigDict(from_attributes=True)


class FileListResponse(BaseModel):
    """Response schema for paginated file list."""

    items: list[FileResponse]
    total: int
    limit: int
    offset: int

    model_config = ConfigDict(extra="forbid")


class UploadUrlRequest(BaseModel):
    """Request schema for getting a presigned upload URL."""

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: str = Field(..., min_length=1, max_length=100)
    size_bytes: int = Field(..., gt=0)
    media_use: Optional[MediaUse] = Field(
        None, description="Media use case (avatar, announcement, help_article, other)"
    )
    is_public: bool = Field(
        False,
        description="Whether the file should be publicly accessible without authentication",
    )

    model_config = ConfigDict(extra="forbid")


class UploadUrlResponse(BaseModel):
    """Response schema for presigned upload URL."""

    upload_url: str
    storage_key: str
    expires_at: datetime
    file_id: UUID

    model_config = ConfigDict(extra="forbid")


class UploadCompleteRequest(BaseModel):
    """Request schema for confirming upload completion."""

    file_id: UUID = Field(..., description="ID of the file returned from /upload-url")

    model_config = ConfigDict(extra="forbid")


class UploadCompleteResponse(BaseModel):
    """Response schema for upload completion confirmation."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    file: FileResponse

    model_config = ConfigDict(extra="forbid")


class DownloadUrlResponse(BaseModel):
    """Response schema for signed download URL."""

    download_url: str
    expires_at: datetime
    filename: str

    model_config = ConfigDict(extra="forbid")


class DeleteFileResponse(BaseModel):
    """Response schema for file deletion."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")

    model_config = ConfigDict(extra="forbid")


class FileUsageResponse(BaseModel):
    """Response schema for file usage statistics."""

    total_files: int
    total_size_bytes: int
    image_count: int
    image_size_bytes: int
    video_count: int
    video_size_bytes: int
    document_count: int
    document_size_bytes: int
    other_count: int
    other_size_bytes: int
    user_quota_bytes: Optional[int] = None
    user_quota_used_percent: Optional[float] = None

    model_config = ConfigDict(extra="forbid")


class OrganizationFileUsageResponse(BaseModel):
    """Response schema for organization-wide file usage."""

    total_files: int
    total_size_bytes: int
    org_quota_bytes: Optional[int] = None
    org_quota_used_percent: Optional[float] = None
    user_count: int

    model_config = ConfigDict(extra="forbid")


class FileSettingsResponse(BaseModel):
    """Response schema for organization file settings."""

    id: UUID
    organization_id: UUID
    max_file_size_bytes: int
    max_video_size_bytes: int
    allowed_extensions: list[str]
    user_storage_quota_bytes: Optional[int] = None
    org_storage_quota_bytes: Optional[int] = None
    signed_url_expiry_seconds: int
    deleted_file_retention_days: int

    model_config = ConfigDict(from_attributes=True)


class UpdateFileSettingsRequest(BaseModel):
    """Request schema for updating file settings."""

    max_file_size_bytes: Optional[int] = Field(None, gt=0)
    max_video_size_bytes: Optional[int] = Field(None, gt=0)
    allowed_extensions: Optional[list[str]] = None
    user_storage_quota_bytes: Optional[int] = Field(None, gt=0)
    org_storage_quota_bytes: Optional[int] = Field(None, gt=0)
    signed_url_expiry_seconds: Optional[int] = Field(None, gt=0, le=86400)
    deleted_file_retention_days: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class ThumbnailUrlResponse(BaseModel):
    """Response schema for thumbnail URL."""

    thumbnail_url: str
    expires_at: datetime
    filename: str

    model_config = ConfigDict(extra="forbid")
