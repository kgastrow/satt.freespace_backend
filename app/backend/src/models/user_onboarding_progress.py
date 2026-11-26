from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.onboarding_step import OnboardingStep
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.user_user_type import UserUserType


class UserOnboardingProgress(Base):
    """
    Tenant-scoped progress tracking for user onboarding steps.
    Records submitted data and completion status for each step.
    """

    __tablename__ = "user_onboarding_progress"

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

    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    user_user_type_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_user_type.id"), nullable=False
    )
    onboarding_step_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("onboarding_step.id"), nullable=False
    )
    submitted_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    completed_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="user_onboarding_progress"
    )
    user: Mapped[User] = relationship("User", back_populates="user_onboarding_progress")
    user_user_type: Mapped[UserUserType] = relationship(
        "UserUserType", back_populates="onboarding_progress"
    )
    onboarding_step: Mapped[OnboardingStep] = relationship(
        "OnboardingStep", back_populates="progress_records"
    )
