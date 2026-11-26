"""
CRUD operations for file management.

All functions filter by organization_id for multi-tenancy isolation.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.file import File


# Configuration for file DSL queries
FILE_FILTER_FIELDS = {"category", "status", "user_id"}
FILE_FIELD_MAPPING: dict[str, str] = {"user_id": "uploaded_by_user_id"}


async def create_file(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    file_data: dict,
) -> File:
    """
    Create a new file record.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string (uploader)
        file_data: Dictionary containing file metadata:
            - original_filename: str
            - storage_key: str
            - content_type: str
            - size_bytes: int
            - file_extension: str (optional)
            - storage_provider: str (default 's3')
            - bucket_name: str (optional)
            - category: str (optional) - 'document', 'image', 'video', 'other'
            - metadata: dict (optional)
            - status: str (default 'pending')

    Returns:
        The created File record
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Set defaults
    file_data.setdefault("status", "pending")
    file_data.setdefault("storage_provider", "s3")

    new_file = File(
        organization_id=org_uuid,
        uploaded_by_user_id=user_uuid,
        original_filename=file_data["original_filename"],
        storage_key=file_data["storage_key"],
        content_type=file_data["content_type"],
        size_bytes=file_data["size_bytes"],
        file_extension=file_data.get("file_extension"),
        storage_provider=file_data.get("storage_provider", "s3"),
        bucket_name=file_data.get("bucket_name"),
        category=file_data.get("category"),
        extra_data=file_data.get("extra_data"),
        status=file_data.get("status", "pending"),
        media_use=file_data.get("media_use"),
        thumbnail_storage_key=file_data.get("thumbnail_storage_key"),
    )

    session.add(new_file)
    try:
        await session.commit()
        await session.refresh(new_file)
    except Exception as e:
        await session.rollback()
        raise e

    return new_file


async def get_file_by_id(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
) -> Optional[File]:
    """
    Get a single file by ID within organization context.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string

    Returns:
        The File record or None if not found
    """
    org_uuid = UUID(organization_id)
    file_uuid = UUID(file_id)

    result = await session.execute(
        select(File).where(
            File.id == file_uuid,
            File.organization_id == org_uuid,
            File.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_files(
    session: AsyncSession,
    organization_id: str,
    user_id: Optional[str] = None,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[File], int]:
    """
    List files with DSL filtering, sorting, and pagination.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: Optional filter by uploader (forces this user filter, e.g., for user's own files)
        filters: List of FilterSpec objects for DSL filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results (default 50)
        offset: Number of results to skip (default 0)

    Returns:
        Tuple of (list of files, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with mandatory tenant isolation
    base_query = select(File).where(
        File.organization_id == org_uuid,
        File.deleted_time.is_(None),
    )

    # Apply user_id filter if provided (for user's own files endpoint)
    if user_id:
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        base_query = base_query.where(File.uploaded_by_user_id == user_uuid)

    # Apply DSL filters
    if filters:
        base_query = apply_filters(base_query, File, filters, FILE_FIELD_MAPPING)

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(base_query, File, sorts, FILE_FIELD_MAPPING)
    else:
        base_query = base_query.order_by(File.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    files = list(result.scalars().all())

    return files, total_count


async def update_file(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
    **kwargs,
) -> Optional[File]:
    """
    Update a file's fields.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string
        **kwargs: Fields to update (storage_key, bucket_name, status, etc.)

    Returns:
        The updated File record or None if not found
    """
    file = await get_file_by_id(session, file_id, organization_id)

    if not file:
        return None

    # Update only the fields that were provided
    updatable_fields = [
        "storage_key",
        "bucket_name",
        "status",
        "category",
        "content_type",
        "file_extension",
        "size_bytes",
        "extra_data",
        "media_use",
        "thumbnail_storage_key",
    ]

    for field in updatable_fields:
        if field in kwargs and kwargs[field] is not None:
            setattr(file, field, kwargs[field])

    try:
        await session.commit()
        await session.refresh(file)
    except Exception as e:
        await session.rollback()
        raise e

    return file


async def update_file_status(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
    status: str,
) -> Optional[File]:
    """
    Update the status of a file.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string
        status: New status ('pending', 'uploaded', 'processing', 'ready', 'failed', 'deleted')

    Returns:
        The updated File record or None if not found

    Raises:
        ValueError: If file not found
    """
    file = await get_file_by_id(session, file_id, organization_id)

    if not file:
        raise ValueError(f"File with id {file_id} not found")

    file.status = status

    try:
        await session.commit()
        await session.refresh(file)
    except Exception as e:
        await session.rollback()
        raise e

    return file


async def soft_delete_file(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
) -> Optional[File]:
    """
    Soft delete a file by setting deleted_time.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string

    Returns:
        The soft-deleted File record

    Raises:
        ValueError: If file not found
    """
    file = await get_file_by_id(session, file_id, organization_id)

    if not file:
        raise ValueError(f"File with id {file_id} not found")

    file.deleted_time = datetime.now(timezone.utc)
    file.status = "deleted"

    try:
        await session.commit()
        await session.refresh(file)
    except Exception as e:
        await session.rollback()
        raise e

    return file


async def increment_download_count(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
) -> Optional[File]:
    """
    Increment the download count and update last accessed time.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string

    Returns:
        The updated File record

    Raises:
        ValueError: If file not found
    """
    file = await get_file_by_id(session, file_id, organization_id)

    if not file:
        raise ValueError(f"File with id {file_id} not found")

    file.download_count = (file.download_count or 0) + 1
    file.last_accessed_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(file)
    except Exception as e:
        await session.rollback()
        raise e

    return file


async def update_file_metadata(
    session: AsyncSession,
    file_id: str,
    organization_id: str,
    metadata: dict,
) -> Optional[File]:
    """
    Update the metadata of a file.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        file_id: File UUID string
        organization_id: Organization UUID string
        metadata: New metadata dictionary

    Returns:
        The updated File record

    Raises:
        ValueError: If file not found
    """
    file = await get_file_by_id(session, file_id, organization_id)

    if not file:
        raise ValueError(f"File with id {file_id} not found")

    file.extra_data = metadata

    try:
        await session.commit()
        await session.refresh(file)
    except Exception as e:
        await session.rollback()
        raise e

    return file
