from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization


class TwoFactorPolicy(str, Enum):
    DISABLED = "disabled"
    OPTIONAL = "optional"
    MANDATORY = "mandatory"


class OrganizationTwoFactorSettings(Base):
    __tablename__ = "organization_two_factor_settings"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    two_factor_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    two_factor_policy: Mapped[str] = mapped_column(
        String(50), nullable=False, default=TwoFactorPolicy.DISABLED.value
    )
    grace_period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    enforcement_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    two_factor_app_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index(
            "uq_org_two_factor_settings_active",
            "organization_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="two_factor_settings"
    )
