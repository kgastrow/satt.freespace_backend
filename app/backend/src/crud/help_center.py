"""
CRUD operations for Help Center models.

Supports mixed-scope content:
- organization_id=None on a row: Platform-wide content (visible to all)
- organization_id=UUID on a row: Organization-specific content

Read helpers take an explicit visibility intent so that the three distinct
cases can never be confused with one another (see ``_visibility_conditions``):

1. ``organization_id=<uuid>``            -> that org's content + platform-wide
2. ``platform_only=True``                -> platform-wide content ONLY
   (used by the unauthenticated public endpoints)
3. ``organization_id=None, platform_only=False`` -> NO filter at all,
   i.e. the cross-organization super-admin view

Public queries return only published content.
Admin queries include drafts and support filtering by status.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.help_center import HelpArticle, HelpCategory, HelpFaq


def _visibility_conditions(
    org_column: Any,
    organization_id: Optional[str],
    platform_only: bool,
) -> list[ColumnElement[bool]]:
    """
    Build the organization-visibility conditions for a help center query.

    The three supported scopes are mutually exclusive and explicit:

    - ``platform_only=True``: only platform-wide rows (organization_id IS NULL).
      This is what the unauthenticated public endpoints must use.
    - ``organization_id`` provided: that organization's rows plus platform-wide
      rows. ``platform_only`` must be False in this case.
    - ``organization_id=None`` and ``platform_only=False``: no organization
      filter at all - the cross-organization super admin view.

    Args:
        org_column: The model's organization_id column
        organization_id: Organization UUID string, or None
        platform_only: If True, restrict to platform-wide rows only

    Returns:
        List of SQLAlchemy conditions (possibly empty for the unfiltered view)

    Raises:
        ValueError: If platform_only is combined with an organization_id
    """
    if platform_only:
        if organization_id is not None:
            raise ValueError(
                "platform_only=True cannot be combined with an organization_id"
            )
        return [org_column.is_(None)]

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        return [
            or_(
                org_column == org_uuid,
                org_column.is_(None),
            )
        ]

    # Unfiltered cross-organization view (super admin only).
    return []


# ============================================================================
# HelpCategory CRUD
# ============================================================================


async def create_category(
    session: AsyncSession,
    category_data: dict[str, Any],
) -> HelpCategory:
    """
    Create a help category.

    Args:
        session: Database session
        category_data: Category data including:
            - name: Category name (required)
            - description: Category description (optional)
            - slug: URL-friendly slug (required)
            - display_order: Display order (default: 0)

    Returns:
        The created HelpCategory

    Raises:
        Exception: If slug already exists
    """
    # Check slug uniqueness
    existing = await session.execute(
        select(HelpCategory).where(
            HelpCategory.slug == category_data["slug"],
            HelpCategory.deleted_time.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Category with slug '{category_data['slug']}' already exists")

    category = HelpCategory(
        name=category_data["name"],
        description=category_data.get("description"),
        slug=category_data["slug"],
        display_order=category_data.get("display_order", 0),
    )

    session.add(category)
    try:
        await session.commit()
        await session.refresh(category)
    except Exception as e:
        await session.rollback()
        raise e

    return category


async def get_category_by_id(
    session: AsyncSession,
    category_id: str,
) -> Optional[HelpCategory]:
    """
    Get category by ID.

    Args:
        session: Database session
        category_id: Category UUID string

    Returns:
        The HelpCategory or None if not found
    """
    cat_uuid = UUID(category_id)
    result = await session.execute(
        select(HelpCategory).where(
            HelpCategory.id == cat_uuid,
            HelpCategory.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_category_by_slug(
    session: AsyncSession,
    slug: str,
) -> Optional[HelpCategory]:
    """
    Get category by slug.

    Args:
        session: Database session
        slug: Category slug

    Returns:
        The HelpCategory or None if not found
    """
    result = await session.execute(
        select(HelpCategory).where(
            HelpCategory.slug == slug,
            HelpCategory.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_categories(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[HelpCategory], int]:
    """
    Get all categories ordered by display_order.

    Args:
        session: Database session
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of categories, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        HelpCategory.deleted_time.is_(None),
    ]

    # Count query
    count_result = await session.execute(
        select(func.count(HelpCategory.id)).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query
    result = await session.execute(
        select(HelpCategory)
        .where(*conditions)
        .order_by(HelpCategory.display_order.asc(), HelpCategory.name.asc())
        .limit(limit)
        .offset(offset)
    )
    categories = result.scalars().all()

    return list(categories), total


async def update_category(
    session: AsyncSession,
    category_id: str,
    category_data: dict[str, Any],
) -> Optional[HelpCategory]:
    """
    Update a category.

    Args:
        session: Database session
        category_id: Category UUID string
        category_data: Fields to update (all optional):
            - name, description, slug, display_order

    Returns:
        The updated HelpCategory or None if not found

    Raises:
        ValueError: If slug already exists for another category
    """
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(HelpCategory).where(
            HelpCategory.id == cat_uuid,
            HelpCategory.deleted_time.is_(None),
        )
    )
    category = result.scalars().first()

    if not category:
        return None

    # Check slug uniqueness if updating
    if "slug" in category_data and category_data["slug"] != category.slug:
        existing = await session.execute(
            select(HelpCategory).where(
                HelpCategory.slug == category_data["slug"],
                HelpCategory.id != cat_uuid,
                HelpCategory.deleted_time.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Category with slug '{category_data['slug']}' already exists"
            )

    # Update allowed fields
    updatable_fields = ["name", "description", "slug", "display_order"]
    for field in updatable_fields:
        if field in category_data:
            setattr(category, field, category_data[field])

    try:
        await session.commit()
        await session.refresh(category)
    except Exception as e:
        await session.rollback()
        raise e

    return category


async def soft_delete_category(
    session: AsyncSession,
    category_id: str,
) -> Optional[HelpCategory]:
    """
    Soft delete a category.

    Args:
        session: Database session
        category_id: Category UUID string

    Returns:
        The deleted HelpCategory or None if not found
    """
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(HelpCategory).where(
            HelpCategory.id == cat_uuid,
            HelpCategory.deleted_time.is_(None),
        )
    )
    category = result.scalars().first()

    if not category:
        return None

    category.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(category)
    except Exception as e:
        await session.rollback()
        raise e

    return category


# ============================================================================
# HelpArticle CRUD
# ============================================================================


async def create_article(
    session: AsyncSession,
    article_data: dict[str, Any],
    organization_id: Optional[str],
    created_by_id: str,
) -> HelpArticle:
    """
    Create a help article.

    Args:
        session: Database session
        article_data: Article data including:
            - title: Article title (required)
            - slug: URL-friendly slug (required)
            - content: Markdown content (required)
            - category_id: Category UUID (required)
            - status: draft or published (default: draft)
            - published_at: Publication datetime (optional)
            - featured_image_url: Featured image URL (optional)
        organization_id: Organization UUID string (None for platform-wide)
        created_by_id: User ID creating the article

    Returns:
        The created HelpArticle

    Raises:
        ValueError: If slug already exists
    """
    org_uuid = UUID(organization_id) if organization_id else None
    creator_uuid = (
        created_by_id if isinstance(created_by_id, UUID) else UUID(created_by_id)
    )
    category_id = article_data["category_id"]
    category_uuid = category_id if isinstance(category_id, UUID) else UUID(category_id)

    # Check slug uniqueness
    existing = await session.execute(
        select(HelpArticle).where(
            HelpArticle.slug == article_data["slug"],
            HelpArticle.deleted_time.is_(None),
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(f"Article with slug '{article_data['slug']}' already exists")

    # Auto-set published_at if status is published and not provided
    published_at = article_data.get("published_at")
    if article_data.get("status") == "published" and not published_at:
        published_at = datetime.now(timezone.utc)

    article = HelpArticle(
        organization_id=org_uuid,
        title=article_data["title"],
        slug=article_data["slug"],
        content=article_data["content"],
        category_id=category_uuid,
        status=article_data.get("status", "draft"),
        published_at=published_at,
        featured_image_url=article_data.get("featured_image_url"),
        display_order=article_data.get("display_order", 0),
        created_by_id=creator_uuid,
    )

    session.add(article)
    try:
        await session.commit()
        await session.refresh(article)
    except Exception as e:
        await session.rollback()
        raise e

    return article


async def get_article_by_id(
    session: AsyncSession,
    article_id: str,
    organization_id: Optional[str],
    published_only: bool = False,
    platform_only: bool = False,
) -> Optional[HelpArticle]:
    """
    Get article by ID within organization context.

    Returns the article if it belongs to the organization or is platform-wide.
    Super admins can pass None for organization_id to access all articles.

    Args:
        session: Database session
        article_id: Article UUID string
        organization_id: Organization UUID string (None for unfiltered admin view)
        published_only: If True, only return published articles
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        The HelpArticle or None if not found
    """
    art_uuid = UUID(article_id)

    conditions: list[ColumnElement[bool]] = [
        HelpArticle.id == art_uuid,
        HelpArticle.deleted_time.is_(None),
    ]

    if published_only:
        conditions.append(HelpArticle.status == "published")

    conditions.extend(
        _visibility_conditions(
            HelpArticle.organization_id, organization_id, platform_only
        )
    )

    result = await session.execute(select(HelpArticle).where(*conditions))
    return result.scalars().first()


async def get_article_by_slug(
    session: AsyncSession,
    slug: str,
    organization_id: Optional[str],
    published_only: bool = False,
    platform_only: bool = False,
) -> Optional[HelpArticle]:
    """
    Get article by slug within organization context.

    Args:
        session: Database session
        slug: Article slug
        organization_id: Organization UUID string (None for unfiltered admin view)
        published_only: If True, only return published articles
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        The HelpArticle or None if not found
    """
    conditions: list[ColumnElement[bool]] = [
        HelpArticle.slug == slug,
        HelpArticle.deleted_time.is_(None),
    ]

    if published_only:
        conditions.append(HelpArticle.status == "published")

    conditions.extend(
        _visibility_conditions(
            HelpArticle.organization_id, organization_id, platform_only
        )
    )

    result = await session.execute(select(HelpArticle).where(*conditions))
    return result.scalars().first()


async def get_articles(
    session: AsyncSession,
    organization_id: Optional[str],
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    published_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    platform_only: bool = False,
) -> tuple[list[HelpArticle], int]:
    """
    Get articles with optional filtering.

    Args:
        session: Database session
        organization_id: Organization UUID string (None for unfiltered admin view)
        category_id: Filter by category UUID (optional)
        status: Filter by status (optional)
        published_only: If True, only return published articles
        limit: Maximum number of results
        offset: Number of results to skip
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        Tuple of (list of articles, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        HelpArticle.deleted_time.is_(None),
    ]

    if published_only or status == "published":
        conditions.append(HelpArticle.status == "published")
    elif status:
        conditions.append(HelpArticle.status == status)

    if category_id:
        cat_uuid = UUID(category_id)
        conditions.append(HelpArticle.category_id == cat_uuid)

    conditions.extend(
        _visibility_conditions(
            HelpArticle.organization_id, organization_id, platform_only
        )
    )

    # Count query
    count_result = await session.execute(
        select(func.count(HelpArticle.id)).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query
    result = await session.execute(
        select(HelpArticle)
        .where(*conditions)
        .order_by(
            HelpArticle.display_order.asc(),
            HelpArticle.published_at.desc().nulls_last(),
        )
        .limit(limit)
        .offset(offset)
    )
    articles = result.scalars().all()

    return list(articles), total


async def search_articles(
    session: AsyncSession,
    query: str,
    organization_id: Optional[str],
    published_only: bool = True,
    limit: int = 50,
    platform_only: bool = False,
) -> list[HelpArticle]:
    """
    Search articles by title and content.

    Args:
        session: Database session
        query: Search query string
        organization_id: Organization UUID string (None for unfiltered admin view)
        published_only: If True, only search published articles
        limit: Maximum number of results
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        List of matching HelpArticles
    """
    conditions: list[ColumnElement[bool]] = [
        HelpArticle.deleted_time.is_(None),
    ]

    if published_only:
        conditions.append(HelpArticle.status == "published")

    conditions.extend(
        _visibility_conditions(
            HelpArticle.organization_id, organization_id, platform_only
        )
    )

    # Search in title and content (case-insensitive)
    search_pattern = f"%{query}%"
    conditions.append(
        or_(
            HelpArticle.title.ilike(search_pattern),
            HelpArticle.content.ilike(search_pattern),
        )
    )

    result = await session.execute(
        select(HelpArticle)
        .where(*conditions)
        .order_by(
            HelpArticle.display_order.asc(),
            HelpArticle.published_at.desc().nulls_last(),
        )
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_article(
    session: AsyncSession,
    article_id: str,
    organization_id: Optional[str],
    article_data: dict[str, Any],
) -> Optional[HelpArticle]:
    """
    Update an article.

    Args:
        session: Database session
        article_id: Article UUID string
        organization_id: Organization UUID string (None for super admin)
        article_data: Fields to update (all optional):
            - title, slug, content, category_id, status, published_at, featured_image_url

    Returns:
        The updated HelpArticle or None if not found

    Raises:
        ValueError: If trying to update an article from another organization or slug exists
    """
    art_uuid = UUID(article_id)

    result = await session.execute(
        select(HelpArticle).where(
            HelpArticle.id == art_uuid,
            HelpArticle.deleted_time.is_(None),
        )
    )
    article = result.scalars().first()

    if not article:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Can only update own org articles or platform-wide (if super admin)
        if article.organization_id is not None and article.organization_id != org_uuid:
            return None
    # else: super admin can update all

    # Check slug uniqueness if updating
    if "slug" in article_data and article_data["slug"] != article.slug:
        existing = await session.execute(
            select(HelpArticle).where(
                HelpArticle.slug == article_data["slug"],
                HelpArticle.id != art_uuid,
                HelpArticle.deleted_time.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Article with slug '{article_data['slug']}' already exists"
            )

    # Auto-set published_at when changing to published status
    if "status" in article_data:
        if article_data["status"] == "published" and article.status != "published":
            if "published_at" not in article_data:
                article_data["published_at"] = datetime.now(timezone.utc)

    # Update allowed fields
    updatable_fields = [
        "title",
        "slug",
        "content",
        "category_id",
        "status",
        "published_at",
        "featured_image_url",
        "display_order",
    ]
    for field in updatable_fields:
        if field in article_data:
            if field == "category_id":
                value = article_data[field]
                setattr(
                    article, field, value if isinstance(value, UUID) else UUID(value)
                )
            else:
                setattr(article, field, article_data[field])

    try:
        await session.commit()
        await session.refresh(article)
    except Exception as e:
        await session.rollback()
        raise e

    return article


async def soft_delete_article(
    session: AsyncSession,
    article_id: str,
    organization_id: Optional[str],
) -> Optional[HelpArticle]:
    """
    Soft delete an article.

    Args:
        session: Database session
        article_id: Article UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The deleted HelpArticle or None if not found

    Raises:
        ValueError: If trying to delete an article from another organization
    """
    art_uuid = UUID(article_id)

    result = await session.execute(
        select(HelpArticle).where(
            HelpArticle.id == art_uuid,
            HelpArticle.deleted_time.is_(None),
        )
    )
    article = result.scalars().first()

    if not article:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Can only delete own org articles
        if article.organization_id is not None and article.organization_id != org_uuid:
            return None
    # else: super admin can delete all

    article.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(article)
    except Exception as e:
        await session.rollback()
        raise e

    return article


# ============================================================================
# HelpFaq CRUD
# ============================================================================


async def create_faq(
    session: AsyncSession,
    faq_data: dict[str, Any],
    organization_id: Optional[str],
) -> HelpFaq:
    """
    Create a FAQ.

    Args:
        session: Database session
        faq_data: FAQ data including:
            - question: FAQ question (required)
            - answer: FAQ answer (required)
            - category_id: Category UUID (required)
            - status: draft or published (default: draft)
            - display_order: Display order (default: 0)
        organization_id: Organization UUID string (None for platform-wide)

    Returns:
        The created HelpFaq
    """
    org_uuid = UUID(organization_id) if organization_id else None
    category_id = faq_data["category_id"]
    category_uuid = category_id if isinstance(category_id, UUID) else UUID(category_id)

    faq = HelpFaq(
        organization_id=org_uuid,
        question=faq_data["question"],
        answer=faq_data["answer"],
        category_id=category_uuid,
        status=faq_data.get("status", "draft"),
        display_order=faq_data.get("display_order", 0),
    )

    session.add(faq)
    try:
        await session.commit()
        await session.refresh(faq)
    except Exception as e:
        await session.rollback()
        raise e

    return faq


async def get_faq_by_id(
    session: AsyncSession,
    faq_id: str,
    organization_id: Optional[str],
    published_only: bool = False,
    platform_only: bool = False,
) -> Optional[HelpFaq]:
    """
    Get FAQ by ID within organization context.

    Returns the FAQ if it belongs to the organization or is platform-wide.
    Super admins can pass None for organization_id to access all FAQs.

    Args:
        session: Database session
        faq_id: FAQ UUID string
        organization_id: Organization UUID string (None for unfiltered admin view)
        published_only: If True, only return published FAQs
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        The HelpFaq or None if not found
    """
    faq_uuid = UUID(faq_id)

    conditions: list[ColumnElement[bool]] = [
        HelpFaq.id == faq_uuid,
        HelpFaq.deleted_time.is_(None),
    ]

    if published_only:
        conditions.append(HelpFaq.status == "published")

    conditions.extend(
        _visibility_conditions(HelpFaq.organization_id, organization_id, platform_only)
    )

    result = await session.execute(select(HelpFaq).where(*conditions))
    return result.scalars().first()


async def get_faqs(
    session: AsyncSession,
    organization_id: Optional[str],
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    published_only: bool = False,
    limit: int = 100,
    offset: int = 0,
    platform_only: bool = False,
) -> tuple[list[HelpFaq], int]:
    """
    Get FAQs with optional filtering.

    Args:
        session: Database session
        organization_id: Organization UUID string (None for unfiltered admin view)
        category_id: Filter by category UUID (optional)
        status: Filter by status (optional)
        published_only: If True, only return published FAQs
        limit: Maximum number of results
        offset: Number of results to skip
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        Tuple of (list of FAQs, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        HelpFaq.deleted_time.is_(None),
    ]

    if published_only or status == "published":
        conditions.append(HelpFaq.status == "published")
    elif status:
        conditions.append(HelpFaq.status == status)

    if category_id:
        cat_uuid = UUID(category_id)
        conditions.append(HelpFaq.category_id == cat_uuid)

    conditions.extend(
        _visibility_conditions(HelpFaq.organization_id, organization_id, platform_only)
    )

    # Count query
    count_result = await session.execute(
        select(func.count(HelpFaq.id)).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query
    result = await session.execute(
        select(HelpFaq)
        .where(*conditions)
        .order_by(HelpFaq.display_order.asc(), HelpFaq.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    faqs = result.scalars().all()

    return list(faqs), total


async def search_faqs(
    session: AsyncSession,
    query: str,
    organization_id: Optional[str],
    published_only: bool = True,
    limit: int = 50,
    platform_only: bool = False,
) -> list[HelpFaq]:
    """
    Search FAQs by question and answer.

    Args:
        session: Database session
        query: Search query string
        organization_id: Organization UUID string (None for unfiltered admin view)
        published_only: If True, only search published FAQs
        limit: Maximum number of results
        platform_only: If True, restrict to platform-wide content only
            (required for unauthenticated public access)

    Returns:
        List of matching HelpFaqs
    """
    conditions: list[ColumnElement[bool]] = [
        HelpFaq.deleted_time.is_(None),
    ]

    if published_only:
        conditions.append(HelpFaq.status == "published")

    conditions.extend(
        _visibility_conditions(HelpFaq.organization_id, organization_id, platform_only)
    )

    # Search in question and answer (case-insensitive)
    search_pattern = f"%{query}%"
    conditions.append(
        or_(
            HelpFaq.question.ilike(search_pattern),
            HelpFaq.answer.ilike(search_pattern),
        )
    )

    result = await session.execute(
        select(HelpFaq)
        .where(*conditions)
        .order_by(HelpFaq.display_order.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_faq(
    session: AsyncSession,
    faq_id: str,
    organization_id: Optional[str],
    faq_data: dict[str, Any],
) -> Optional[HelpFaq]:
    """
    Update a FAQ.

    Args:
        session: Database session
        faq_id: FAQ UUID string
        organization_id: Organization UUID string (None for super admin)
        faq_data: Fields to update (all optional):
            - question, answer, category_id, status, display_order

    Returns:
        The updated HelpFaq or None if not found

    Raises:
        ValueError: If trying to update a FAQ from another organization
    """
    faq_uuid = UUID(faq_id)

    result = await session.execute(
        select(HelpFaq).where(
            HelpFaq.id == faq_uuid,
            HelpFaq.deleted_time.is_(None),
        )
    )
    faq = result.scalars().first()

    if not faq:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Can only update own org FAQs or platform-wide (if super admin)
        if faq.organization_id is not None and faq.organization_id != org_uuid:
            return None
    # else: super admin can update all

    # Update allowed fields
    updatable_fields = [
        "question",
        "answer",
        "category_id",
        "status",
        "display_order",
    ]
    for field in updatable_fields:
        if field in faq_data:
            if field == "category_id":
                value = faq_data[field]
                setattr(faq, field, value if isinstance(value, UUID) else UUID(value))
            else:
                setattr(faq, field, faq_data[field])

    try:
        await session.commit()
        await session.refresh(faq)
    except Exception as e:
        await session.rollback()
        raise e

    return faq


async def soft_delete_faq(
    session: AsyncSession,
    faq_id: str,
    organization_id: Optional[str],
) -> Optional[HelpFaq]:
    """
    Soft delete a FAQ.

    Args:
        session: Database session
        faq_id: FAQ UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The deleted HelpFaq or None if not found

    Raises:
        ValueError: If trying to delete a FAQ from another organization
    """
    faq_uuid = UUID(faq_id)

    result = await session.execute(
        select(HelpFaq).where(
            HelpFaq.id == faq_uuid,
            HelpFaq.deleted_time.is_(None),
        )
    )
    faq = result.scalars().first()

    if not faq:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Can only delete own org FAQs
        if faq.organization_id is not None and faq.organization_id != org_uuid:
            return None
    # else: super admin can delete all

    faq.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(faq)
    except Exception as e:
        await session.rollback()
        raise e

    return faq


# ============================================================================
# Reorder Operations
# ============================================================================


async def reorder_articles(
    session: AsyncSession,
    items: list[dict[str, Any]],
    organization_id: Optional[str],
) -> int:
    """
    Batch update display_order for multiple articles.

    Args:
        session: Database session
        items: List of dicts with 'id' and 'display_order' keys
        organization_id: Organization UUID string (None for super admin)

    Returns:
        Number of articles updated

    Raises:
        ValueError: If any article not found or not accessible
    """
    updated_count = 0

    for item in items:
        article_id = str(item["id"])
        new_order = item["display_order"]

        art_uuid = UUID(article_id)

        result = await session.execute(
            select(HelpArticle).where(
                HelpArticle.id == art_uuid,
                HelpArticle.deleted_time.is_(None),
            )
        )
        article = result.scalars().first()

        if not article:
            raise ValueError(f"Article with ID '{article_id}' not found")

        # Check organization ownership
        if organization_id is not None:
            org_uuid = UUID(organization_id)
            if (
                article.organization_id is not None
                and article.organization_id != org_uuid
            ):
                raise ValueError(f"Article with ID '{article_id}' not accessible")

        article.display_order = new_order
        updated_count += 1

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return updated_count


async def reorder_faqs(
    session: AsyncSession,
    items: list[dict[str, Any]],
    organization_id: Optional[str],
) -> int:
    """
    Batch update display_order for multiple FAQs.

    Args:
        session: Database session
        items: List of dicts with 'id' and 'display_order' keys
        organization_id: Organization UUID string (None for super admin)

    Returns:
        Number of FAQs updated

    Raises:
        ValueError: If any FAQ not found or not accessible
    """
    updated_count = 0

    for item in items:
        faq_id = str(item["id"])
        new_order = item["display_order"]

        faq_uuid = UUID(faq_id)

        result = await session.execute(
            select(HelpFaq).where(
                HelpFaq.id == faq_uuid,
                HelpFaq.deleted_time.is_(None),
            )
        )
        faq = result.scalars().first()

        if not faq:
            raise ValueError(f"FAQ with ID '{faq_id}' not found")

        # Check organization ownership
        if organization_id is not None:
            org_uuid = UUID(organization_id)
            if faq.organization_id is not None and faq.organization_id != org_uuid:
                raise ValueError(f"FAQ with ID '{faq_id}' not accessible")

        faq.display_order = new_order
        updated_count += 1

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return updated_count


async def reorder_categories(
    session: AsyncSession,
    items: list[dict[str, Any]],
) -> int:
    """
    Batch update display_order for multiple categories.

    Args:
        session: Database session
        items: List of dicts with 'id' and 'display_order' keys

    Returns:
        Number of categories updated

    Raises:
        ValueError: If any category not found
    """
    updated_count = 0

    for item in items:
        category_id = str(item["id"])
        new_order = item["display_order"]

        cat_uuid = UUID(category_id)

        result = await session.execute(
            select(HelpCategory).where(
                HelpCategory.id == cat_uuid,
                HelpCategory.deleted_time.is_(None),
            )
        )
        category = result.scalars().first()

        if not category:
            raise ValueError(f"Category with ID '{category_id}' not found")

        category.display_order = new_order
        updated_count += 1

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return updated_count
