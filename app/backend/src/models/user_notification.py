"""
User notification model for in-app notifications.
Stores notifications that are displayed in the application's notification bell/panel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.notification_category import NotificationCategory
    from src.models.organization import Organization
    from src.models.user import User


class UserNotification(Base):
    """
    In-app notification for a user.

    Stores notifications that are displayed in the notification bell/panel.
    Multi-tenancy: Scoped by organization_id (mandatory).
    """

    __tablename__ = "user_notification"

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

    # Notification content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional link for click-through navigation
    link: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Category (optional) - for filtering and preference resolution
    category_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_category.id"),
        nullable=True,
        index=True,
    )

    # Read status
    read_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user: Mapped[User] = relationship("User", back_populates="in_app_notifications")
    category: Mapped[NotificationCategory | None] = relationship("NotificationCategory")

    __table_args__ = (
        # Composite index for efficient user notification queries
        Index(
            "ix_user_notification_org_user",
            "organization_id",
            "user_id",
        ),
        # Index for listing unread notifications (read_time IS NULL)
        Index(
            "ix_user_notification_user_read",
            "user_id",
            "read_time",
        ),
        # Index for sorting by created_time
        Index(
            "ix_user_notification_user_created",
            "user_id",
            "created_time",
        ),
    )

    def __repr__(self) -> str:
        return f"<UserNotification id={self.id} user={self.user_id} title={self.title[:30]}>"
