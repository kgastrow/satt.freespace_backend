"""
Organization notification settings model.
Per-organization configuration for notification channels.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class OrganizationNotificationSettings(Base):
    """
    Per-organization notification settings.

    Configures which notification channels are enabled, rate limits,
    and retention policies for each organization.
    """

    __tablename__ = "organization_notification_settings"

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

    # One-to-one with Organization
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Channel enablement
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    whatsapp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Off by default: Web Push needs a VAPID keypair the org may not have, and
    # an org that has not configured it should not appear to offer the channel.
    web_push_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Preferred providers (override system defaults)
    sms_provider: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # NULL = use system default
    whatsapp_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Retention
    notification_retention_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=90
    )

    # Rate limits (per hour)
    sms_rate_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    whatsapp_rate_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1000
    )

    # Sender customization
    email_sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sms_sender_id: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # Alphanumeric sender ID

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="notification_settings"
    )

    __table_args__ = (
        # Partial unique index - one settings record per org
        Index(
            "uq_org_notification_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationNotificationSettings org={self.organization_id}>"
