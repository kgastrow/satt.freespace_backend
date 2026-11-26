from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.data_deletion_request import DataDeletionRequest, DeletionStatus


async def create_data_deletion_request(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    scheduled_hard_delete_at: datetime | None = None,
) -> DataDeletionRequest:
    """
    Create a new data deletion request for a user.

    Validates that no active deletion request already exists for the user.

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation
        scheduled_hard_delete_at: When to hard delete (defaults to 30 days from now)

    Returns:
        Created DataDeletionRequest

    Raises:
        ValueError: If an active deletion request already exists for this user
    """
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    # Check for existing active deletion request
    existing = await get_active_deletion_request(session, user_id, organization_id)
    if existing:
        raise ValueError(
            "User already has an active deletion request. "
            "Cancel the existing request before creating a new one."
        )

    # Default to 30 days from now if not provided
    if scheduled_hard_delete_at is None:
        scheduled_hard_delete_at = datetime.now(timezone.utc) + timedelta(days=30)

    deletion_request = DataDeletionRequest(
        user_id=user_uuid,
        organization_id=org_uuid,
        status=DeletionStatus.PENDING,
        scheduled_hard_delete_at=scheduled_hard_delete_at,
    )

    session.add(deletion_request)
    await session.commit()
    await session.refresh(deletion_request)

    return deletion_request


async def get_data_deletion_request(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> DataDeletionRequest | None:
    """
    Get any deletion request (active or inactive) for a user.

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation

    Returns:
        DataDeletionRequest if found, None otherwise
    """
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(DataDeletionRequest)
        .where(
            DataDeletionRequest.user_id == user_uuid,
            DataDeletionRequest.organization_id == org_uuid,
            DataDeletionRequest.deleted_time.is_(None),
        )
        .order_by(DataDeletionRequest.created_time.desc())
    )
    return result.scalars().first()


async def get_active_deletion_request(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> DataDeletionRequest | None:
    """
    Get the active deletion request for a user (pending or scheduled status).

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation

    Returns:
        Active DataDeletionRequest if found, None otherwise
    """
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(DataDeletionRequest).where(
            DataDeletionRequest.user_id == user_uuid,
            DataDeletionRequest.organization_id == org_uuid,
            DataDeletionRequest.status.in_(
                [DeletionStatus.PENDING, DeletionStatus.SCHEDULED]
            ),
            DataDeletionRequest.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def cancel_deletion_request(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    cancellation_reason: str | None = None,
) -> DataDeletionRequest:
    """
    Cancel an active deletion request for a user.

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation
        cancellation_reason: Optional reason for cancellation

    Returns:
        Updated DataDeletionRequest

    Raises:
        ValueError: If no active deletion request found or request already completed
    """
    deletion_request = await get_active_deletion_request(
        session, user_id, organization_id
    )

    if not deletion_request:
        raise ValueError("No active deletion request found for this user")

    if deletion_request.status == DeletionStatus.COMPLETED:
        raise ValueError("Cannot cancel a completed deletion request")

    deletion_request.status = DeletionStatus.CANCELLED
    deletion_request.cancelled_at = datetime.now(timezone.utc)
    if cancellation_reason:
        deletion_request.cancellation_reason = cancellation_reason

    # Soft delete cancelled requests to allow creation of new requests
    # (SQLite doesn't support partial unique indexes, so we rely on soft delete)
    deletion_request.deleted_time = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(deletion_request)

    return deletion_request


async def get_pending_hard_deletions(
    session: AsyncSession,
    cutoff_time: datetime | None = None,
) -> list[DataDeletionRequest]:
    """
    Get deletion requests that are past their 30-day window and ready for hard deletion.
    This function does NOT filter by organization_id as it's used by background workers.

    Args:
        session: Database session
        cutoff_time: Optional cutoff time (defaults to now)

    Returns:
        List of deletion requests ready for hard deletion
    """
    if cutoff_time is None:
        cutoff_time = datetime.now(timezone.utc)

    result = await session.execute(
        select(DataDeletionRequest).where(
            DataDeletionRequest.scheduled_hard_delete_at <= cutoff_time,
            DataDeletionRequest.status.in_(
                [DeletionStatus.PENDING, DeletionStatus.SCHEDULED]
            ),
            DataDeletionRequest.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def update_deletion_status(
    session: AsyncSession,
    deletion_request_id: str,
    status: DeletionStatus,
) -> DataDeletionRequest:
    """
    Update the status of a deletion request.

    Args:
        session: Database session
        deletion_request_id: Deletion request ID
        status: New status

    Returns:
        Updated DataDeletionRequest

    Raises:
        ValueError: If deletion request not found
    """
    request_uuid = UUID(deletion_request_id)

    result = await session.execute(
        select(DataDeletionRequest).where(
            DataDeletionRequest.id == request_uuid,
            DataDeletionRequest.deleted_time.is_(None),
        )
    )
    deletion_request = result.scalars().first()

    if not deletion_request:
        raise ValueError(f"Deletion request {deletion_request_id} not found")

    deletion_request.status = status

    if status == DeletionStatus.COMPLETED:
        deletion_request.hard_deleted_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(deletion_request)

    return deletion_request


async def mark_deletion_as_completed(
    session: AsyncSession,
    deletion_request_id: str,
) -> DataDeletionRequest:
    """
    Mark a deletion request as completed (hard deleted).

    Args:
        session: Database session
        deletion_request_id: Deletion request ID

    Returns:
        Updated DataDeletionRequest

    Raises:
        ValueError: If deletion request not found
    """
    return await update_deletion_status(
        session, deletion_request_id, DeletionStatus.COMPLETED
    )
