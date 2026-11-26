"""
Notification category model.
Categories that users can subscribe/unsubscribe from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user_notification_preference import UserCategoryPreference


class NotificationCategory(Base):
    """
    Notification categories that users can subscribe/unsubscribe from.

    Multi-tenancy: NULL organization_id = system category, UUID = org-specific category.
    Categories define types of notifications (marketing, announcements, alerts, etc.)
    that users can opt in/out of.
    """

    __tablename__ = "notification_category"

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

    # Multi-tenancy: NULL = system category, UUID = org-specific category
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Category identification
    code: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'marketing', 'announcements', 'reminders', 'alerts'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Default opt-in/out behavior
    default_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )  # Users are opted-in by default

    # Can users change this preference? (some categories like 'security' should be mandatory)
    user_configurable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # Priority for display ordering
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="notification_categories"
    )
    user_preferences: Mapped[list[UserCategoryPreference]] = relationship(
        "UserCategoryPreference", back_populates="category"
    )

    __table_args__ = (
        # Partial unique index - allows recreating deleted categories
        Index(
            "uq_notif_category_org_code_active",
            "organization_id",
            "code",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<NotificationCategory {self.code}>"
