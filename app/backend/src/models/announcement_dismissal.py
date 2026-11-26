"""
Announcement dismissal tracking model.
Records when users dismiss announcements.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.announcement import Announcement
    from src.models.user import User


class AnnouncementDismissal(Base):
    """
    Tracks user-specific dismissal of announcements.

    Each user can dismiss each announcement once.
    Unique constraint on (announcement_id, user_id).
    """

    __tablename__ = "announcement_dismissal"

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

    announcement_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("announcement.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    dismissed_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    announcement: Mapped[Announcement] = relationship(
        "Announcement", back_populates="dismissals"
    )
    user: Mapped[User] = relationship("User")

    # Partial unique index: one active dismissal per user per announcement
    __table_args__ = (
        Index(
            "uq_announcement_dismissal_active",
            "announcement_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        Index("idx_dismissal_user", "user_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AnnouncementDismissal {self.user_id} dismissed {self.announcement_id}>"
        )
