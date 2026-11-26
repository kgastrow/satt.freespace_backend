"""
Changelog view tracking model.
Records when users view changelog entries.
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
    from src.models.changelog import Changelog
    from src.models.user import User


class ChangelogView(Base):
    """
    Tracks which users have viewed which changelog entries.

    Each user can view each changelog entry once (tracked).
    Unique constraint on (changelog_id, user_id) where deleted_time IS NULL.
    """

    __tablename__ = "changelog_view"

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

    changelog_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("changelog.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    viewed_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    changelog: Mapped[Changelog] = relationship("Changelog", back_populates="views")
    user: Mapped[User] = relationship("User")

    # Partial unique index: one active view per user per changelog entry
    __table_args__ = (
        Index(
            "uq_changelog_view_active",
            "changelog_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        Index("idx_changelog_view_user", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<ChangelogView {self.user_id} viewed {self.changelog_id}>"
