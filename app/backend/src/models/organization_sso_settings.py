"""
Organization SSO settings model.
Per-organization configuration for SSO providers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class OrganizationSSOSettings(Base):
    """
    Per-organization SSO settings.

    Configures which SSO providers are enabled and stores provider-specific
    credentials (encrypted) for each organization.
    """

    __tablename__ = "organization_sso_settings"

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

    # Master switch - super admin controls whether SSO is allowed for this org
    sso_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Google SSO configuration (org admin can configure if sso_allowed is True)
    google_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    google_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_client_secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Should be encrypted in production

    # Relationships (one-directional until Organization model is updated in Phase 3)
    organization: Mapped[Organization] = relationship("Organization")

    __table_args__ = (
        # Partial unique index - one settings record per org
        Index(
            "uq_org_sso_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return f"<OrganizationSSOSettings org={self.organization_id}>"
