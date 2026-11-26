from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, String, desc
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class ImpersonationSession(Base):
    __tablename__ = "impersonation_session"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # The super admin who is impersonating
    impersonator_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # The user being impersonated
    target_user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # The organization of the user being impersonated
    target_organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # When the impersonation session ended (NULL means active)
    ended_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # IP address and user agent for security tracking
    ip_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Composite index for impersonation history queries
        # Covers: WHERE target_user_id = X AND target_organization_id = X ORDER BY created_time DESC
        Index(
            "ix_impersonation_target_user_org_created",
            "target_user_id",
            "target_organization_id",
            desc("created_time"),
        ),
    )

    # Relationships - using foreign_keys to disambiguate multiple FKs to User
    impersonator: Mapped[User] = relationship("User", foreign_keys=[impersonator_id])
    target_user: Mapped[User] = relationship("User", foreign_keys=[target_user_id])
    target_organization: Mapped[Organization] = relationship("Organization")
