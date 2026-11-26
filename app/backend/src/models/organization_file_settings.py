"""
OrganizationFileSettings model for per-organization file upload configuration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import BIGINT, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


# Default allowed file extensions
DEFAULT_ALLOWED_EXTENSIONS = [
    # Images
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    # Documents
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    # Videos
    "mp4",
    "mov",
    "avi",
    "webm",
    # Audio
    "mp3",
    "wav",
    # Other
    "zip",
    "txt",
    "csv",
]


class OrganizationFileSettings(Base):
    """
    Per-organization file upload settings.

    Configures:
    - Maximum file sizes (general and per-type)
    - Allowed file extensions
    - Storage quotas (per-user and per-org)
    - Signed URL expiry
    - Retention periods for deleted files

    One settings record exists per organization.
    Includes deleted_time for cascade soft-delete when organization is deleted.
    """

    __tablename__ = "organization_file_settings"

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

    # Organization - one settings per org
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # File size limits (in bytes)
    max_file_size_bytes: Mapped[int] = mapped_column(
        BIGINT, nullable=False, default=104857600
    )  # 100MB default
    max_video_size_bytes: Mapped[int] = mapped_column(
        BIGINT, nullable=False, default=104857600
    )  # 100MB for videos

    # Allowed file extensions (JSON array)
    allowed_extensions: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=lambda: DEFAULT_ALLOWED_EXTENSIONS
    )

    # Storage quotas (in bytes) - NULL means unlimited
    user_storage_quota_bytes: Mapped[int | None] = mapped_column(
        BIGINT, nullable=True
    )  # Per-user quota
    org_storage_quota_bytes: Mapped[int | None] = mapped_column(
        BIGINT, nullable=True
    )  # Organization-wide quota

    # Signed URL configuration
    signed_url_expiry_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3600
    )  # 1 hour default

    # Retention for soft-deleted files (days before hard delete)
    deleted_file_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30
    )

    # Relationship
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="file_settings"
    )

    __table_args__ = (
        # Partial unique index - one settings record per org
        Index(
            "uq_org_file_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationFileSettings org={self.organization_id}>"
