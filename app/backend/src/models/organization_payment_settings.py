"""
Organization payment settings model.
Per-organization configuration for payment providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class OrganizationPaymentSettings(Base):
    """
    Per-organization payment configuration.

    Follows the same pattern as OrganizationSSOSettings and
    OrganizationFileSettings for consistent multi-tenant configuration.

    Two-Tier Permission System (mirrors SSO):
    1. Super Admin: payments_allowed (master switch)
    2. Org Admin: {provider}_enabled (per-provider toggle)

    Both must be True for a provider to be usable.
    """

    __tablename__ = "organization_payment_settings"

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

    # ─────────────────────────────────────────────────────────────
    # Master Switches
    # ─────────────────────────────────────────────────────────────

    # Super admin control - must be True for any payments
    payments_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ─────────────────────────────────────────────────────────────
    # Provider Configuration
    # ─────────────────────────────────────────────────────────────

    # Default provider for this organization
    default_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Default currency (ISO 4217)
    default_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD"
    )

    # Supported currencies for this org (JSON array)
    supported_currencies: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # ─────────────────────────────────────────────────────────────
    # Stripe Configuration
    # ─────────────────────────────────────────────────────────────

    stripe_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # For Stripe Connect (marketplace scenarios)
    # Organization's own Stripe account ID
    stripe_connect_account_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # Optional per-org credentials (for white-label/reseller)
    # If NULL, system-wide credentials from config are used
    stripe_publishable_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    stripe_secret_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Should be encrypted in practice
    stripe_webhook_secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # ─────────────────────────────────────────────────────────────
    # PayFast Configuration (South Africa)
    # ─────────────────────────────────────────────────────────────

    payfast_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Optional per-org PayFast credentials
    payfast_merchant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payfast_merchant_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payfast_passphrase: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payfast_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ─────────────────────────────────────────────────────────────
    # PayPal Configuration
    # ─────────────────────────────────────────────────────────────

    paypal_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    paypal_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paypal_client_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    paypal_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ─────────────────────────────────────────────────────────────
    # Relationships
    # ─────────────────────────────────────────────────────────────

    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="payment_settings"
    )

    __table_args__ = (
        # Partial unique index - one settings record per org
        Index(
            "uq_org_payment_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationPaymentSettings org={self.organization_id}>"
