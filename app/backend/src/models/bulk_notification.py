"""
Bulk notification batch tracking model.
Tracks progress of bulk notification operations.
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
    from src.models.notification import Notification
    from src.models.notification_template import NotificationTemplate
    from src.models.organization import Organization
    from src.models.user import User


class BulkNotification(Base):
    """
    Bulk notification batch tracking.

    Multi-tenancy: NULL organization_id = system notification, UUID = org notification.
    Tracks sending progress for batch operations.
    """

    __tablename__ = "bulk_notification"

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

    # Sender
    created_by_user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )

    # Batch info
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )  # "Term Start Announcement"
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'email', 'sms', 'whatsapp', 'in_app'
    template_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notification_template.id"), nullable=True
    )

    # Content (if not using template)
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Recipients
    total_recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Progress tracking
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Values: 'pending', 'processing', 'completed', 'failed', 'cancelled'

    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Scheduling
    scheduled_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # NULL = send immediately

    # Extra data (recipient_filters, category_code, is_urgent, etc.)
    # Note: named extra_data instead of metadata due to reserved keyword conflict
    extra_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True, default=dict
    )

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="bulk_notifications"
    )
    created_by: Mapped[User] = relationship("User")
    template: Mapped[NotificationTemplate | None] = relationship("NotificationTemplate")
    notifications: Mapped[list[Notification]] = relationship(
        "Notification", back_populates="bulk_notification"
    )

    # Indexes for common query patterns
    __table_args__ = (Index("ix_bulk_notification_status", "status"),)

    def __repr__(self) -> str:
        return f"<BulkNotification {self.name} ({self.status})>"

    @property
    def progress_percentage(self) -> float:
        """Calculate completion percentage (capped at 100%)."""
        if self.total_recipients == 0:
            return 0.0
        sent = self.sent_count or 0
        failed = self.failed_count or 0
        return min(((sent + failed) / self.total_recipients) * 100, 100.0)
