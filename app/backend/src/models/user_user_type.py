from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Index, text
from sqlalchemy import Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.onboarding_review_comment import OnboardingReviewComment
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.user_onboarding_progress import UserOnboardingProgress
    from src.models.user_type import UserType


class OnboardingStatus(str, enum.Enum):
    """Enum for onboarding status values."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    CHANGE_REQUESTED = "change_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class UserUserType(Base):
    """
    Tenant-scoped junction table linking users to user types.
    Tracks onboarding status per user type within an organization.
    """

    __tablename__ = "user_user_type"

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
    user_type_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_type.id"), nullable=False
    )
    onboarding_status: Mapped[OnboardingStatus] = mapped_column(
        SQLAEnum(OnboardingStatus, name="onboarding_status"),
        nullable=False,
        default=OnboardingStatus.PENDING,
    )
    onboarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requires_admin_attention: Mapped[bool] = mapped_column(
        default=False, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expiry_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Partial unique index - prevents duplicate user type assignments per org
        Index(
            "uq_user_user_type_active",
            "organization_id",
            "user_id",
            "user_type_id",
            unique=True,
            postgresql_where=text("deleted_time IS NULL"),
            sqlite_where=text("deleted_time IS NULL"),
        ),
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", back_populates="user_user_types"
    )
    user: Mapped[User] = relationship("User", back_populates="user_user_types")
    user_type: Mapped[UserType] = relationship(
        "UserType", back_populates="user_user_types"
    )
    onboarding_progress: Mapped[list[UserOnboardingProgress]] = relationship(
        "UserOnboardingProgress",
        back_populates="user_user_type",
        cascade="all, delete-orphan",
    )
    review_comments: Mapped[list[OnboardingReviewComment]] = relationship(
        "OnboardingReviewComment",
        back_populates="user_user_type",
        cascade="all, delete-orphan",
    )
