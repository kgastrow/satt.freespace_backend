from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.user_onboarding_progress import UserOnboardingProgress
    from src.models.user_type import UserType


class OnboardingStep(Base):
    """
    Global OnboardingStep model - defines steps required for each user type.
    Steps include validation rules and required fields stored as JSONB.
    """

    __tablename__ = "onboarding_step"

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

    user_type_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_type.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    required_fields: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validation_rules: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    requires_verification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    user_type: Mapped[UserType] = relationship(
        "UserType", back_populates="onboarding_steps"
    )
    progress_records: Mapped[list[UserOnboardingProgress]] = relationship(
        "UserOnboardingProgress",
        back_populates="onboarding_step",
        cascade="all, delete-orphan",
    )
