"""
CRUD operations for Changelog and ChangelogView models.

Changelogs support mixed scope:
- organization_id=None: Platform-wide entries (super admin only)
- organization_id=UUID: Organization-specific entries
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.changelog import Changelog
from src.models.changelog_view import ChangelogView


async def create_changelog(
    session: AsyncSession,
    changelog_data: dict[str, Any],
    organization_id: Optional[str],
    created_by_id: str,
) -> Changelog:
    """Create a changelog entry."""
    org_uuid = UUID(organization_id) if organization_id else None
    creator_uuid = UUID(created_by_id)

    changelog = Changelog(
        organization_id=org_uuid,
        version=changelog_data["version"],
        title=changelog_data["title"],
        body=changelog_data["body"],
        category=changelog_data.get("category", "other"),
        release_date=changelog_data["release_date"],
        is_published=changelog_data.get("is_published", False),
        created_by_id=creator_uuid,
    )

    session.add(changelog)
    try:
        await session.commit()
        await session.refresh(changelog)
    except Exception as e:
        await session.rollback()
        raise e

    return changelog


async def get_changelog_by_id(
    session: AsyncSession,
    changelog_id: str,
    organization_id: Optional[str],
) -> Optional[Changelog]:
    """Get changelog by ID within organization context."""
    cl_uuid = UUID(changelog_id)

    conditions: list[ColumnElement[bool]] = [
        Changelog.id == cl_uuid,
        Changelog.deleted_time.is_(None),
    ]

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        conditions.append(
            or_(
                Changelog.organization_id == org_uuid,
                Changelog.organization_id.is_(None),
            )
        )

    result = await session.execute(select(Changelog).where(*conditions))
    return result.scalars().first()


async def list_changelogs(
    session: AsyncSession,
    organization_id: Optional[str],
    published_only: bool = False,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Changelog], int]:
    """
    List changelogs with pagination.
    If published_only=True, only returns published entries (user view).
    """
    conditions: list[ColumnElement[bool]] = [
        Changelog.deleted_time.is_(None),
    ]

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        conditions.append(
            or_(
                Changelog.organization_id == org_uuid,
                Changelog.organization_id.is_(None),
            )
        )

    if published_only:
        conditions.append(Changelog.is_published.is_(True))

    if category:
        conditions.append(Changelog.category == category)

    # Count
    count_query = select(func.count(Changelog.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total = count_result.scalar() or 0

    # Data
    data_query = (
        select(Changelog)
        .where(*conditions)
        .order_by(Changelog.release_date.desc(), Changelog.created_time.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    changelogs = list(result.scalars().all())

    return changelogs, total


async def update_changelog(
    session: AsyncSession,
    changelog_id: str,
    organization_id: Optional[str],
    changelog_data: dict[str, Any],
) -> Optional[Changelog]:
    """Update a changelog entry."""
    cl_uuid = UUID(changelog_id)

    result = await session.execute(
        select(Changelog).where(
            Changelog.id == cl_uuid,
            Changelog.deleted_time.is_(None),
        )
    )
    changelog = result.scalars().first()

    if not changelog:
        return None

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if changelog.organization_id is None:
            return None
        if changelog.organization_id != org_uuid:
            return None

    updatable_fields = [
        "version",
        "title",
        "body",
        "category",
        "release_date",
        "is_published",
    ]
    for field in updatable_fields:
        if field in changelog_data:
            setattr(changelog, field, changelog_data[field])

    try:
        await session.commit()
        await session.refresh(changelog)
    except Exception as e:
        await session.rollback()
        raise e

    return changelog


async def soft_delete_changelog(
    session: AsyncSession,
    changelog_id: str,
    organization_id: Optional[str],
) -> Optional[Changelog]:
    """Soft delete a changelog entry."""
    cl_uuid = UUID(changelog_id)

    result = await session.execute(
        select(Changelog).where(
            Changelog.id == cl_uuid,
            Changelog.deleted_time.is_(None),
        )
    )
    changelog = result.scalars().first()

    if not changelog:
        return None

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if changelog.organization_id is None:
            return None
        if changelog.organization_id != org_uuid:
            return None

    changelog.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(changelog)
    except Exception as e:
        await session.rollback()
        raise e

    return changelog


async def get_viewed_changelog_ids(
    session: AsyncSession,
    user_id: str,
) -> set[str]:
    """Get set of changelog IDs viewed by a user."""
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(ChangelogView.changelog_id).where(
            ChangelogView.user_id == user_uuid,
            ChangelogView.deleted_time.is_(None),
        )
    )
    return {str(row) for row in result.scalars().all()}


async def get_unread_count(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> int:
    """Count published changelog entries not viewed by user."""
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    viewed_subquery = (
        select(ChangelogView.changelog_id)
        .where(
            ChangelogView.user_id == user_uuid,
            ChangelogView.deleted_time.is_(None),
        )
        .scalar_subquery()
    )

    count_query = select(func.count(Changelog.id)).where(
        Changelog.deleted_time.is_(None),
        Changelog.is_published.is_(True),
        or_(
            Changelog.organization_id == org_uuid,
            Changelog.organization_id.is_(None),
        ),
        Changelog.id.notin_(viewed_subquery),
    )

    result = await session.execute(count_query)
    return result.scalar() or 0


async def mark_as_viewed(
    session: AsyncSession,
    changelog_id: str,
    user_id: str,
) -> ChangelogView:
    """Mark a changelog entry as viewed by a user (upsert)."""
    cl_uuid = UUID(changelog_id)
    user_uuid = UUID(user_id)

    # Check if already viewed
    existing = await session.execute(
        select(ChangelogView).where(
            ChangelogView.changelog_id == cl_uuid,
            ChangelogView.user_id == user_uuid,
            ChangelogView.deleted_time.is_(None),
        )
    )
    view = existing.scalars().first()
    if view:
        return view

    view = ChangelogView(
        changelog_id=cl_uuid,
        user_id=user_uuid,
    )
    session.add(view)
    try:
        await session.commit()
        await session.refresh(view)
    except Exception as e:
        await session.rollback()
        raise e

    return view


async def mark_all_as_viewed(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> int:
    """Mark all published changelog entries as viewed for a user. Returns count marked."""
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    viewed_subquery = (
        select(ChangelogView.changelog_id)
        .where(
            ChangelogView.user_id == user_uuid,
            ChangelogView.deleted_time.is_(None),
        )
        .scalar_subquery()
    )

    unread_query = select(Changelog.id).where(
        Changelog.deleted_time.is_(None),
        Changelog.is_published.is_(True),
        or_(
            Changelog.organization_id == org_uuid,
            Changelog.organization_id.is_(None),
        ),
        Changelog.id.notin_(viewed_subquery),
    )

    result = await session.execute(unread_query)
    unread_ids = list(result.scalars().all())

    for cl_id in unread_ids:
        view = ChangelogView(
            changelog_id=cl_id,
            user_id=user_uuid,
        )
        session.add(view)

    try:
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise e

    return len(unread_ids)
