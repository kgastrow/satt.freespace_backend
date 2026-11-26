"""
CRUD operations for file usage tracking.

All functions filter by organization_id for multi-tenancy isolation.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.file_usage import FileUsage


async def get_or_create_usage(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
) -> FileUsage:
    """
    Get existing usage record or create a new one.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string

    Returns:
        The FileUsage record (existing or newly created)
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Try to get existing record
    result = await session.execute(
        select(FileUsage).where(
            FileUsage.organization_id == org_uuid,
            FileUsage.user_id == user_uuid,
        )
    )
    usage = result.scalars().first()

    if usage:
        return usage

    # Create new usage record with default values
    usage = FileUsage(
        organization_id=org_uuid,
        user_id=user_uuid,
        total_files=0,
        total_size_bytes=0,
        image_count=0,
        image_size_bytes=0,
        video_count=0,
        video_size_bytes=0,
        document_count=0,
        document_size_bytes=0,
        other_count=0,
        other_size_bytes=0,
    )

    session.add(usage)
    try:
        await session.commit()
        await session.refresh(usage)
    except Exception as e:
        await session.rollback()
        raise e

    return usage


async def update_usage_on_upload(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    size_bytes: int,
    category: Optional[str] = None,
) -> FileUsage:
    """
    Increment usage stats when a file is uploaded.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string
        size_bytes: Size of the uploaded file in bytes
        category: File category ('image', 'video', 'document', 'other')

    Returns:
        The updated FileUsage record
    """
    usage = await get_or_create_usage(session, organization_id, user_id)

    # Increment total counts
    usage.total_files = (usage.total_files or 0) + 1
    usage.total_size_bytes = (usage.total_size_bytes or 0) + size_bytes

    # Increment category-specific counts
    if category == "image":
        usage.image_count = (usage.image_count or 0) + 1
        usage.image_size_bytes = (usage.image_size_bytes or 0) + size_bytes
    elif category == "video":
        usage.video_count = (usage.video_count or 0) + 1
        usage.video_size_bytes = (usage.video_size_bytes or 0) + size_bytes
    elif category == "document":
        usage.document_count = (usage.document_count or 0) + 1
        usage.document_size_bytes = (usage.document_size_bytes or 0) + size_bytes
    else:
        # Default to 'other' for unknown categories
        usage.other_count = (usage.other_count or 0) + 1
        usage.other_size_bytes = (usage.other_size_bytes or 0) + size_bytes

    try:
        await session.commit()
        await session.refresh(usage)
    except Exception as e:
        await session.rollback()
        raise e

    return usage


async def update_usage_on_delete(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    size_bytes: int,
    category: Optional[str] = None,
) -> FileUsage:
    """
    Decrement usage stats when a file is deleted.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string
        size_bytes: Size of the deleted file in bytes
        category: File category ('image', 'video', 'document', 'other')

    Returns:
        The updated FileUsage record
    """
    usage = await get_or_create_usage(session, organization_id, user_id)

    # Decrement total counts (ensure non-negative)
    usage.total_files = max(0, (usage.total_files or 0) - 1)
    usage.total_size_bytes = max(0, (usage.total_size_bytes or 0) - size_bytes)

    # Decrement category-specific counts (ensure non-negative)
    if category == "image":
        usage.image_count = max(0, (usage.image_count or 0) - 1)
        usage.image_size_bytes = max(0, (usage.image_size_bytes or 0) - size_bytes)
    elif category == "video":
        usage.video_count = max(0, (usage.video_count or 0) - 1)
        usage.video_size_bytes = max(0, (usage.video_size_bytes or 0) - size_bytes)
    elif category == "document":
        usage.document_count = max(0, (usage.document_count or 0) - 1)
        usage.document_size_bytes = max(
            0, (usage.document_size_bytes or 0) - size_bytes
        )
    else:
        # Default to 'other' for unknown categories
        usage.other_count = max(0, (usage.other_count or 0) - 1)
        usage.other_size_bytes = max(0, (usage.other_size_bytes or 0) - size_bytes)

    try:
        await session.commit()
        await session.refresh(usage)
    except Exception as e:
        await session.rollback()
        raise e

    return usage


async def get_user_usage(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
) -> Optional[FileUsage]:
    """
    Get usage stats for a specific user.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string

    Returns:
        The FileUsage record, or None if no usage found
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(FileUsage).where(
            FileUsage.organization_id == org_uuid,
            FileUsage.user_id == user_uuid,
        )
    )
    return result.scalars().first()


async def get_organization_usage(
    session: AsyncSession,
    organization_id: str,
) -> dict:
    """
    Get aggregate usage stats for an entire organization.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        Dictionary with aggregate usage stats:
        {
            "total_files": int,
            "total_size_bytes": int,
            "image_count": int,
            "image_size_bytes": int,
            "video_count": int,
            "video_size_bytes": int,
            "document_count": int,
            "document_size_bytes": int,
            "other_count": int,
            "other_size_bytes": int,
            "user_count": int,  # Number of users with usage records
        }
    """
    org_uuid = UUID(organization_id)

    # Aggregate all FileUsage records for the organization
    result = await session.execute(
        select(
            func.sum(FileUsage.total_files).label("total_files"),
            func.sum(FileUsage.total_size_bytes).label("total_size_bytes"),
            func.sum(FileUsage.image_count).label("image_count"),
            func.sum(FileUsage.image_size_bytes).label("image_size_bytes"),
            func.sum(FileUsage.video_count).label("video_count"),
            func.sum(FileUsage.video_size_bytes).label("video_size_bytes"),
            func.sum(FileUsage.document_count).label("document_count"),
            func.sum(FileUsage.document_size_bytes).label("document_size_bytes"),
            func.sum(FileUsage.other_count).label("other_count"),
            func.sum(FileUsage.other_size_bytes).label("other_size_bytes"),
            func.count(FileUsage.id).label("user_count"),
        ).where(FileUsage.organization_id == org_uuid)
    )
    row = result.first()

    return {
        "total_files": (row.total_files or 0) if row else 0,
        "total_size_bytes": (row.total_size_bytes or 0) if row else 0,
        "image_count": (row.image_count or 0) if row else 0,
        "image_size_bytes": (row.image_size_bytes or 0) if row else 0,
        "video_count": (row.video_count or 0) if row else 0,
        "video_size_bytes": (row.video_size_bytes or 0) if row else 0,
        "document_count": (row.document_count or 0) if row else 0,
        "document_size_bytes": (row.document_size_bytes or 0) if row else 0,
        "other_count": (row.other_count or 0) if row else 0,
        "other_size_bytes": (row.other_size_bytes or 0) if row else 0,
        "user_count": (row.user_count or 0) if row else 0,
    }


async def get_all_user_usage(
    session: AsyncSession,
    organization_id: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[FileUsage], int]:
    """
    Get usage stats for all users in an organization with pagination.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)

    Returns:
        Tuple of (list of FileUsage records, total count)
    """
    org_uuid = UUID(organization_id)

    # Count query
    count_result = await session.execute(
        select(func.count())
        .select_from(FileUsage)
        .where(FileUsage.organization_id == org_uuid)
    )
    total_count = count_result.scalar()

    # Data query with ordering and pagination
    result = await session.execute(
        select(FileUsage)
        .where(FileUsage.organization_id == org_uuid)
        .order_by(FileUsage.total_size_bytes.desc())
        .limit(limit)
        .offset(offset)
    )
    usage_records = result.scalars().all()

    return list(usage_records), total_count or 0
