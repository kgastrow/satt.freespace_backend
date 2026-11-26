"""
Notification template model.
Templates can be system-level (organization_id=NULL) or org-specific.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class NotificationTemplate(Base):
    """
    Notification templates - system or org-specific.

    Multi-tenancy: NULL organization_id = system template, UUID = org-specific.

    Templates support variable substitution using SINGLE-brace {variable_name}
    syntax, e.g. "Hello {first_name}". Double braces are NOT a placeholder:
    TemplateRenderer matches the inner {variable_name} of "{{variable_name}}"
    and the surrounding braces are shipped verbatim in the rendered body.
    The `variables` column documents the placeholders a template expects.
    """

    __tablename__ = "notification_template"

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

    # Multi-tenancy: NULL = system template, UUID = org-specific
    organization_id: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=True, index=True
    )

    # Template identification
    code: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # 'welcome_email', 'password_reset', etc.
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Channel support
    channel: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'email', 'sms', 'whatsapp', 'in_app'

    # Content
    subject: Mapped[str | None] = mapped_column(String(255), nullable=True)  # For email
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)  # For email

    # External provider template ID (e.g., Twilio content_sid for WhatsApp templates)
    # Required for WhatsApp business-initiated messages outside the 24-hour window
    provider_template_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Template variables (JSON schema for validation)
    variables: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )  # {"user_name": "string", "otp_code": "string"}

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    organization: Mapped[Organization | None] = relationship(
        "Organization", back_populates="notification_templates"
    )

    __table_args__ = (
        Index("ix_notification_template_code", "code"),
        # Partial unique index - allows recreating deleted templates
        Index(
            "uq_template_org_code_channel_active",
            "organization_id",
            "code",
            "channel",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate {self.code} ({self.channel})>"
