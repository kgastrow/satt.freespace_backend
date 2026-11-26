"""
Pydantic serializers for Announcement API endpoints.
"""

from datetime import datetime
import re
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Pattern to validate safe URLs (relative paths or http/https)
SAFE_URL_PATTERN = re.compile(
    r"^(/[\w\-./]*|https?://[\w\-.]+(:\d+)?(/[\w\-./?%&=#]*)?)$",
    re.IGNORECASE,
)


def validate_safe_url(url: Optional[str]) -> Optional[str]:
    """
    Validate that a URL is safe (relative path or http/https).
    Blocks javascript:, data:, and other potentially dangerous schemes.
    """
    if url is None or url == "":
        return url
    if not SAFE_URL_PATTERN.match(url):
        raise ValueError(
            "URL must be a relative path (starting with /) or an http/https URL"
        )
    return url


class AnnouncementCreate(BaseModel):
    """Request schema for creating an announcement"""

    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    priority: Literal["critical", "high", "normal", "low"] = Field(default="normal")
    background_color: Optional[str] = Field(None, max_length=50)
    text_color: Optional[str] = Field(None, max_length=50)
    featured_image_url: Optional[str] = Field(None, max_length=2048)
    cta_text: Optional[str] = Field(None, max_length=100)
    cta_url: Optional[str] = Field(None, max_length=2048)
    cta_dismisses: bool = Field(default=True)
    cta_button_color: Optional[str] = Field(None, max_length=50)
    cta_button_variant: Optional[str] = Field(None, max_length=50)
    is_dismissible: bool = Field(default=True)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    is_platform_wide: bool = Field(
        default=False,
        description="If True, create platform-wide announcement (super admin only)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("cta_url", "featured_image_url")
    @classmethod
    def validate_urls(cls, v: Optional[str]) -> Optional[str]:
        """Validate that URLs are safe (relative or http/https only)."""
        return validate_safe_url(v)


class AnnouncementUpdate(BaseModel):
    """Request schema for updating an announcement"""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    body: Optional[str] = Field(None, min_length=1)
    priority: Optional[Literal["critical", "high", "normal", "low"]] = None
    background_color: Optional[str] = Field(None, max_length=50)
    text_color: Optional[str] = Field(None, max_length=50)
    featured_image_url: Optional[str] = Field(None, max_length=2048)
    cta_text: Optional[str] = Field(None, max_length=100)
    cta_url: Optional[str] = Field(None, max_length=2048)
    cta_dismisses: Optional[bool] = None
    cta_button_color: Optional[str] = Field(None, max_length=50)
    cta_button_variant: Optional[str] = Field(None, max_length=50)
    is_dismissible: Optional[bool] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("cta_url", "featured_image_url")
    @classmethod
    def validate_urls(cls, v: Optional[str]) -> Optional[str]:
        """Validate that URLs are safe (relative or http/https only)."""
        return validate_safe_url(v)


class AnnouncementResponse(BaseModel):
    """Response schema for a single announcement"""

    id: UUID
    organization_id: Optional[UUID]
    title: str
    body: str
    priority: str
    background_color: Optional[str]
    text_color: Optional[str]
    featured_image_url: Optional[str]
    cta_text: Optional[str]
    cta_url: Optional[str]
    cta_dismisses: bool
    cta_button_color: Optional[str]
    cta_button_variant: Optional[str]
    is_dismissible: bool
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    created_by_id: UUID
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    is_platform_wide: bool = Field(
        default=False, description="True if organization_id is None"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_announcement(cls, announcement):
        """Convert Announcement ORM object to response"""
        return cls(
            id=announcement.id,
            organization_id=announcement.organization_id,
            title=announcement.title,
            body=announcement.body,
            priority=announcement.priority,
            background_color=announcement.background_color,
            text_color=announcement.text_color,
            featured_image_url=announcement.featured_image_url,
            cta_text=announcement.cta_text,
            cta_url=announcement.cta_url,
            cta_dismisses=announcement.cta_dismisses,
            cta_button_color=announcement.cta_button_color,
            cta_button_variant=announcement.cta_button_variant,
            is_dismissible=announcement.is_dismissible,
            start_time=announcement.start_time,
            end_time=announcement.end_time,
            created_by_id=announcement.created_by_id,
            created_time=announcement.created_time,
            updated_time=announcement.updated_time,
            is_platform_wide=announcement.organization_id is None,
        )


class AnnouncementListResponse(BaseModel):
    """Response schema for list of announcements with pagination"""

    items: list[AnnouncementResponse]
    total: int
    limit: int
    offset: int


class ActiveAnnouncementsResponse(BaseModel):
    """Response schema for active announcements"""

    announcements: list[AnnouncementResponse]


class DismissAnnouncementRequest(BaseModel):
    """Request schema for dismissing an announcement"""

    model_config = ConfigDict(extra="forbid")


class DismissAnnouncementResponse(BaseModel):
    """Response schema for dismissing an announcement"""

    message: str
    message_code: str
    announcement_id: UUID
