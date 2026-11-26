"""
Pydantic serializers for Help Center API endpoints.
"""

from datetime import datetime
import re
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Slug validation pattern (lowercase alphanumeric with hyphens)
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_slug(slug: str) -> str:
    """
    Validate that a slug is URL-friendly (lowercase alphanumeric with hyphens).
    """
    if not SLUG_PATTERN.match(slug):
        raise ValueError(
            "Slug must be lowercase alphanumeric with hyphens (e.g., 'getting-started')"
        )
    return slug


# ============================================================================
# HelpCategory Serializers
# ============================================================================


class HelpCategoryCreate(BaseModel):
    """Request schema for creating a help category"""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    slug: str = Field(..., min_length=1, max_length=255)
    display_order: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, v: str) -> str:
        """Validate slug is URL-friendly."""
        return validate_slug(v)


class HelpCategoryUpdate(BaseModel):
    """Request schema for updating a help category"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    display_order: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate slug is URL-friendly."""
        if v is not None:
            return validate_slug(v)
        return v


class HelpCategoryResponse(BaseModel):
    """Response schema for a single help category"""

    id: UUID
    name: str
    description: Optional[str]
    slug: str
    display_order: int
    created_time: Optional[datetime]
    updated_time: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class HelpCategoryListResponse(BaseModel):
    """Response schema for list of categories with pagination"""

    items: list[HelpCategoryResponse]
    total: int
    limit: int
    offset: int


# ============================================================================
# HelpArticle Serializers
# ============================================================================


class HelpArticleCreate(BaseModel):
    """Request schema for creating a help article"""

    title: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    category_id: UUID
    status: Literal["draft", "published"] = Field(default="draft")
    published_at: Optional[datetime] = None
    featured_image_url: Optional[str] = Field(None, max_length=2048)
    display_order: int = Field(default=0, ge=0)
    is_platform_wide: bool = Field(
        default=False,
        description="If True, create platform-wide article (super admin only)",
    )

    model_config = ConfigDict(extra="forbid")

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, v: str) -> str:
        """Validate slug is URL-friendly."""
        return validate_slug(v)


class HelpArticleUpdate(BaseModel):
    """Request schema for updating a help article"""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    slug: Optional[str] = Field(None, min_length=1, max_length=500)
    content: Optional[str] = Field(None, min_length=1)
    category_id: Optional[UUID] = None
    status: Optional[Literal["draft", "published"]] = None
    published_at: Optional[datetime] = None
    featured_image_url: Optional[str] = Field(None, max_length=2048)
    display_order: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("slug")
    @classmethod
    def validate_slug_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate slug is URL-friendly."""
        if v is not None:
            return validate_slug(v)
        return v


class HelpArticleResponse(BaseModel):
    """Response schema for a single help article"""

    id: UUID
    organization_id: Optional[UUID]
    title: str
    slug: str
    content: str
    category_id: UUID
    status: str
    published_at: Optional[datetime]
    featured_image_url: Optional[str]
    display_order: int
    created_by_id: UUID
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    is_platform_wide: bool = Field(
        default=False, description="True if organization_id is None"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_article(cls, article):
        """Convert HelpArticle ORM object to response"""
        return cls(
            id=article.id,
            organization_id=article.organization_id,
            title=article.title,
            slug=article.slug,
            content=article.content,
            category_id=article.category_id,
            status=article.status,
            published_at=article.published_at,
            featured_image_url=article.featured_image_url,
            display_order=article.display_order,
            created_by_id=article.created_by_id,
            created_time=article.created_time,
            updated_time=article.updated_time,
            is_platform_wide=article.organization_id is None,
        )


class HelpArticleListResponse(BaseModel):
    """Response schema for list of articles with pagination"""

    items: list[HelpArticleResponse]
    total: int
    limit: int
    offset: int


# ============================================================================
# HelpFaq Serializers
# ============================================================================


class HelpFaqCreate(BaseModel):
    """Request schema for creating a FAQ"""

    question: str = Field(..., min_length=1, max_length=500)
    answer: str = Field(..., min_length=1)
    category_id: UUID
    status: Literal["draft", "published"] = Field(default="draft")
    display_order: int = Field(default=0, ge=0)
    is_platform_wide: bool = Field(
        default=False,
        description="If True, create platform-wide FAQ (super admin only)",
    )

    model_config = ConfigDict(extra="forbid")


class HelpFaqUpdate(BaseModel):
    """Request schema for updating a FAQ"""

    question: Optional[str] = Field(None, min_length=1, max_length=500)
    answer: Optional[str] = Field(None, min_length=1)
    category_id: Optional[UUID] = None
    status: Optional[Literal["draft", "published"]] = None
    display_order: Optional[int] = Field(None, ge=0)

    model_config = ConfigDict(extra="forbid")


class HelpFaqResponse(BaseModel):
    """Response schema for a single FAQ"""

    id: UUID
    organization_id: Optional[UUID]
    question: str
    answer: str
    category_id: UUID
    status: str
    display_order: int
    created_time: Optional[datetime]
    updated_time: Optional[datetime]
    is_platform_wide: bool = Field(
        default=False, description="True if organization_id is None"
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_faq(cls, faq):
        """Convert HelpFaq ORM object to response"""
        return cls(
            id=faq.id,
            organization_id=faq.organization_id,
            question=faq.question,
            answer=faq.answer,
            category_id=faq.category_id,
            status=faq.status,
            display_order=faq.display_order,
            created_time=faq.created_time,
            updated_time=faq.updated_time,
            is_platform_wide=faq.organization_id is None,
        )


class HelpFaqListResponse(BaseModel):
    """Response schema for list of FAQs with pagination"""

    items: list[HelpFaqResponse]
    total: int
    limit: int
    offset: int


# ============================================================================
# Search Serializers
# ============================================================================


class HelpSearchResponse(BaseModel):
    """Response schema for help center search"""

    articles: list[HelpArticleResponse]
    faqs: list[HelpFaqResponse]
    total_results: int = Field(description="Total count of articles + FAQs")


class HelpDeleteResponse(BaseModel):
    """Response schema for delete operations"""

    message: str
    message_code: str


# ============================================================================
# Reorder Serializers
# ============================================================================


class ReorderItem(BaseModel):
    """Single item in a reorder request"""

    id: UUID
    display_order: int = Field(..., ge=0)


class ReorderRequest(BaseModel):
    """Request schema for reordering items"""

    items: list[ReorderItem] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")


class ReorderResponse(BaseModel):
    """Response schema for reorder operations"""

    message: str
    message_code: str
    updated_count: int
