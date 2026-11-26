"""
Announcement model for organization and platform-wide announcements.
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
    from src.models.announcement_dismissal import AnnouncementDismissal
    from src.models.organization import Organization
    from src.models.user import User


class Announcement(Base):
    """
    Announcement banner notification.

    Multi-tenancy: NULL organization_id = platform-wide, UUID = org-specific.
    Supports priority levels, scheduling, customizable styling, and dismissal tracking.
    """

    __tablename__ = "announcement"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Priority levels
    priority: Mapped[str] = mapped_column(
        Enum("critical", "high", "normal", "low", name="announcement_priority"),
        nullable=False,
        default="normal",
        index=True,
    )

    # Styling
    background_color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    text_color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    featured_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Call-to-action
    cta_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cta_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    cta_dismisses: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    cta_button_color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cta_button_variant: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g., 'solid', 'outline', 'ghost'

    # Dismissal behavior
    is_dismissible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Scheduling
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Creator
    created_by_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="announcements"
    )
    created_by: Mapped[User] = relationship("User")
    dismissals: Mapped[list[AnnouncementDismissal]] = relationship(
        "AnnouncementDismissal", back_populates="announcement"
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index(
            "idx_announcement_org_priority_start",
            "organization_id",
            "priority",
            "start_time",
        ),
        Index("idx_announcement_end_time", "end_time"),
    )

    def __repr__(self) -> str:
        scope = "platform-wide" if self.organization_id is None else "org-specific"
        return f"<Announcement {self.title} ({scope}, {self.priority})>"
