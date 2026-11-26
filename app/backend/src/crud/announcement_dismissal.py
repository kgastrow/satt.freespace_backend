"""
CRUD operations for AnnouncementDismissal model.

Tracks user-specific dismissal of announcements.
Each user can dismiss each announcement once (enforced by unique constraint).
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.announcement_dismissal import AnnouncementDismissal


async def create_dismissal(
    session: AsyncSession,
    announcement_id: str,
    user_id: str,
) -> AnnouncementDismissal:
    """
    Create a dismissal record for a user and announcement.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        user_id: User UUID string

    Returns:
        The created AnnouncementDismissal

    Raises:
        Exception: If user has already dismissed this announcement (unique constraint)
    """
    ann_uuid = UUID(announcement_id)
    user_uuid = UUID(user_id)

    # Check if dismissal already exists
    existing = await is_dismissed(session, announcement_id, user_id)
    if existing:
        raise ValueError(
            f"User {user_id} has already dismissed announcement {announcement_id}"
        )

    dismissal = AnnouncementDismissal(
        announcement_id=ann_uuid,
        user_id=user_uuid,
    )

    session.add(dismissal)
    try:
        await session.commit()
        await session.refresh(dismissal)
    except Exception as e:
        await session.rollback()
        raise e

    return dismissal


async def get_user_dismissals(
    session: AsyncSession,
    user_id: str,
) -> set[str]:
    """
    Get all announcement IDs dismissed by a user.

    Args:
        session: Database session
        user_id: User UUID string

    Returns:
        Set of announcement UUID strings dismissed by the user
    """
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(AnnouncementDismissal.announcement_id).where(
            AnnouncementDismissal.user_id == user_uuid
        )
    )

    announcement_ids = result.scalars().all()
    return {str(ann_id) for ann_id in announcement_ids}


async def is_dismissed(
    session: AsyncSession,
    announcement_id: str,
    user_id: str,
) -> bool:
    """
    Check if a specific announcement is dismissed by a user.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        user_id: User UUID string

    Returns:
        True if the announcement is dismissed by the user, False otherwise
    """
    ann_uuid = UUID(announcement_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == ann_uuid,
            AnnouncementDismissal.user_id == user_uuid,
        )
    )

    dismissal = result.scalars().first()
    return dismissal is not None


async def get_dismissal_by_ids(
    session: AsyncSession,
    announcement_id: str,
    user_id: str,
) -> Optional[AnnouncementDismissal]:
    """
    Get a specific dismissal record.

    Args:
        session: Database session
        announcement_id: Announcement UUID string
        user_id: User UUID string

    Returns:
        The AnnouncementDismissal or None if not found
    """
    ann_uuid = UUID(announcement_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == ann_uuid,
            AnnouncementDismissal.user_id == user_uuid,
        )
    )

    return result.scalars().first()


async def get_dismissals_for_announcement(
    session: AsyncSession,
    announcement_id: str,
) -> list[AnnouncementDismissal]:
    """
    Get all dismissals for a specific announcement.

    Useful for analytics or understanding how many users dismissed an announcement.

    Args:
        session: Database session
        announcement_id: Announcement UUID string

    Returns:
        List of AnnouncementDismissal records
    """
    ann_uuid = UUID(announcement_id)

    result = await session.execute(
        select(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == ann_uuid
        )
    )

    return list(result.scalars().all())
