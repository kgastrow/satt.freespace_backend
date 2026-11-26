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
    from src.models.user import User
    from src.models.user_two_factor_backup_code import UserTwoFactorBackupCode


class UserTwoFactor(Base):
    __tablename__ = "user_two_factor"

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

    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    secret: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "uq_user_two_factor_user_active",
            "user_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
        Index(
            "ix_user_two_factor_org_enabled",
            "organization_id",
            "is_enabled",
        ),
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="two_factor")
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="user_two_factors"
    )
    backup_codes: Mapped[list[UserTwoFactorBackupCode]] = relationship(
        "UserTwoFactorBackupCode", back_populates="user_two_factor"
    )
