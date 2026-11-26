"""
Pydantic serializers for Changelog API endpoints.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateChangelogRequest(BaseModel):
    """Request schema for creating a changelog entry"""

    version: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    category: Literal["feature", "improvement", "bugfix", "breaking", "other"] = Field(
        default="other"
    )
    release_date: datetime
    is_published: bool = Field(default=False)
    is_platform_wide: bool = Field(
        default=False,
        description="If True, create platform-wide entry (super admin only)",
    )

    model_config = ConfigDict(extra="forbid")


class UpdateChangelogRequest(BaseModel):
    """Request schema for updating a changelog entry"""

    version: Optional[str] = Field(None, min_length=1, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    body: Optional[str] = Field(None, min_length=1)
    category: Optional[
        Literal["feature", "improvement", "bugfix", "breaking", "other"]
    ] = None
    release_date: Optional[datetime] = None
    is_published: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class ChangelogResponse(BaseModel):
    """Response schema for a single changelog entry"""

    id: UUID
    organization_id: Optional[UUID]
    version: str
    title: str
    body: str
    category: str
    release_date: datetime
    is_published: bool
    created_by_id: UUID
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    is_platform_wide: bool = Field(
        default=False, description="True if organization_id is None"
    )
    is_viewed: bool = Field(
        default=False, description="Whether the current user has viewed this entry"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_changelog(cls, changelog, is_viewed: bool = False):
        """Convert Changelog ORM object to response"""
        return cls(
            id=changelog.id,
            organization_id=changelog.organization_id,
            version=changelog.version,
            title=changelog.title,
            body=changelog.body,
            category=changelog.category,
            release_date=changelog.release_date,
            is_published=changelog.is_published,
            created_by_id=changelog.created_by_id,
            created_time=changelog.created_time,
            updated_time=changelog.updated_time,
            is_platform_wide=changelog.organization_id is None,
            is_viewed=is_viewed,
        )


class ChangelogListResponse(BaseModel):
    """Response schema for list of changelog entries with pagination"""

    items: list[ChangelogResponse]
    total: int
    limit: int
    offset: int
    unread_count: int = 0


class UnreadCountResponse(BaseModel):
    """Response schema for unread changelog count"""

    count: int
