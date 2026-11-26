"""
Notification history model.
Records all sent notifications for audit and tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.bulk_notification import BulkNotification
    from src.models.notification_template import NotificationTemplate
    from src.models.organization import Organization
    from src.models.user import User


class Notification(Base):
    """
    Notification records for history tracking.

    Multi-tenancy: NULL organization_id = system notification, UUID = org notification.
    Stores sent notifications for audit, debugging, and delivery tracking.
    """

    __tablename__ = "notification"

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

    # Multi-tenancy: NULL = system notification, UUID = org notification
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Reference to user (recipient)
    user_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True, index=True
    )

    # Channel and provider
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'email', 'sms', 'whatsapp', 'in_app'
    provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # 'aws_sns', 'twilio', etc.

    # Recipient info (denormalized for history)
    recipient: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # email or phone number

    # Content (stored for audit)
    template_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_template.id"), nullable=True
    )
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_preview: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # First 500 chars

    # Delivery status
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Values: 'pending', 'queued', 'sent', 'delivered', 'failed', 'bounced', 'skipped'

    # Provider response
    provider_message_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_retry_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Bulk notification reference
    bulk_notification_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bulk_notification.id"),
        nullable=True,
        index=True,
    )

    # Additional context (renamed from metadata to avoid SQLAlchemy reserved name)
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="notifications"
    )
    user: Mapped[User | None] = relationship("User", back_populates="notifications")
    template: Mapped[NotificationTemplate | None] = relationship("NotificationTemplate")
    bulk_notification: Mapped[BulkNotification | None] = relationship(
        "BulkNotification", back_populates="notifications"
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_notification_org_created", "organization_id", "created_time"),
        Index("ix_notification_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.channel} to {self.recipient} ({self.status})>"
