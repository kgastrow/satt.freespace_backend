"""
Help Center API endpoints.

Provides public endpoints for viewing published help content (categories, articles, FAQs, search)
and admin endpoints for content management (CRUD operations restricted to super admins).

Public endpoints are unauthenticated to allow access from new browser tabs and before login.
They return only published, platform-wide content.
Admin endpoints require super admin role for creating/editing platform-wide help content.
"""

import traceback
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.crud.help_center import (
    create_article,
    create_category,
    create_faq,
    get_article_by_id,
    get_article_by_slug,
    get_articles,
    get_categories,
    get_faq_by_id,
    get_faqs,
    reorder_articles,
    reorder_categories,
    reorder_faqs,
    search_articles,
    search_faqs,
    soft_delete_article,
    soft_delete_category,
    soft_delete_faq,
    update_article,
    update_category,
    update_faq,
)
from src.logger.logger import Logger
from src.serialisers.help_center import (
    HelpArticleCreate,
    HelpArticleListResponse,
    HelpArticleResponse,
    HelpArticleUpdate,
    HelpCategoryCreate,
    HelpCategoryListResponse,
    HelpCategoryResponse,
    HelpCategoryUpdate,
    HelpDeleteResponse,
    HelpFaqCreate,
    HelpFaqListResponse,
    HelpFaqResponse,
    HelpFaqUpdate,
    HelpSearchResponse,
    ReorderRequest,
    ReorderResponse,
)


router = APIRouter(prefix="/help", tags=["help-center"])

# Slug pattern: lowercase letters, numbers, and hyphens (no leading/trailing hyphens)
SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def validate_uuid(value: Optional[str], field_name: str) -> Optional[str]:
    """Validate that a string is a valid UUID format."""
    if value is None:
        return None
    try:
        UUID(value)
        return value
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name} format. Expected UUID.",
            detail_code=f"help_center.invalid_{field_name}",
        )


# ============================================================================
# Public Endpoints - Categories
# ============================================================================


@router.get("/categories", response_model=HelpCategoryListResponse)
async def get_categories_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Get all help categories.

    Returns all categories ordered by display_order.
    Categories are platform-wide and publicly accessible (no authentication required).
    """
    categories, total = await get_categories(
        session=session,
        limit=limit,
        offset=offset,
    )

    return HelpCategoryListResponse(
        items=[HelpCategoryResponse.model_validate(cat) for cat in categories],
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Public Endpoints - Articles
# ============================================================================


@router.get("/articles", response_model=HelpArticleListResponse)
async def get_articles_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Get published help articles.

    Returns published platform-wide articles, optionally filtered by category.
    Publicly accessible (no authentication required).
    """
    # Validate category_id is a valid UUID format if provided
    validated_category_id = validate_uuid(category_id, "category_id")

    articles, total = await get_articles(
        session=session,
        organization_id=None,
        platform_only=True,  # Public: platform-wide content only, never org content
        category_id=validated_category_id,
        published_only=True,
        limit=limit,
        offset=offset,
    )

    return HelpArticleListResponse(
        items=[HelpArticleResponse.from_orm_article(art) for art in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/articles/{slug}", response_model=HelpArticleResponse)
async def get_article_by_slug_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    slug: str = Path(
        ...,
        pattern=SLUG_PATTERN,
        description="Article slug (lowercase letters, numbers, and hyphens)",
    ),
):
    """
    Get a published help article by slug.

    Returns the article if it is published and platform-wide.
    Publicly accessible (no authentication required).
    """
    article = await get_article_by_slug(
        session=session,
        slug=slug,
        organization_id=None,
        platform_only=True,  # Public: platform-wide content only, never org content
        published_only=True,
    )

    if not article:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found",
            detail_code="help_article.not_found",
        )

    return HelpArticleResponse.from_orm_article(article)


# ============================================================================
# Public Endpoints - FAQs
# ============================================================================


@router.get("/faqs", response_model=HelpFaqListResponse)
async def get_faqs_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    Get published FAQs.

    Returns published platform-wide FAQs ordered by display_order, optionally filtered by category.
    Publicly accessible (no authentication required).
    """
    # Validate category_id is a valid UUID format if provided
    validated_category_id = validate_uuid(category_id, "category_id")

    faqs, total = await get_faqs(
        session=session,
        organization_id=None,
        platform_only=True,  # Public: platform-wide content only, never org content
        category_id=validated_category_id,
        published_only=True,
        limit=limit,
        offset=offset,
    )

    return HelpFaqListResponse(
        items=[HelpFaqResponse.from_orm_faq(faq) for faq in faqs],
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Public Endpoints - Search
# ============================================================================


@router.get("/search", response_model=HelpSearchResponse)
async def search_help_endpoint(
    session: Annotated[AsyncSession, Depends(get_session)],
    q: str = Query(..., min_length=1, description="Search query"),
):
    """
    Search help articles and FAQs by keyword.

    Searches title/content in articles and question/answer in FAQs.
    Returns only published platform-wide content.
    Publicly accessible (no authentication required).
    """
    articles = await search_articles(
        session=session,
        query=q,
        organization_id=None,
        platform_only=True,  # Public: platform-wide content only, never org content
        published_only=True,
        limit=50,
    )

    faqs = await search_faqs(
        session=session,
        query=q,
        organization_id=None,
        platform_only=True,  # Public: platform-wide content only, never org content
        published_only=True,
        limit=50,
    )

    return HelpSearchResponse(
        articles=[HelpArticleResponse.from_orm_article(art) for art in articles],
        faqs=[HelpFaqResponse.from_orm_faq(faq) for faq in faqs],
        total_results=len(articles) + len(faqs),
    )


# ============================================================================
# Admin Endpoints - Categories
# ============================================================================


@router.post(
    "/admin/categories",
    response_model=HelpCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category_endpoint(
    http_request: Request,
    request: HelpCategoryCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a help category.

    Requires super admin role.
    Categories are platform-wide and visible to all users.
    """
    try:
        category = await create_category(
            session=session,
            category_data=request.model_dump(),
        )
        return HelpCategoryResponse.model_validate(category)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_category.invalid",
        )
    except IntegrityError as e:
        error_tb = traceback.format_exc()
        Logger.warning(f"Integrity error creating category: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category could not be created due to a conflict",
            detail_code="help_category.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating category: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating category",
            detail_code="help_category.database_error",
        )


@router.put("/admin/categories/reorder", response_model=ReorderResponse)
async def reorder_categories_endpoint(
    http_request: Request,
    request: ReorderRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reorder categories by updating their display_order.

    Requires super admin role.
    Accepts a list of category IDs with their new display_order values.
    """
    try:
        items = [
            {"id": item.id, "display_order": item.display_order}
            for item in request.items
        ]
        updated_count = await reorder_categories(
            session=session,
            items=items,
        )
        return ReorderResponse(
            message="Categories reordered successfully",
            message_code="help_category.reordered",
            updated_count=updated_count,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_category.reorder_invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error reordering categories: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while reordering categories",
            detail_code="help_category.database_error",
        )


@router.put("/admin/categories/{category_id}", response_model=HelpCategoryResponse)
async def update_category_endpoint(
    http_request: Request,
    category_id: str,
    request: HelpCategoryUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a help category.

    Requires super admin role.
    """
    # Validate category_id is a valid UUID format
    validate_uuid(category_id, "category_id")

    try:
        category = await update_category(
            session=session,
            category_id=category_id,
            category_data=request.model_dump(exclude_unset=True),
        )

        if not category:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
                detail_code="help_category.not_found",
            )

        return HelpCategoryResponse.model_validate(category)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_category.invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error updating category: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while updating category",
            detail_code="help_category.database_error",
        )


@router.delete("/admin/categories/{category_id}", status_code=status.HTTP_200_OK)
async def delete_category_endpoint(
    http_request: Request,
    category_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a help category.

    Requires super admin role.
    """
    # Validate category_id is a valid UUID format
    validate_uuid(category_id, "category_id")

    try:
        category = await soft_delete_category(
            session=session,
            category_id=category_id,
        )

        if not category:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Category not found",
                detail_code="help_category.not_found",
            )

        return HelpDeleteResponse(
            message="Category deleted successfully",
            message_code="help_category.deleted",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error deleting category: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deleting category",
            detail_code="help_category.database_error",
        )


# ============================================================================
# Admin Endpoints - Articles
# ============================================================================


@router.get("/admin/articles", response_model=HelpArticleListResponse)
async def list_all_articles_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List all help articles (admin view).

    Requires super admin role.
    Returns all articles including drafts, across all organizations.
    """
    # Validate category_id is a valid UUID format if provided
    validated_category_id = validate_uuid(category_id, "category_id")

    articles, total = await get_articles(
        session=session,
        organization_id=None,  # Super admin: unfiltered cross-org view
        platform_only=False,
        category_id=validated_category_id,
        status=status_filter,
        published_only=False,
        limit=limit,
        offset=offset,
    )

    return HelpArticleListResponse(
        items=[HelpArticleResponse.from_orm_article(art) for art in articles],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/articles",
    response_model=HelpArticleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_article_endpoint(
    http_request: Request,
    request: HelpArticleCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a help article.

    Requires super admin role.
    Can create platform-wide articles (is_platform_wide=True) or org-specific articles.
    """
    # Determine organization_id based on is_platform_wide flag
    organization_id: Optional[str] = None
    if not request.is_platform_wide:
        organization_id = current_user.organization_id

    try:
        article_data = request.model_dump(exclude={"is_platform_wide"})
        article = await create_article(
            session=session,
            article_data=article_data,
            organization_id=organization_id,
            created_by_id=current_user.id,
        )
        return HelpArticleResponse.from_orm_article(article)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_article.invalid",
        )
    except IntegrityError as e:
        error_tb = traceback.format_exc()
        Logger.warning(f"Integrity error creating article: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="Article could not be created due to a conflict",
            detail_code="help_article.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating article: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating article",
            detail_code="help_article.database_error",
        )


@router.put("/admin/articles/reorder", response_model=ReorderResponse)
async def reorder_articles_endpoint(
    http_request: Request,
    request: ReorderRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reorder help articles by updating their display_order.

    Requires super admin role.
    Accepts a list of article IDs with their new display_order values.
    """
    try:
        items = [
            {"id": item.id, "display_order": item.display_order}
            for item in request.items
        ]
        updated_count = await reorder_articles(
            session=session,
            items=items,
            organization_id=None,  # Super admin can reorder all
        )
        return ReorderResponse(
            message="Articles reordered successfully",
            message_code="help_article.reordered",
            updated_count=updated_count,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_article.reorder_invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error reordering articles: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while reordering articles",
            detail_code="help_article.database_error",
        )


@router.get("/admin/articles/{article_id}", response_model=HelpArticleResponse)
async def get_article_by_id_endpoint(
    article_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a help article by ID (admin view).

    Requires super admin role.
    Returns article including drafts.
    """
    # Validate article_id is a valid UUID format
    validate_uuid(article_id, "article_id")

    article = await get_article_by_id(
        session=session,
        article_id=article_id,
        organization_id=None,  # Super admin sees all
        published_only=False,
    )

    if not article:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Article not found",
            detail_code="help_article.not_found",
        )

    return HelpArticleResponse.from_orm_article(article)


@router.put("/admin/articles/{article_id}", response_model=HelpArticleResponse)
async def update_article_endpoint(
    http_request: Request,
    article_id: str,
    request: HelpArticleUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a help article.

    Requires super admin role.
    """
    # Validate article_id is a valid UUID format
    validate_uuid(article_id, "article_id")

    try:
        article = await update_article(
            session=session,
            article_id=article_id,
            organization_id=None,  # Super admin can update all
            article_data=request.model_dump(exclude_unset=True),
        )

        if not article:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found",
                detail_code="help_article.not_found",
            )

        return HelpArticleResponse.from_orm_article(article)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_article.invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error updating article: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while updating article",
            detail_code="help_article.database_error",
        )


@router.delete("/admin/articles/{article_id}", status_code=status.HTTP_200_OK)
async def delete_article_endpoint(
    http_request: Request,
    article_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a help article.

    Requires super admin role.
    """
    # Validate article_id is a valid UUID format
    validate_uuid(article_id, "article_id")

    try:
        article = await soft_delete_article(
            session=session,
            article_id=article_id,
            organization_id=None,  # Super admin can delete all
        )

        if not article:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Article not found",
                detail_code="help_article.not_found",
            )

        return HelpDeleteResponse(
            message="Article deleted successfully",
            message_code="help_article.deleted",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error deleting article: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deleting article",
            detail_code="help_article.database_error",
        )


# ============================================================================
# Admin Endpoints - FAQs
# ============================================================================


@router.get("/admin/faqs", response_model=HelpFaqListResponse)
async def list_all_faqs_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    category_id: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List all FAQs (admin view).

    Requires super admin role.
    Returns all FAQs including drafts, across all organizations.
    """
    # Validate category_id is a valid UUID format if provided
    validated_category_id = validate_uuid(category_id, "category_id")

    faqs, total = await get_faqs(
        session=session,
        organization_id=None,  # Super admin: unfiltered cross-org view
        platform_only=False,
        category_id=validated_category_id,
        status=status_filter,
        published_only=False,
        limit=limit,
        offset=offset,
    )

    return HelpFaqListResponse(
        items=[HelpFaqResponse.from_orm_faq(faq) for faq in faqs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/faqs", response_model=HelpFaqResponse, status_code=status.HTTP_201_CREATED
)
async def create_faq_endpoint(
    http_request: Request,
    request: HelpFaqCreate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a FAQ.

    Requires super admin role.
    Can create platform-wide FAQs (is_platform_wide=True) or org-specific FAQs.
    """
    # Determine organization_id based on is_platform_wide flag
    organization_id: Optional[str] = None
    if not request.is_platform_wide:
        organization_id = current_user.organization_id

    try:
        faq_data = request.model_dump(exclude={"is_platform_wide"})
        faq = await create_faq(
            session=session,
            faq_data=faq_data,
            organization_id=organization_id,
        )
        return HelpFaqResponse.from_orm_faq(faq)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_faq.invalid",
        )
    except IntegrityError as e:
        error_tb = traceback.format_exc()
        Logger.warning(f"Integrity error creating FAQ: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail="FAQ could not be created due to a conflict",
            detail_code="help_faq.conflict",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error creating FAQ: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating FAQ",
            detail_code="help_faq.database_error",
        )


@router.put("/admin/faqs/reorder", response_model=ReorderResponse)
async def reorder_faqs_endpoint(
    http_request: Request,
    request: ReorderRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reorder FAQs by updating their display_order.

    Requires super admin role.
    Accepts a list of FAQ IDs with their new display_order values.
    """
    try:
        items = [
            {"id": item.id, "display_order": item.display_order}
            for item in request.items
        ]
        updated_count = await reorder_faqs(
            session=session,
            items=items,
            organization_id=None,  # Super admin can reorder all
        )
        return ReorderResponse(
            message="FAQs reordered successfully",
            message_code="help_faq.reordered",
            updated_count=updated_count,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_faq.reorder_invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error reordering FAQs: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while reordering FAQs",
            detail_code="help_faq.database_error",
        )


@router.get("/admin/faqs/{faq_id}", response_model=HelpFaqResponse)
async def get_faq_by_id_endpoint(
    faq_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a FAQ by ID (admin view).

    Requires super admin role.
    Returns FAQ including drafts.
    """
    # Validate faq_id is a valid UUID format
    validate_uuid(faq_id, "faq_id")

    faq = await get_faq_by_id(
        session=session,
        faq_id=faq_id,
        organization_id=None,  # Super admin sees all
        published_only=False,
    )

    if not faq:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FAQ not found",
            detail_code="help_faq.not_found",
        )

    return HelpFaqResponse.from_orm_faq(faq)


@router.put("/admin/faqs/{faq_id}", response_model=HelpFaqResponse)
async def update_faq_endpoint(
    http_request: Request,
    faq_id: str,
    request: HelpFaqUpdate,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a FAQ.

    Requires super admin role.
    """
    # Validate faq_id is a valid UUID format
    validate_uuid(faq_id, "faq_id")

    try:
        faq = await update_faq(
            session=session,
            faq_id=faq_id,
            organization_id=None,  # Super admin can update all
            faq_data=request.model_dump(exclude_unset=True),
        )

        if not faq:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FAQ not found",
                detail_code="help_faq.not_found",
            )

        return HelpFaqResponse.from_orm_faq(faq)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="help_faq.invalid",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error updating FAQ: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while updating FAQ",
            detail_code="help_faq.database_error",
        )


@router.delete("/admin/faqs/{faq_id}", status_code=status.HTTP_200_OK)
async def delete_faq_endpoint(
    http_request: Request,
    faq_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a FAQ.

    Requires super admin role.
    """
    # Validate faq_id is a valid UUID format
    validate_uuid(faq_id, "faq_id")

    try:
        faq = await soft_delete_faq(
            session=session,
            faq_id=faq_id,
            organization_id=None,  # Super admin can delete all
        )

        if not faq:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="FAQ not found",
                detail_code="help_faq.not_found",
            )

        return HelpDeleteResponse(
            message="FAQ deleted successfully",
            message_code="help_faq.deleted",
        )
    except SQLAlchemyError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Database error deleting FAQ: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while deleting FAQ",
            detail_code="help_faq.database_error",
        )
