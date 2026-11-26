"""
User notification preference models.
Manages user preferences for notification channels and categories.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.notification_category import NotificationCategory
    from src.models.organization import Organization
    from src.models.user import User


class UserNotificationPreference(Base):
    """
    User preferences for notification channels and categories.

    Global preferences for a user including:
    - Channel enablement (email, SMS, WhatsApp, in-app)
    - Quiet hours settings
    """

    __tablename__ = "user_notification_preference"

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

    # Global channel preferences (user can disable entire channels)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether this account may be pushed to at all. Subscribing a device is the
    # other half (see WebPushSubscription); one without the other delivers
    # nothing and reads to the user as a broken toggle.
    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Quiet hours (optional - don't send non-urgent notifications during these hours)
    quiet_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    quiet_hours_start: Mapped[time | None] = mapped_column(
        Time, nullable=True
    )  # e.g., 22:00
    quiet_hours_end: Mapped[time | None] = mapped_column(
        Time, nullable=True
    )  # e.g., 07:00
    quiet_hours_timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="UTC"
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user: Mapped[User] = relationship("User", back_populates="notification_preference")

    __table_args__ = (
        # Partial unique index - one preference record per user per org
        Index(
            "uq_user_notif_pref_org_user_active",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<UserNotificationPreference user={self.user_id}>"


class UserCategoryPreference(Base):
    """
    User preferences for specific notification categories.

    Allows users to enable/disable specific categories per channel.
    """

    __tablename__ = "user_category_preference"

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
    category_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_category.id"),
        nullable=False,
        index=True,
    )

    # Per-channel preferences for this category
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Whether this account may be pushed to at all. Subscribing a device is the
    # other half (see WebPushSubscription); one without the other delivers
    # nothing and reads to the user as a broken toggle.
    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user: Mapped[User] = relationship("User")
    category: Mapped[NotificationCategory] = relationship(
        "NotificationCategory", back_populates="user_preferences"
    )

    __table_args__ = (
        # Partial unique index - one preference per user per category
        Index(
            "uq_user_category_pref_active",
            "user_id",
            "category_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserCategoryPreference user={self.user_id} category={self.category_id}>"
        )
