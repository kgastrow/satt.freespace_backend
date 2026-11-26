from __future__ import annotations

from datetime import datetime, timezone
import enum
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy import Enum as SQLAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User
    from src.models.user_user_type import UserUserType


class CommentAuthorType(str, enum.Enum):
    """Who authored the comment."""

    ADMIN = "admin"
    USER = "user"


class OnboardingReviewComment(Base):
    """
    Tenant-scoped comments for onboarding review conversations.
    Tracks messages between admins and users during change request flow.
    """

    __tablename__ = "onboarding_review_comment"

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
    user_user_type_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user_user_type.id"), nullable=False, index=True
    )
    author_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False
    )
    author_type: Mapped[CommentAuthorType] = mapped_column(
        SQLAEnum(CommentAuthorType, name="comment_author_type"),
        nullable=False,
    )
    comment: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization")
    user_user_type: Mapped[UserUserType] = relationship(
        "UserUserType", back_populates="review_comments"
    )
    author: Mapped[User] = relationship("User")
