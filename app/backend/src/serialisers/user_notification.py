"""
User notification API serializer models.
Contains Pydantic models for in-app notification API endpoints.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.serialisers.common import PaginatedResponse


# =============================================================================
# Response Models
# =============================================================================


class InAppNotificationResponse(BaseModel):
    """Response for a single in-app notification."""

    id: UUID
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    category_id: Optional[UUID] = None
    read_time: Optional[datetime] = None
    created_time: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class InAppNotificationListResponse(PaginatedResponse):
    """Paginated list of in-app notifications."""

    items: list[InAppNotificationResponse]


class UnreadCountResponse(BaseModel):
    """Response for unread notification count."""

    unread_count: int

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Request Models
# =============================================================================


class CreateInAppNotificationRequest(BaseModel):
    """Request to create an in-app notification (internal use)."""

    user_id: UUID = Field(..., description="Target user ID")
    title: str = Field(..., min_length=1, max_length=255)
    body: Optional[str] = Field(None, max_length=5000)
    link: Optional[str] = Field(None, max_length=2048)
    category_id: Optional[UUID] = None

    model_config = ConfigDict(extra="forbid")


class MarkNotificationsReadRequest(BaseModel):
    """Request to mark specific notifications as read."""

    notification_ids: list[UUID] = Field(
        ..., min_length=1, description="List of notification IDs to mark as read"
    )

    model_config = ConfigDict(extra="forbid")


class DismissNotificationsRequest(BaseModel):
    """Request to dismiss (soft delete) notifications."""

    notification_ids: list[UUID] = Field(
        ..., min_length=1, description="List of notification IDs to dismiss"
    )

    model_config = ConfigDict(extra="forbid")


# =============================================================================
# Action Response Models
# =============================================================================


class MarkReadResponse(BaseModel):
    """Response after marking notification(s) as read."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    count: int = Field(..., description="Number of notifications marked as read")

    model_config = ConfigDict(extra="forbid")


class DismissResponse(BaseModel):
    """Response after dismissing notifications."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    count: int = Field(..., description="Number of notifications dismissed")

    model_config = ConfigDict(extra="forbid")
