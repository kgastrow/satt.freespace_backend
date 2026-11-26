"""
Pydantic serializers for Feedback API endpoints.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateFeedbackRequest(BaseModel):
    """Request schema for creating feedback"""

    type: Literal["bug", "suggestion", "complaint", "praise", "other"] = Field(
        ..., description="Type of feedback being submitted"
    )
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating from 1-5 stars")
    subject: str = Field(
        ..., min_length=1, max_length=100, description="Feedback subject"
    )
    message: str = Field(
        ..., min_length=1, max_length=2000, description="Feedback message"
    )
    page_url: Optional[str] = Field(
        None, max_length=2048, description="Auto-captured page URL"
    )
    user_agent: Optional[str] = Field(
        None, max_length=512, description="Auto-captured user agent"
    )
    screen_resolution: Optional[str] = Field(
        None, max_length=50, description="Auto-captured screen resolution"
    )

    model_config = ConfigDict(extra="forbid")


class UpdateFeedbackRequest(BaseModel):
    """Request schema for updating feedback (admin only)"""

    status: Optional[Literal["new", "in_review", "resolved", "dismissed"]] = Field(
        None, description="Feedback status"
    )
    admin_notes: Optional[str] = Field(
        None, max_length=5000, description="Internal admin notes (not visible to user)"
    )
    admin_response: Optional[str] = Field(
        None, max_length=5000, description="Admin response (visible to user)"
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("status")
    @classmethod
    def validate_status_transition(cls, v: Optional[str]) -> Optional[str]:
        """Validate status is one of the allowed values"""
        if v is not None and v not in ["new", "in_review", "resolved", "dismissed"]:
            raise ValueError("Invalid status value")
        return v


class FeedbackAttachmentResponse(BaseModel):
    """Response schema for feedback attachment"""

    id: UUID
    feedback_id: UUID
    file_path: str
    file_type: str
    file_size_bytes: int
    created_time: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class FeedbackReplyResponse(BaseModel):
    """Response schema for feedback reply"""

    id: UUID
    feedback_id: UUID
    user_id: UUID
    user_email: Optional[str] = None
    message: str
    is_admin_reply: bool
    created_time: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_reply(cls, reply):
        """Convert FeedbackReply ORM object to response"""
        from sqlalchemy import inspect

        user_email = None

        insp = inspect(reply)

        # Check if user relationship is loaded
        if "user" in insp.mapper.relationships:
            user_state = insp.attrs.user
            user_loaded = user_state.loaded_value
            if user_loaded is not None and hasattr(user_loaded, "email"):
                user_email = user_loaded.email

        return cls(
            id=reply.id,
            feedback_id=reply.feedback_id,
            user_id=reply.user_id,
            user_email=user_email,
            message=reply.message,
            is_admin_reply=reply.is_admin_reply,
            created_time=reply.created_time,
        )


class FeedbackResponse(BaseModel):
    """Response schema for a single feedback submission"""

    id: UUID
    organization_id: UUID
    user_id: UUID
    user_email: Optional[str] = None
    type: str
    rating: Optional[int]
    subject: str
    message: str
    page_url: Optional[str]
    user_agent: Optional[str]
    screen_resolution: Optional[str]
    status: str
    admin_notes: Optional[str]
    admin_response: Optional[str]
    responded_by: Optional[UUID]
    responded_at: Optional[datetime]
    resolved_by: Optional[UUID]
    resolved_at: Optional[datetime]
    user_last_viewed_at: Optional[datetime] = None
    admin_last_viewed_at: Optional[datetime] = None
    has_unread_replies: bool = False
    requires_attention: bool = False
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    attachments: list[FeedbackAttachmentResponse] = Field(default_factory=list)
    replies: list[FeedbackReplyResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_feedback(cls, feedback, include_replies: bool = True):
        """Convert Feedback ORM object to response

        Args:
            feedback: Feedback ORM object (attachments, user, and replies relationships should be loaded if needed)
            include_replies: Whether to include replies in the response
        """
        from sqlalchemy import inspect

        attachments = []
        replies = []
        user_email = None
        has_unread_replies = False
        requires_attention = False
        loaded_replies = []

        insp = inspect(feedback)

        # Check if attachments relationship is loaded
        if "attachments" in insp.mapper.relationships:
            att_state = insp.attrs.attachments
            loaded = att_state.loaded_value
            if isinstance(loaded, list):
                attachments = [
                    FeedbackAttachmentResponse.model_validate(att) for att in loaded
                ]

        # Check if user relationship is loaded
        if "user" in insp.mapper.relationships:
            user_state = insp.attrs.user
            user_loaded = user_state.loaded_value
            if user_loaded is not None and hasattr(user_loaded, "email"):
                user_email = user_loaded.email

        # Check if replies relationship is loaded
        if "replies" in insp.mapper.relationships:
            replies_state = insp.attrs.replies
            loaded_replies = replies_state.loaded_value
            if isinstance(loaded_replies, list):
                if include_replies:
                    replies = [
                        FeedbackReplyResponse.from_orm_reply(reply)
                        for reply in loaded_replies
                        if reply.deleted_time is None
                    ]
                # Check for unread replies (any reply after user_last_viewed_at)
                if feedback.user_last_viewed_at:
                    has_unread_replies = any(
                        reply.created_time
                        and reply.created_time > feedback.user_last_viewed_at
                        for reply in loaded_replies
                        if reply.deleted_time is None
                    )
                else:
                    # If user has never viewed, any reply is unread
                    has_unread_replies = (
                        len([r for r in loaded_replies if r.deleted_time is None]) > 0
                    )

        # Compute requires_attention for admin view
        # True if: status is "new" OR (status is "in_review" AND has unread user replies)
        if feedback.status == "new":
            requires_attention = True
        elif feedback.status == "in_review":
            # Find the most recent admin activity timestamp
            admin_timestamps = [
                t
                for t in [feedback.admin_last_viewed_at, feedback.responded_at]
                if t is not None
            ]
            # Also consider the most recent admin reply time
            if isinstance(loaded_replies, list):
                for reply in loaded_replies:
                    if (
                        reply.deleted_time is None
                        and reply.is_admin_reply
                        and reply.created_time
                    ):
                        admin_timestamps.append(reply.created_time)

            last_admin_activity = max(admin_timestamps) if admin_timestamps else None

            # Check if there are user replies after the last admin activity
            if isinstance(loaded_replies, list):
                user_replies = [
                    r
                    for r in loaded_replies
                    if r.deleted_time is None
                    and not r.is_admin_reply
                    and r.created_time is not None
                ]
                if last_admin_activity:
                    requires_attention = any(
                        r.created_time > last_admin_activity for r in user_replies
                    )
                else:
                    # If admin has never interacted, any user reply requires attention
                    requires_attention = len(user_replies) > 0

        return cls(
            id=feedback.id,
            organization_id=feedback.organization_id,
            user_id=feedback.user_id,
            user_email=user_email,
            type=feedback.type,
            rating=feedback.rating,
            subject=feedback.subject,
            message=feedback.message,
            page_url=feedback.page_url,
            user_agent=feedback.user_agent,
            screen_resolution=feedback.screen_resolution,
            status=feedback.status,
            admin_notes=feedback.admin_notes,
            admin_response=feedback.admin_response,
            responded_by=feedback.responded_by,
            responded_at=feedback.responded_at,
            resolved_by=feedback.resolved_by,
            resolved_at=feedback.resolved_at,
            user_last_viewed_at=feedback.user_last_viewed_at,
            admin_last_viewed_at=feedback.admin_last_viewed_at,
            has_unread_replies=has_unread_replies,
            requires_attention=requires_attention,
            created_time=feedback.created_time,
            updated_time=feedback.updated_time,
            attachments=attachments,
            replies=replies,
        )


class FeedbackListResponse(BaseModel):
    """Response schema for list of feedback with pagination"""

    items: list[FeedbackResponse]
    total: int
    limit: int
    offset: int


class FeedbackAttachmentRequest(BaseModel):
    """Request schema for creating feedback attachment"""

    file_path: str = Field(..., max_length=512, description="Path to file in S3")
    file_type: str = Field(..., max_length=100, description="MIME type of file")
    file_size_bytes: int = Field(..., gt=0, description="File size in bytes")

    model_config = ConfigDict(extra="forbid")


class CreateFeedbackResponse(BaseModel):
    """Response schema for feedback creation"""

    message: str
    message_code: str
    feedback: FeedbackResponse


class UpdateFeedbackResponse(BaseModel):
    """Response schema for feedback update"""

    message: str
    message_code: str
    feedback: FeedbackResponse


class DeleteFeedbackResponse(BaseModel):
    """Response schema for feedback deletion"""

    message: str
    message_code: str
    feedback_id: UUID


class CreateFeedbackReplyRequest(BaseModel):
    """Request schema for creating a feedback reply"""

    message: str = Field(
        ..., min_length=1, max_length=5000, description="Reply message"
    )

    model_config = ConfigDict(extra="forbid")


class CreateFeedbackReplyResponse(BaseModel):
    """Response schema for feedback reply creation"""

    message: str
    message_code: str
    reply: FeedbackReplyResponse


class MarkFeedbackViewedResponse(BaseModel):
    """Response schema for marking feedback as viewed"""

    message: str
    message_code: str
    feedback_id: UUID
    viewed_at: Optional[datetime]
