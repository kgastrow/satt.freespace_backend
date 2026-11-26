"""
CRUD operations for Announcement model.

Announcements support mixed scope:
- organization_id=None: Platform-wide announcements (super admin only)
- organization_id=UUID: Organization-specific announcements

Active announcements are filtered by:
- Current time between start_time and end_time
- Soft delete (deleted_time is None)
- Sorted by: non-dismissible first, priority (critical > high > normal > low), then created_time
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.announcement import Announcement


async def create_announcement(
    session: AsyncSession,
    announcement_data: dict[str, Any],
    organization_id: Optional[str],
    created_by_id: str,
) -> Announcement:
    """
    Create an announcement.

    Args:
        session: Database session
        announcement_data: Announcement data including:
            - title: Announcement title (required)
            - body: Announcement body (required)
            - priority: Priority level (default: 'normal')
            - background_color: Background color (optional)
            - featured_image_url: Featured image URL (optional)
            - cta_text: CTA button text (optional)
            - cta_url: CTA URL (optional)
            - cta_dismisses: Whether CTA dismisses (default: True)
            - cta_button_color: CTA button color (optional)
            - cta_button_variant: CTA button variant (optional)
            - is_dismissible: Whether announcement is dismissible (default: True)
            - start_time: Start time (optional)
            - end_time: End time (optional)
        organization_id: Organization UUID string (None for platform-wide)
        created_by_id: User ID creating the announcement

    Returns:
        The created Announcement

    Raises:
        ValueError: If validation fails
    """
    org_uuid = UUID(organization_id) if organization_id else None
    creator_uuid = UUID(created_by_id)

    announcement = Announcement(
        organization_id=org_uuid,
        title=announcement_data["title"],
        body=announcement_data["body"],
        priority=announcement_data.get("priority", "normal"),
        background_color=announcement_data.get("background_color"),
        text_color=announcement_data.get("text_color"),
        featured_image_url=announcement_data.get("featured_image_url"),
        cta_text=announcement_data.get("cta_text"),
        cta_url=announcement_data.get("cta_url"),
        cta_dismisses=announcement_data.get("cta_dismisses", True),
        cta_button_color=announcement_data.get("cta_button_color"),
        cta_button_variant=announcement_data.get("cta_button_variant"),
        is_dismissible=announcement_data.get("is_dismissible", True),
        start_time=announcement_data.get("start_time"),
        end_time=announcement_data.get("end_time"),
        created_by_id=creator_uuid,
    )

    session.add(announcement)
    try:
        await session.commit()
        await session.refresh(announcement)
    except Exception as e:
        await session.rollback()
        raise e

    return announcement


async def get_announcement_by_id(
    session: AsyncSession,
    announcement_id: str,
    organization_id: Optional[str],
) -> Optional[Announcement]:
    """
    Get announcement by ID within organization context.

    Returns the announcement if it belongs to the organization or is platform-wide.
    Super admins can pass None for organization_id to access all announcements.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The Announcement or None if not found
    """
    ann_uuid = UUID(announcement_id)

    conditions: list[ColumnElement[bool]] = [
        Announcement.id == ann_uuid,
        Announcement.deleted_time.is_(None),
    ]

    if organization_id is not None:
        # Regular user/admin: can see own org announcements + platform-wide
        org_uuid = UUID(organization_id)
        conditions.append(
            or_(
                Announcement.organization_id == org_uuid,
                Announcement.organization_id.is_(None),
            )
        )
    # else: super admin with organization_id=None can see all

    result = await session.execute(select(Announcement).where(*conditions))
    return result.scalars().first()


async def get_active_announcements(
    session: AsyncSession,
    organization_id: str,
    user_id: Optional[str] = None,
    exclude_dismissed: bool = True,
) -> list[Announcement]:
    """
    Get active announcements for an organization.

    Returns announcements where:
    - now() is between start_time and end_time (or no time constraints)
    - Includes platform-wide (NULL org_id) and org-specific announcements
    - Excludes soft-deleted announcements
    - Optionally excludes dismissed announcements for a user

    Sorted by:
    1. Non-dismissible first (is_dismissible=False)
    2. Priority: critical > high > normal > low
    3. Created time (newest first)

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string (optional, for dismissal filtering)
        exclude_dismissed: Whether to exclude dismissed announcements (default: True)

    Returns:
        List of active Announcements
    """
    from src.models.announcement_dismissal import AnnouncementDismissal

    org_uuid = UUID(organization_id)
    now = datetime.now(timezone.utc)

    conditions: list[ColumnElement[bool]] = [
        or_(
            Announcement.organization_id == org_uuid,
            Announcement.organization_id.is_(None),
        ),
        Announcement.deleted_time.is_(None),
    ]

    # Time window filtering: must be within start_time and end_time if specified
    conditions.append(
        or_(
            Announcement.start_time.is_(None),
            Announcement.start_time <= now,
        )
    )
    conditions.append(
        or_(
            Announcement.end_time.is_(None),
            Announcement.end_time >= now,
        )
    )

    query = select(Announcement).where(*conditions)

    # Exclude dismissed announcements for this user
    if exclude_dismissed and user_id:
        user_uuid = UUID(user_id)
        dismissed_subquery = (
            select(AnnouncementDismissal.announcement_id)
            .where(AnnouncementDismissal.user_id == user_uuid)
            .scalar_subquery()
        )
        query = query.where(Announcement.id.notin_(dismissed_subquery))

    # Sorting:
    # 1. Non-dismissible first (is_dismissible=False comes first)
    # 2. Priority: critical=0, high=1, normal=2, low=3
    # 3. Created time descending (newest first)
    priority_order = case(
        (Announcement.priority == "critical", 0),
        (Announcement.priority == "high", 1),
        (Announcement.priority == "normal", 2),
        (Announcement.priority == "low", 3),
        else_=4,
    )

    query = query.order_by(
        Announcement.is_dismissible.asc(),  # False (0) before True (1)
        priority_order.asc(),
        Announcement.created_time.desc(),
    )

    result = await session.execute(query)
    return list(result.scalars().all())


async def get_announcements(
    session: AsyncSession,
    organization_id: Optional[str],
    include_platform_wide: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Announcement], int]:
    """
    Get all announcements for an organization (admin view).

    Args:
        session: Database session
        organization_id: Organization UUID string (None for super admin)
        include_platform_wide: Whether to include platform-wide announcements
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of announcements, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        Announcement.deleted_time.is_(None),
    ]

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if include_platform_wide:
            conditions.append(
                or_(
                    Announcement.organization_id == org_uuid,
                    Announcement.organization_id.is_(None),
                )
            )
        else:
            conditions.append(Announcement.organization_id == org_uuid)
    # else: super admin with organization_id=None sees all

    base_query = select(Announcement).where(*conditions)

    # Count query
    count_query = select(func.count(Announcement.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query with ordering and pagination
    priority_order = case(
        (Announcement.priority == "critical", 0),
        (Announcement.priority == "high", 1),
        (Announcement.priority == "normal", 2),
        (Announcement.priority == "low", 3),
        else_=4,
    )

    data_query = (
        base_query.order_by(
            Announcement.organization_id.desc().nulls_last(),  # Platform-wide first
            priority_order.asc(),
            Announcement.created_time.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    announcements = result.scalars().all()

    return list(announcements), total_count


async def update_announcement(
    session: AsyncSession,
    announcement_id: str,
    organization_id: Optional[str],
    announcement_data: dict[str, Any],
) -> Optional[Announcement]:
    """
    Update an announcement.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        organization_id: Organization UUID string (None for super admin)
        announcement_data: Fields to update (all optional):
            - title, body, priority, background_color, featured_image_url,
            - cta_text, cta_url, cta_dismisses, cta_button_color, cta_button_variant,
            - is_dismissible, start_time, end_time

    Returns:
        The updated Announcement or None if not found

    Raises:
        ValueError: If trying to update an announcement from another organization
    """
    ann_uuid = UUID(announcement_id)

    result = await session.execute(
        select(Announcement).where(
            Announcement.id == ann_uuid,
            Announcement.deleted_time.is_(None),
        )
    )
    announcement = result.scalars().first()

    if not announcement:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Prevent non-super-admins from modifying platform-wide announcements
        if announcement.organization_id is None:
            return None
        # Can only update own org announcements
        if announcement.organization_id != org_uuid:
            return None
    # else: super admin can update all

    # Update allowed fields
    updatable_fields = [
        "title",
        "body",
        "priority",
        "background_color",
        "text_color",
        "featured_image_url",
        "cta_text",
        "cta_url",
        "cta_dismisses",
        "cta_button_color",
        "cta_button_variant",
        "is_dismissible",
        "start_time",
        "end_time",
    ]
    for field in updatable_fields:
        if field in announcement_data:
            setattr(announcement, field, announcement_data[field])

    try:
        await session.commit()
        await session.refresh(announcement)
    except Exception as e:
        await session.rollback()
        raise e

    return announcement


async def soft_delete_announcement(
    session: AsyncSession,
    announcement_id: str,
    organization_id: Optional[str],
) -> Optional[Announcement]:
    """
    Soft delete an announcement.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The deleted Announcement or None if not found

    Raises:
        ValueError: If trying to delete an announcement from another organization
    """
    ann_uuid = UUID(announcement_id)

    result = await session.execute(
        select(Announcement).where(
            Announcement.id == ann_uuid,
            Announcement.deleted_time.is_(None),
        )
    )
    announcement = result.scalars().first()

    if not announcement:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        # Prevent non-super-admins from deleting platform-wide announcements
        if announcement.organization_id is None:
            return None
        # Can only delete own org announcements
        if announcement.organization_id != org_uuid:
            return None
    # else: super admin can delete all

    announcement.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(announcement)
    except Exception as e:
        await session.rollback()
        raise e

    return announcement
