"""
CRUD operations for BulkNotification model.

Bulk notifications track batch notification jobs for sending to many recipients.
All functions filter by organization_id for multi-tenancy isolation.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.bulk_notification import BulkNotification


async def create_bulk_notification(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    data: dict[str, Any],
) -> BulkNotification:
    """
    Create a bulk notification job.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        user_id: User UUID string (the creator of the bulk notification)
        data: Bulk notification data including:
            - name: Name/title of the bulk notification (required)
            - channel: Channel type ('email', 'sms', 'whatsapp', 'in_app') (required)
            - total_recipients: Total number of recipients (required)
            - template_id: Template UUID (optional)
            - subject: Email subject if not using template (optional)
            - body_text: Text body if not using template (optional)
            - body_html: HTML body for email if not using template (optional)
            - scheduled_time: When to send (optional, None = immediate)
            - status: Initial status (default: 'pending')
            - extra_data: JSON side-car read back by bulk_processor (optional):
                recipient_filters, template_code, category_code, is_urgent

    Returns:
        The created BulkNotification instance
    """
    org_uuid = UUID(organization_id) if organization_id else None
    creator_uuid = UUID(user_id)
    template_uuid = UUID(data.get("template_id")) if data.get("template_id") else None

    bulk_notification = BulkNotification(
        organization_id=org_uuid,
        created_by_user_id=creator_uuid,
        name=data["name"],
        channel=data["channel"],
        template_id=template_uuid,
        subject=data.get("subject"),
        body_text=data.get("body_text"),
        body_html=data.get("body_html"),
        total_recipients=data["total_recipients"],
        status=data.get("status", "pending"),
        scheduled_time=data.get("scheduled_time"),
        # The caller's recipient filters, category and urgency live here, and
        # this is where bulk_processor reads them back from. Dropping it
        # silently - as this did - meant the processor found no filters and
        # fell through to its "every user in the org" default: a send the
        # admin had narrowed to one segment went to the whole tenant, and the
        # run still reported success.
        extra_data=data.get("extra_data"),
    )

    session.add(bulk_notification)
    try:
        await session.commit()
        await session.refresh(bulk_notification)
    except Exception as e:
        await session.rollback()
        raise e

    return bulk_notification


async def get_bulk_notification(
    session: AsyncSession,
    bulk_id: str,
    organization_id: str,
) -> Optional[BulkNotification]:
    """
    Get a bulk notification by ID within organization context.

    Args:
        session: Database session
        bulk_id: Bulk notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)

    Returns:
        The BulkNotification or None if not found
    """
    org_uuid = UUID(organization_id)
    bulk_uuid = UUID(bulk_id)

    result = await session.execute(
        select(BulkNotification).where(
            BulkNotification.id == bulk_uuid,
            BulkNotification.organization_id == org_uuid,
            BulkNotification.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def update_bulk_progress(
    session: AsyncSession,
    bulk_id: str,
    sent_count: int,
    failed_count: int,
    status: Optional[str] = None,
) -> Optional[BulkNotification]:
    """
    Update bulk notification progress counts.

    This function does NOT require organization_id since it's called by background
    workers that already have the bulk_id. The bulk notification itself contains
    the organization_id for audit purposes.

    Args:
        session: Database session
        bulk_id: Bulk notification UUID string
        sent_count: Number of successfully sent notifications
        failed_count: Number of failed notifications
        status: New status (optional) - 'pending', 'processing', 'completed', 'failed', 'cancelled'

    Returns:
        The updated BulkNotification or None if not found
    """
    bulk_uuid = UUID(bulk_id)

    result = await session.execute(
        select(BulkNotification).where(
            BulkNotification.id == bulk_uuid,
            BulkNotification.deleted_time.is_(None),
        )
    )
    bulk_notification = result.scalars().first()

    if not bulk_notification:
        return None

    # Update progress counts
    bulk_notification.sent_count = sent_count
    bulk_notification.failed_count = failed_count

    # Update status if provided
    if status:
        bulk_notification.status = status

        # Set timestamps based on status
        if status == "processing" and bulk_notification.started_time is None:
            bulk_notification.started_time = datetime.now(timezone.utc)
        elif status in ("completed", "failed", "cancelled"):
            bulk_notification.completed_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(bulk_notification)
    except Exception as e:
        await session.rollback()
        raise e

    return bulk_notification


async def get_bulk_notifications(
    session: AsyncSession,
    organization_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[BulkNotification], int]:
    """
    Get bulk notifications for an organization with optional status filter.

    Args:
        session: Database session
        organization_id: Organization UUID string (required for tenant isolation)
        status: Filter by status (optional) - 'pending', 'processing', 'completed', 'failed', 'cancelled'
        limit: Maximum number of results (default: 50)
        offset: Number of results to skip (default: 0)

    Returns:
        Tuple of (list of bulk notifications, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with organization filter
    conditions = [
        BulkNotification.organization_id == org_uuid,
        BulkNotification.deleted_time.is_(None),
    ]

    # Apply optional status filter
    if status:
        conditions.append(BulkNotification.status == status)

    base_query = select(BulkNotification).where(*conditions)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar()

    # Data query with ordering and pagination
    data_query = (
        base_query.order_by(BulkNotification.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(data_query)
    bulk_notifications = result.scalars().all()

    return list(bulk_notifications), total_count or 0


async def cancel_bulk_notification(
    session: AsyncSession,
    bulk_id: str,
    organization_id: str,
) -> Optional[BulkNotification]:
    """
    Cancel a pending or processing bulk notification.

    Args:
        session: Database session
        bulk_id: Bulk notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)

    Returns:
        The cancelled BulkNotification or None if not found

    Raises:
        ValueError: If the bulk notification cannot be cancelled (already completed/failed)
    """
    org_uuid = UUID(organization_id)
    bulk_uuid = UUID(bulk_id)

    result = await session.execute(
        select(BulkNotification).where(
            BulkNotification.id == bulk_uuid,
            BulkNotification.organization_id == org_uuid,
            BulkNotification.deleted_time.is_(None),
        )
    )
    bulk_notification = result.scalars().first()

    if not bulk_notification:
        return None

    # Check if can be cancelled
    if bulk_notification.status in ("completed", "failed", "cancelled"):
        raise ValueError(
            f"Cannot cancel bulk notification with status '{bulk_notification.status}'"
        )

    bulk_notification.status = "cancelled"
    bulk_notification.completed_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(bulk_notification)
    except Exception as e:
        await session.rollback()
        raise e

    return bulk_notification


async def get_pending_bulk_notifications(
    session: AsyncSession,
    limit: int = 100,
) -> list[BulkNotification]:
    """
    Get pending bulk notifications ready for processing (worker function).

    This function does NOT require organization_id since it's used by
    background workers to process bulk notifications from all organizations.

    Args:
        session: Database session
        limit: Maximum number of results

    Returns:
        List of pending bulk notifications ordered by creation time
    """
    now = datetime.now(timezone.utc)

    result = await session.execute(
        select(BulkNotification)
        .where(
            BulkNotification.status == "pending",
            BulkNotification.deleted_time.is_(None),
            # Either no scheduled time (immediate) or scheduled time has passed
            (BulkNotification.scheduled_time.is_(None))
            | (BulkNotification.scheduled_time <= now),
        )
        .order_by(BulkNotification.created_time.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def soft_delete_bulk_notification(
    session: AsyncSession,
    bulk_id: str,
    organization_id: str,
) -> Optional[BulkNotification]:
    """
    Soft delete a bulk notification by setting deleted_time.

    Args:
        session: Database session
        bulk_id: Bulk notification UUID string
        organization_id: Organization UUID string (required for tenant isolation)

    Returns:
        The deleted BulkNotification or None if not found
    """
    org_uuid = UUID(organization_id)
    bulk_uuid = UUID(bulk_id)

    result = await session.execute(
        select(BulkNotification).where(
            BulkNotification.id == bulk_uuid,
            BulkNotification.organization_id == org_uuid,
            BulkNotification.deleted_time.is_(None),
        )
    )
    bulk_notification = result.scalars().first()

    if not bulk_notification:
        return None

    bulk_notification.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(bulk_notification)
    except Exception as e:
        await session.rollback()
        raise e

    return bulk_notification
