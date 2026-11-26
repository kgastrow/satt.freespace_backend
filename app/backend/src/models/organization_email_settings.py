"""
Organization email settings model.
Per-organization configuration for email providers (SMTP, SendGrid).
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


class OrganizationEmailSettings(Base):
    """
    Per-organization email configuration.

    Allows organizations to override platform-wide email settings with their
    own provider credentials and branding. Supports SMTP and SendGrid providers.

    Credential fields (smtp_username, smtp_password, sendgrid_api_key) are
    stored encrypted using the encryption utilities.

    Hierarchy:
    1. Organization settings (if configured)
    2. Platform defaults from SystemConfig
    3. Fallback to config.json values
    """

    __tablename__ = "organization_email_settings"

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

    # Provider selection (NULL = use platform default)
    # Valid values: 'smtp', 'sendgrid', or NULL
    provider: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # SMTP configuration
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_username: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # Encrypted
    smtp_password: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # Encrypted
    smtp_use_tls: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    smtp_use_ssl: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # SendGrid configuration
    sendgrid_api_key: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )  # Encrypted

    # Branding / Sender configuration
    sender_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="email_settings"
    )

    __table_args__ = (
        # Partial unique index - one settings record per org (soft delete aware)
        Index(
            "uq_org_email_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationEmailSettings org={self.organization_id} provider={self.provider}>"
