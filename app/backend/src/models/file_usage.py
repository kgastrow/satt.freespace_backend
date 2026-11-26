"""
FileUsage model for tracking storage usage per user and organization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class FileUsage(Base):
    """
    Track file storage usage per user and organization.

    Maintains running totals of:
    - Total files and size
    - Breakdown by category (image, video, document, other)

    Used for:
    - Quota enforcement
    - Usage reporting
    - Billing (if applicable)

    Multi-tenant: Usage records are scoped to an organization.
    """

    __tablename__ = "file_usage"

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
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # Overall usage stats
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Image usage
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Video usage
    video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    video_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Document usage
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    document_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Audio usage
    audio_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    audio_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Other files usage
    other_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    other_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False, default=0)

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="file_usages"
    )
    user: Mapped[User] = relationship("User", back_populates="file_usage")

    __table_args__ = (
        # Partial unique index - one usage record per user per org
        Index(
            "uq_file_usage_org_user_active",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        # Composite index for queries filtering by org + user + soft delete status
        Index(
            "ix_file_usage_org_user_deleted",
            "organization_id",
            "user_id",
            "deleted_time",
        ),
    )

    def __repr__(self) -> str:
        return f"<FileUsage user={self.user_id} files={self.total_files} size={self.total_size_bytes}>"
