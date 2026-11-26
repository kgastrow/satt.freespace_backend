"""
File model for tracking uploaded files and their storage references.

This is the unified file/media storage system supporting:
- Documents, images, videos, and other file types
- Local and S3 storage providers
- Thumbnail generation for images
- Media use case tracking (avatar, announcement, help_article, etc.)
"""

from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import BIGINT, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class MediaUse(str, enum.Enum):
    """Context where media/file is used, for categorization and retention policy tracking."""

    AVATAR = "avatar"
    ANNOUNCEMENT = "announcement"
    HELP_ARTICLE = "help_article"
    OTHER = "other"


class File(Base):
    """
    File metadata and tracking.

    Stores information about uploaded files including:
    - Original filename and content type
    - S3 storage location (bucket/key)
    - File size and category
    - Upload status and access tracking

    Multi-tenant: Files belong to an organization.
    """

    __tablename__ = "file"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc)
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Multi-tenancy
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Uploader
    uploaded_by_user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # File info
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(
        String(512), nullable=False
    )  # S3 key - uniqueness enforced via partial index

    # Type info
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_extension: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Size
    size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False)

    # Storage
    storage_provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default="s3"
    )  # 's3', 'local'
    bucket_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Status
    # Values: 'pending', 'uploaded', 'processing', 'ready', 'failed', 'deleted'
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    # Optional categorization
    category: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'document', 'image', 'video', 'other'

    # Additional info like dimensions, duration for videos, etc.
    # Example: {"width": 1920, "height": 1080, "duration": 120} for videos
    # Renamed from 'metadata' to avoid SQLAlchemy reserved name
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Media use case tracking (nullable for regular files)
    # e.g., "avatar", "announcement", "help_article", "other"
    # native_enum=False stores the uppercase member NAME as VARCHAR. The width
    # was already the project-wide 50 (~4x the longest member, HELP_ARTICLE),
    # but create_constraint defaults to False in SQLAlchemy 2.0, so this was a
    # free-text VARCHAR: an out-of-range value was accepted on write and only
    # blew up later on READ, as a LookupError deep in the ORM. True emits a
    # CHECK so the database rejects it at the point of writing.
    media_use: Mapped[MediaUse | None] = mapped_column(
        Enum(
            MediaUse,
            native_enum=False,
            length=50,
            create_constraint=True,
            name="ck_file_media_use",
        ),
        nullable=True,
        index=True,
    )

    # Public access flag - if True, file can be accessed without authentication
    # Used for help center images and other publicly accessible content
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Thumbnail support for images
    thumbnail_storage_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    # Access tracking
    download_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_accessed_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="files", foreign_keys=[organization_id]
    )
    uploaded_by: Mapped[User] = relationship(
        "User", foreign_keys=[uploaded_by_user_id], back_populates="uploaded_files"
    )

    # Indexes for common query patterns
    __table_args__ = (
        # Partial unique index for storage_key on active records
        Index(
            "uq_file_storage_key_active",
            "storage_key",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        Index("idx_file_org_category", "organization_id", "category"),
        Index("idx_file_org_status", "organization_id", "status"),
        Index("idx_file_org_created", "organization_id", "created_time"),
        Index("idx_file_org_media_use", "organization_id", "media_use"),
    )

    def __repr__(self) -> str:
        return f"<File {self.original_filename} ({self.id})>"
