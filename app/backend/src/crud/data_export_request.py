from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.models.data_export_request import DataExportRequest, ExportStatus


async def create_data_export_request(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> DataExportRequest:
    """
    Create a new data export request for a user.

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation

    Returns:
        Created DataExportRequest
    """
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    export_request = DataExportRequest(
        user_id=user_uuid,
        organization_id=org_uuid,
        status=ExportStatus.PENDING,
    )

    session.add(export_request)
    await session.commit()
    await session.refresh(export_request)

    return export_request


async def get_user_export_requests(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[DataExportRequest], int]:
    """
    Get all export requests for a user with pagination.

    Args:
        session: Database session
        user_id: User ID
        organization_id: Organization ID for tenant isolation
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (export requests, total count)
    """
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)

    conditions: list[ColumnElement[bool]] = [
        DataExportRequest.user_id == user_uuid,
        DataExportRequest.organization_id == org_uuid,
        DataExportRequest.deleted_time.is_(None),
    ]

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(DataExportRequest).where(*conditions)
    )
    total = count_result.scalar() or 0

    # Data query - order by created_time descending (newest first)
    result = await session.execute(
        select(DataExportRequest)
        .where(*conditions)
        .order_by(DataExportRequest.created_time.desc())
        .limit(limit)
        .offset(offset)
    )
    export_requests = result.scalars().all()

    return list(export_requests), total


async def get_export_request_by_id(
    session: AsyncSession,
    export_request_id: str,
    organization_id: str,
) -> DataExportRequest | None:
    """
    Get a single export request by ID with organization isolation.

    Args:
        session: Database session
        export_request_id: Export request ID
        organization_id: Organization ID for tenant isolation

    Returns:
        DataExportRequest if found, None otherwise
    """
    request_uuid = UUID(export_request_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(DataExportRequest).where(
            DataExportRequest.id == request_uuid,
            DataExportRequest.organization_id == org_uuid,
            DataExportRequest.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def update_export_request_status(
    session: AsyncSession,
    export_request_id: str,
    status: ExportStatus,
    file_path: str | None = None,
    file_size_bytes: int | None = None,
    expires_at: datetime | None = None,
) -> DataExportRequest:
    """
    Update the status of an export request.

    Args:
        session: Database session
        export_request_id: Export request ID
        status: New status
        file_path: Optional S3 file path (for completed exports)
        file_size_bytes: Optional file size (for completed exports)
        expires_at: Optional expiration timestamp (for completed exports)

    Returns:
        Updated DataExportRequest

    Raises:
        ValueError: If export request not found
    """
    request_uuid = UUID(export_request_id)

    result = await session.execute(
        select(DataExportRequest).where(
            DataExportRequest.id == request_uuid,
            DataExportRequest.deleted_time.is_(None),
        )
    )
    export_request = result.scalars().first()

    if not export_request:
        raise ValueError(f"Export request {export_request_id} not found")

    export_request.status = status

    if status == ExportStatus.COMPLETED:
        export_request.completed_at = datetime.now(timezone.utc)
        if file_path:
            export_request.file_path = file_path
        if file_size_bytes is not None:
            export_request.file_size_bytes = file_size_bytes
        if expires_at:
            export_request.expires_at = expires_at

    await session.commit()
    await session.refresh(export_request)

    return export_request


async def increment_download_count(
    session: AsyncSession,
    export_request_id: str,
    organization_id: str,
) -> DataExportRequest:
    """
    Increment the download count for an export request.

    Args:
        session: Database session
        export_request_id: Export request ID
        organization_id: Organization ID for tenant isolation

    Returns:
        Updated DataExportRequest

    Raises:
        ValueError: If export request not found
    """
    request_uuid = UUID(export_request_id)
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(DataExportRequest).where(
            DataExportRequest.id == request_uuid,
            DataExportRequest.organization_id == org_uuid,
            DataExportRequest.deleted_time.is_(None),
        )
    )
    export_request = result.scalars().first()

    if not export_request:
        raise ValueError(f"Export request {export_request_id} not found")

    export_request.download_count += 1

    await session.commit()
    await session.refresh(export_request)

    return export_request


async def get_expired_export_requests(
    session: AsyncSession,
    cutoff_time: datetime,
) -> list[DataExportRequest]:
    """
    Get all export requests that have expired (for background cleanup).
    This function does NOT filter by organization_id as it's used by background workers.

    Args:
        session: Database session
        cutoff_time: Expiration cutoff time

    Returns:
        List of expired export requests
    """
    result = await session.execute(
        select(DataExportRequest).where(
            DataExportRequest.expires_at < cutoff_time,
            DataExportRequest.status == ExportStatus.COMPLETED,
            DataExportRequest.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def mark_export_as_expired(
    session: AsyncSession,
    export_request_id: str,
) -> DataExportRequest:
    """
    Mark an export request as expired.

    Args:
        session: Database session
        export_request_id: Export request ID

    Returns:
        Updated DataExportRequest

    Raises:
        ValueError: If export request not found
    """
    request_uuid = UUID(export_request_id)

    result = await session.execute(
        select(DataExportRequest).where(
            DataExportRequest.id == request_uuid,
            DataExportRequest.deleted_time.is_(None),
        )
    )
    export_request = result.scalars().first()

    if not export_request:
        raise ValueError(f"Export request {export_request_id} not found")

    export_request.status = ExportStatus.EXPIRED

    await session.commit()
    await session.refresh(export_request)

    return export_request
