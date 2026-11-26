"""
CRUD operations for UserNotification model (in-app notifications).

All functions filter by organization_id for multi-tenancy isolation.
Additionally, user notifications are scoped to individual users.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.notification import scrub_credential_text
from src.models.user_notification import UserNotification


async def create_user_notification(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    category_id: Optional[str] = None,
) -> UserNotification:
    """
    Create an in-app notification for a user.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (recipient)
        title: Notification title (required)
        body: Notification body text (optional)
        link: Click-through link (optional)
        category_id: Notification category UUID string (optional)

    Returns:
        The created UserNotification instance
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    cat_uuid = UUID(category_id) if category_id else None

    # Scrub here rather than in the caller, because this function is the only
    # chokepoint. in_app_provider already scrubs, but api/feedback.py writes
    # rows directly and any future caller would too - a control applied per
    # caller is a control that is one new caller away from being absent.
    # Scrubbing is idempotent, so the provider's own pass is harmless.
    #
    # An in-app row outlives the credential it might carry by weeks, and it is
    # readable by the recipient AND by a super admin impersonating them (an
    # impersonation token carries the target's user_id), so it is not
    # self-only storage.
    #
    # `link` is deliberately NOT scrubbed: it is the notification's action, and
    # this row is the only copy the UI can click. Redacting a token out of it
    # produces a notification that renders correctly and does nothing. A caller
    # putting a live credential in `link` needs a one-shot-link concept, not a
    # redaction.
    notification = UserNotification(
        organization_id=org_uuid,
        user_id=user_uuid,
        title=scrub_credential_text(title),
        body=scrub_credential_text(body),
        link=link,
        category_id=cat_uuid,
    )

    session.add(notification)
    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification


async def get_user_notifications(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    unread_only: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[UserNotification], int]:
    """
    Get in-app notifications for a user with pagination.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string
        unread_only: If True, only return unread notifications
        limit: Maximum number of results (default: 20)
        offset: Number of results to skip (default: 0)

    Returns:
        Tuple of (list of notifications, total count)
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    conditions: list[ColumnElement[bool]] = [
        UserNotification.organization_id == org_uuid,
        UserNotification.user_id == user_uuid,
        UserNotification.deleted_time.is_(None),
    ]

    if unread_only:
        conditions.append(UserNotification.read_time.is_(None))

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(UserNotification).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query with ordering by created_time descending (newest first)
    result = await session.execute(
        select(UserNotification)
        .where(*conditions)
        .order_by(UserNotification.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    notifications = result.scalars().all()

    return list(notifications), total


async def get_unread_count(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
) -> int:
    """
    Get count of unread in-app notifications for a user.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string

    Returns:
        Count of unread notifications
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(func.count())
        .select_from(UserNotification)
        .where(
            UserNotification.organization_id == org_uuid,
            UserNotification.user_id == user_uuid,
            UserNotification.read_time.is_(None),
            UserNotification.deleted_time.is_(None),
        )
    )
    return result.scalar() or 0


async def get_user_notification_by_id(
    session: AsyncSession,
    notification_id: str,
    organization_id: str,
    user_id: str,
) -> Optional[UserNotification]:
    """
    Get a single in-app notification by ID.

    Args:
        session: Database session
        notification_id: Notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (required to verify ownership)

    Returns:
        The UserNotification or None if not found
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    notif_uuid = UUID(notification_id)

    result = await session.execute(
        select(UserNotification).where(
            UserNotification.id == notif_uuid,
            UserNotification.organization_id == org_uuid,
            UserNotification.user_id == user_uuid,
            UserNotification.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def mark_as_read(
    session: AsyncSession,
    notification_id: str,
    organization_id: str,
    user_id: str,
) -> Optional[UserNotification]:
    """
    Mark a single notification as read.

    Args:
        session: Database session
        notification_id: Notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (required to verify ownership)

    Returns:
        The updated UserNotification or None if not found
    """
    notification = await get_user_notification_by_id(
        session, notification_id, organization_id, user_id
    )

    if not notification:
        return None

    # Only update if not already read
    if notification.read_time is None:
        notification.read_time = datetime.now(timezone.utc)
        try:
            await session.commit()
            await session.refresh(notification)
        except Exception as e:
            await session.rollback()
            raise e

    return notification


async def mark_all_as_read(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
) -> int:
    """
    Mark all unread notifications as read for a user.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string

    Returns:
        Number of notifications marked as read
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    now = datetime.now(timezone.utc)

    # Get all unread notifications for this user
    result = await session.execute(
        select(UserNotification).where(
            UserNotification.organization_id == org_uuid,
            UserNotification.user_id == user_uuid,
            UserNotification.read_time.is_(None),
            UserNotification.deleted_time.is_(None),
        )
    )
    notifications = result.scalars().all()

    count = 0
    for notification in notifications:
        notification.read_time = now
        count += 1

    if count > 0:
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e

    return count


async def bulk_dismiss(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    notification_ids: list[str],
) -> int:
    """
    Soft delete multiple notifications (dismiss/archive).

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (required to verify ownership)
        notification_ids: List of notification UUID strings to dismiss

    Returns:
        Number of notifications dismissed
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    now = datetime.now(timezone.utc)

    # Convert string IDs to UUIDs
    notif_uuids = [UUID(nid) for nid in notification_ids]

    # Get notifications that belong to this user in this organization
    result = await session.execute(
        select(UserNotification).where(
            UserNotification.id.in_(notif_uuids),
            UserNotification.organization_id == org_uuid,
            UserNotification.user_id == user_uuid,
            UserNotification.deleted_time.is_(None),
        )
    )
    notifications = result.scalars().all()

    count = 0
    for notification in notifications:
        notification.deleted_time = now
        count += 1

    if count > 0:
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e

    return count


async def soft_delete_user_notification(
    session: AsyncSession,
    notification_id: str,
    organization_id: str,
    user_id: str,
) -> Optional[UserNotification]:
    """
    Soft delete a single notification.

    Args:
        session: Database session
        notification_id: Notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (required to verify ownership)

    Returns:
        The deleted UserNotification or None if not found
    """
    notification = await get_user_notification_by_id(
        session, notification_id, organization_id, user_id
    )

    if not notification:
        return None

    notification.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(notification)
    except Exception as e:
        await session.rollback()
        raise e

    return notification
