"""
CRUD operations for NotificationCategory model.

Categories support mixed scope:
- organization_id=None: System categories (available to all organizations)
- organization_id=UUID: Organization-specific categories

When fetching categories, include both org-specific and system categories.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.query_builder import (
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import SortSpec
from src.models.notification_category import NotificationCategory


# SDL configuration for notification categories
CATEGORY_FIELD_MAPPING: dict[str, str] = {}


async def get_categories(
    session: AsyncSession,
    organization_id: str,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[NotificationCategory], int]:
    """
    Get all notification categories available to an organization with SDL sorting.

    Returns both organization-specific categories and system categories.

    Args:
        session: Database session
        organization_id: Organization UUID string
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of categories, total count)
    """
    org_uuid = UUID(organization_id)

    # Include both org categories and system categories
    base_query = select(NotificationCategory).where(
        or_(
            NotificationCategory.organization_id == org_uuid,
            NotificationCategory.organization_id.is_(None),
        ),
        NotificationCategory.deleted_time.is_(None),
    )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to display_order, then by org, then name)
    if sorts:
        base_query = apply_sort(
            base_query, NotificationCategory, sorts, CATEGORY_FIELD_MAPPING
        )
    else:
        base_query = base_query.order_by(
            NotificationCategory.display_order.asc(),
            NotificationCategory.organization_id.desc().nulls_last(),
            NotificationCategory.name.asc(),
        )

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    categories = result.scalars().all()

    return list(categories), total_count


async def get_category_by_code(
    session: AsyncSession,
    organization_id: str,
    code: str,
) -> Optional[NotificationCategory]:
    """
    Get category by code, checking organization first, then system categories.

    This implements the fallback pattern:
    1. First, try to find an org-specific category
    2. If not found, fall back to system category (organization_id=None)

    Args:
        session: Database session
        organization_id: Organization UUID string
        code: Category code (e.g., 'marketing', 'announcements')

    Returns:
        The NotificationCategory or None if not found
    """
    org_uuid = UUID(organization_id)

    # First try organization-specific category
    result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.organization_id == org_uuid,
            NotificationCategory.code == code,
            NotificationCategory.deleted_time.is_(None),
        )
    )
    category = result.scalars().first()

    if category:
        return category

    # Fall back to system category
    result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.organization_id.is_(None),
            NotificationCategory.code == code,
            NotificationCategory.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_category_by_id(
    session: AsyncSession,
    category_id: str,
    organization_id: str,
) -> Optional[NotificationCategory]:
    """
    Get category by ID within organization context.

    Returns the category if it belongs to the organization or is a system category.

    Args:
        session: Database session
        category_id: Category UUID string
        organization_id: Organization UUID string

    Returns:
        The NotificationCategory or None if not found
    """
    org_uuid = UUID(organization_id)
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.id == cat_uuid,
            or_(
                NotificationCategory.organization_id == org_uuid,
                NotificationCategory.organization_id.is_(None),
            ),
            NotificationCategory.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_category(
    session: AsyncSession,
    organization_id: str,
    category_data: dict[str, Any],
) -> NotificationCategory:
    """
    Create an organization-specific notification category.

    Args:
        session: Database session
        organization_id: Organization UUID string
        category_data: Category data including:
            - code: Category code (required)
            - name: Category display name (required)
            - description: Description (optional)
            - default_enabled: Whether enabled by default (default: True)
            - user_configurable: Whether users can change preference (default: True)
            - display_order: Order for display (default: 0)

    Returns:
        The created NotificationCategory

    Raises:
        ValueError: If category with same code already exists for organization
    """
    org_uuid = UUID(organization_id)

    # Check if category with same code exists for this org
    existing_result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.organization_id == org_uuid,
            NotificationCategory.code == category_data["code"],
            NotificationCategory.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"Category with code '{category_data['code']}' already exists for this organization"
        )

    category = NotificationCategory(
        organization_id=org_uuid,
        code=category_data["code"],
        name=category_data["name"],
        description=category_data.get("description"),
        default_enabled=category_data.get("default_enabled", True),
        user_configurable=category_data.get("user_configurable", True),
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


async def update_category(
    session: AsyncSession,
    category_id: str,
    organization_id: str,
    category_data: dict[str, Any],
) -> Optional[NotificationCategory]:
    """
    Update an organization-specific notification category.

    Only org-specific categories can be updated. System categories are read-only.

    Args:
        session: Database session
        category_id: Category UUID string
        organization_id: Organization UUID string
        category_data: Fields to update (all optional):
            - name, description, default_enabled, user_configurable, display_order

    Returns:
        The updated NotificationCategory or None if not found

    Raises:
        ValueError: If trying to update a system category
    """
    org_uuid = UUID(organization_id)
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.id == cat_uuid,
            NotificationCategory.deleted_time.is_(None),
        )
    )
    category = result.scalars().first()

    if not category:
        return None

    # Check if this is a system category (cannot be updated by org)
    if category.organization_id is None:
        raise ValueError(
            "System categories cannot be modified. Create an org-specific category instead."
        )

    # Check if category belongs to this organization
    if category.organization_id != org_uuid:
        return None

    # Update allowed fields
    updatable_fields = [
        "name",
        "description",
        "default_enabled",
        "user_configurable",
        "display_order",
    ]
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


async def delete_category(
    session: AsyncSession,
    category_id: str,
    organization_id: str,
) -> Optional[NotificationCategory]:
    """
    Soft delete an organization-specific notification category.

    Only org-specific categories can be deleted. System categories are protected.

    Args:
        session: Database session
        category_id: Category UUID string
        organization_id: Organization UUID string

    Returns:
        The deleted NotificationCategory or None if not found

    Raises:
        ValueError: If trying to delete a system category
    """
    org_uuid = UUID(organization_id)
    cat_uuid = UUID(category_id)

    result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.id == cat_uuid,
            NotificationCategory.deleted_time.is_(None),
        )
    )
    category = result.scalars().first()

    if not category:
        return None

    # Check if this is a system category
    if category.organization_id is None:
        raise ValueError("System categories cannot be deleted.")

    # Check if category belongs to this organization
    if category.organization_id != org_uuid:
        return None

    category.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(category)
    except Exception as e:
        await session.rollback()
        raise e

    return category


# Admin-only functions for system categories


async def create_system_category(
    session: AsyncSession,
    category_data: dict[str, Any],
) -> NotificationCategory:
    """
    Create a system notification category (admin only).

    Args:
        session: Database session
        category_data: Category data (same as create_category)

    Returns:
        The created NotificationCategory

    Raises:
        ValueError: If category with same code already exists
    """
    # Check if system category with same code exists
    existing_result = await session.execute(
        select(NotificationCategory).where(
            NotificationCategory.organization_id.is_(None),
            NotificationCategory.code == category_data["code"],
            NotificationCategory.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"System category with code '{category_data['code']}' already exists"
        )

    category = NotificationCategory(
        organization_id=None,  # System category
        code=category_data["code"],
        name=category_data["name"],
        description=category_data.get("description"),
        default_enabled=category_data.get("default_enabled", True),
        user_configurable=category_data.get("user_configurable", True),
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


async def get_system_categories(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[NotificationCategory], int]:
    """
    Get all system notification categories (admin only).

    Args:
        session: Database session
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of categories, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        NotificationCategory.organization_id.is_(None),
        NotificationCategory.deleted_time.is_(None),
    ]

    base_query = select(NotificationCategory).where(*conditions)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query
    data_query = (
        base_query.order_by(
            NotificationCategory.display_order.asc(),
            NotificationCategory.code.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    categories = result.scalars().all()

    return list(categories), total_count
