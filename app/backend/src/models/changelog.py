"""
Changelog model for versioned release notes.
Supports platform-wide and per-organization entries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.changelog_view import ChangelogView
    from src.models.organization import Organization
    from src.models.user import User


class Changelog(Base):
    """
    Versioned release notes / changelog entry.

    Multi-tenancy: NULL organization_id = platform-wide, UUID = org-specific.
    Supports draft/published states, categories, and view tracking.
    """

    __tablename__ = "changelog"

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

    # Multi-tenancy: NULL = platform-wide, UUID = org-specific
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Content
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Category
    category: Mapped[str] = mapped_column(
        Enum(
            "feature",
            "improvement",
            "bugfix",
            "breaking",
            "other",
            name="changelog_category",
        ),
        nullable=False,
        default="other",
    )

    # Scheduling / visibility
    release_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Creator
    created_by_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )

    # Relationships
    organization: Mapped[Organization | None] = relationship("Organization")
    created_by: Mapped[User] = relationship("User")
    views: Mapped[list[ChangelogView]] = relationship(
        "ChangelogView", back_populates="changelog"
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index(
            "idx_changelog_org_release_date",
            "organization_id",
            "release_date",
        ),
        Index(
            "idx_changelog_published_release_date",
            "is_published",
            "release_date",
        ),
    )

    def __repr__(self) -> str:
        scope = "platform-wide" if self.organization_id is None else "org-specific"
        return f"<Changelog {self.version} - {self.title} ({scope})>"
