"""
Notification provider configuration model.
Global provider configurations (system-level) for SMS, WhatsApp, Email providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class NotificationProvider(Base):
    """
    Global provider configurations (system-level).

    Examples:
    - AWS SNS for SMS
    - Twilio for SMS/WhatsApp
    - SMTP for Email

    This is a global model (no organization_id).
    """

    __tablename__ = "notification_provider"

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

    # Provider identification
    name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'aws_sns', 'twilio', 'twilio_whatsapp'
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'sms', 'whatsapp', 'email'
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # Default for this channel

    # Configuration (encrypted in production)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Example for AWS SNS: {"region": "us-east-1"}
    # Example for Twilio: {"account_sid": "...", "from_number": "+1..."}

    __table_args__ = (
        Index("ix_notification_provider_channel", "channel"),
        # Partial unique index - allows recreating deleted providers
        Index(
            "uq_provider_name_channel_active",
            "name",
            "channel",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<NotificationProvider {self.name} ({self.channel})>"
