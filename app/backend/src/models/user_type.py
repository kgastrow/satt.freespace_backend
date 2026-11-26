from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.onboarding_step import OnboardingStep
    from src.models.user_type_permission import UserTypePermission
    from src.models.user_user_type import UserUserType


class UserType(Base):
    """
    Global UserType model - user types are system-wide and not scoped to organizations.
    Defines types like 'individual', 'business', 'provider' with onboarding requirements.
    """

    __tablename__ = "user_type"

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4
    )
    created_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    requires_onboarding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    requires_manual_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # Partial unique index - allows soft-deleted codes to be reused
        Index(
            "uq_user_type_code_active",
            "code",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    user_user_types: Mapped[list[UserUserType]] = relationship(
        "UserUserType", back_populates="user_type", cascade="all, delete-orphan"
    )
    onboarding_steps: Mapped[list[OnboardingStep]] = relationship(
        "OnboardingStep", back_populates="user_type", cascade="all, delete-orphan"
    )
    user_type_permissions: Mapped[list[UserTypePermission]] = relationship(
        "UserTypePermission", back_populates="user_type", cascade="all, delete-orphan"
    )
