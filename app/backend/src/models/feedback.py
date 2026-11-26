"""
Feedback models for user feedback collection system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import uuid as uuid_module

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import BIGINT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


if TYPE_CHECKING:
    from src.models.organization import Organization
    from src.models.user import User


class Feedback(Base):
    """
    Feedback submission model.

    Allows users to submit bug reports, suggestions, complaints, praise, and other feedback
    through a feedback widget. Includes attachment support via S3, admin management with
    status tracking and responses, and role-based permissions.

    Multi-tenant: Feedback belongs to an organization.
    """

    __tablename__ = "feedback"

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

    # Multi-tenancy
    organization_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organization.id"), nullable=False, index=True
    )

    # Submitter
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # Feedback type
    type: Mapped[str] = mapped_column(
        Enum("bug", "suggestion", "complaint", "praise", "other", name="feedback_type"),
        nullable=False,
        index=True,
    )

    # Rating (1-5 stars)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Content
    subject: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Auto-captured context
    page_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    screen_resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Status tracking
    status: Mapped[str] = mapped_column(
        Enum("new", "in_review", "resolved", "dismissed", name="feedback_status"),
        nullable=False,
        default="new",
        index=True,
    )

    # Admin management
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Response tracking
    responded_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Resolution tracking
    resolved_by: Mapped[uuid_module.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Track when user last viewed replies (for "new reply" indicator)
    user_last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Track when admin last viewed (for "requires attention" indicator)
    admin_last_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped[Organization] = relationship(
        "Organization", foreign_keys=[organization_id]
    )
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])
    responded_by_user: Mapped[User | None] = relationship(
        "User", foreign_keys=[responded_by]
    )
    resolved_by_user: Mapped[User | None] = relationship(
        "User", foreign_keys=[resolved_by]
    )
    attachments: Mapped[list[FeedbackAttachment]] = relationship(
        "FeedbackAttachment", back_populates="feedback"
    )
    replies: Mapped[list[FeedbackReply]] = relationship(
        "FeedbackReply",
        back_populates="feedback",
        order_by="FeedbackReply.created_time",
    )

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_feedback_org_status", "organization_id", "status"),
        Index("idx_feedback_org_type", "organization_id", "type"),
        Index("idx_feedback_org_created", "organization_id", "created_time"),
        Index("idx_feedback_user_created", "user_id", "created_time"),
    )

    def __repr__(self) -> str:
        return f"<Feedback {self.type} - {self.subject[:30]} ({self.status})>"


class FeedbackAttachment(Base):
    """
    Feedback attachment model.

    Stores information about files attached to feedback submissions
    (screenshots, documents, etc.) via S3 storage.

    Multi-tenant: Attachments inherit organization scope from parent feedback.
    """

    __tablename__ = "feedback_attachment"

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

    # Parent feedback
    feedback_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback.id"), nullable=False, index=True
    )

    # File information
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BIGINT, nullable=False)

    # Relationships
    feedback: Mapped[Feedback] = relationship("Feedback", back_populates="attachments")

    __table_args__ = (Index("idx_feedback_attachment_feedback", "feedback_id"),)

    def __repr__(self) -> str:
        return f"<FeedbackAttachment {self.file_type} ({self.file_size_bytes} bytes)>"


class FeedbackReply(Base):
    """
    Feedback reply model for conversation threads.

    Allows both users and admins to have back-and-forth communication
    on feedback items. Each reply tracks who sent it and whether it's
    from an admin or the original user.

    Multi-tenant: Replies inherit organization scope from parent feedback.
    """

    __tablename__ = "feedback_reply"

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

    # Parent feedback
    feedback_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feedback.id"), nullable=False, index=True
    )

    # Author of the reply
    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=False, index=True
    )

    # Reply content
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Whether this is an admin reply (has feedback:respond permission)
    is_admin_reply: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships
    feedback: Mapped[Feedback] = relationship("Feedback", back_populates="replies")
    user: Mapped[User] = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        Index("idx_feedback_reply_feedback", "feedback_id"),
        Index("idx_feedback_reply_created", "feedback_id", "created_time"),
    )

    def __repr__(self) -> str:
        reply_type = "Admin" if self.is_admin_reply else "User"
        return f"<FeedbackReply {reply_type} - {self.message[:30]}>"
