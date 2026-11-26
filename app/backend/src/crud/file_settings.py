"""
CRUD operations for organization file settings.

All functions filter by organization_id for multi-tenancy isolation.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.organization_file_settings import OrganizationFileSettings


# Default allowed extensions
DEFAULT_ALLOWED_EXTENSIONS = [
    # Images
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    # Documents
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    # Videos
    "mp4",
    "mov",
    "avi",
    "webm",
    # Audio
    "mp3",
    "wav",
    # Other
    "zip",
    "txt",
    "csv",
]


async def get_file_settings(
    session: AsyncSession,
    organization_id: str,
) -> OrganizationFileSettings:
    """
    Get file settings for an organization. Creates default settings if not exists.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationFileSettings record (existing or newly created with defaults)
    """
    org_uuid = UUID(organization_id)

    # Try to get existing settings
    result = await session.execute(
        select(OrganizationFileSettings).where(
            OrganizationFileSettings.organization_id == org_uuid
        )
    )
    settings = result.scalars().first()

    if settings:
        return settings

    # Create default settings for the organization
    settings = OrganizationFileSettings(
        organization_id=org_uuid,
        max_file_size_bytes=104857600,  # 100MB default
        max_video_size_bytes=104857600,  # 100MB for videos
        allowed_extensions=DEFAULT_ALLOWED_EXTENSIONS,
        user_storage_quota_bytes=None,  # Unlimited by default
        org_storage_quota_bytes=None,  # Unlimited by default
        signed_url_expiry_seconds=3600,  # 1 hour
        deleted_file_retention_days=30,  # Keep deleted files for 30 days
    )

    session.add(settings)
    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings


async def update_file_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict,
) -> OrganizationFileSettings:
    """
    Update file settings for an organization.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Dictionary with settings to update. Allowed keys:
            - max_file_size_bytes: int
            - max_video_size_bytes: int
            - allowed_extensions: List[str]
            - user_storage_quota_bytes: int or None
            - org_storage_quota_bytes: int or None
            - signed_url_expiry_seconds: int
            - deleted_file_retention_days: int

    Returns:
        The updated OrganizationFileSettings record
    """
    # Get or create settings first
    settings = await get_file_settings(session, organization_id)

    # List of allowed fields that can be updated
    allowed_fields = [
        "max_file_size_bytes",
        "max_video_size_bytes",
        "allowed_extensions",
        "user_storage_quota_bytes",
        "org_storage_quota_bytes",
        "signed_url_expiry_seconds",
        "deleted_file_retention_days",
    ]

    # Update only allowed fields
    for field in allowed_fields:
        if field in settings_data:
            setattr(settings, field, settings_data[field])

    try:
        await session.commit()
        await session.refresh(settings)
    except Exception as e:
        await session.rollback()
        raise e

    return settings


async def get_file_settings_by_id(
    session: AsyncSession,
    settings_id: str,
    organization_id: str,
) -> Optional[OrganizationFileSettings]:
    """
    Get file settings by ID within organization context.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        settings_id: Settings UUID string
        organization_id: Organization UUID string

    Returns:
        The OrganizationFileSettings record or None if not found
    """
    org_uuid = UUID(organization_id)
    settings_uuid = UUID(settings_id)

    result = await session.execute(
        select(OrganizationFileSettings).where(
            OrganizationFileSettings.id == settings_uuid,
            OrganizationFileSettings.organization_id == org_uuid,
        )
    )
    return result.scalars().first()


async def check_file_allowed(
    session: AsyncSession,
    organization_id: str,
    file_extension: str,
    file_size_bytes: int,
    is_video: bool = False,
) -> tuple[bool, Optional[str]]:
    """
    Check if a file upload is allowed based on organization settings.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        file_extension: File extension (without dot)
        file_size_bytes: File size in bytes
        is_video: Whether the file is a video

    Returns:
        Tuple of (is_allowed: bool, error_message: str or None)
    """
    settings = await get_file_settings(session, organization_id)

    # Normalize extension (lowercase, no dot)
    ext = file_extension.lower().lstrip(".")

    # Check allowed extensions
    if ext not in settings.allowed_extensions:
        return False, f"File type '.{ext}' is not allowed"

    # Check file size
    if is_video:
        max_size = settings.max_video_size_bytes
        if file_size_bytes > max_size:
            max_mb = max_size / (1024 * 1024)
            return False, f"Video file exceeds maximum size of {max_mb:.0f}MB"
    else:
        max_size = settings.max_file_size_bytes
        if file_size_bytes > max_size:
            max_mb = max_size / (1024 * 1024)
            return False, f"File exceeds maximum size of {max_mb:.0f}MB"

    return True, None


async def check_quota(
    session: AsyncSession,
    organization_id: str,
    user_id: str,
    additional_bytes: int,
) -> tuple[bool, Optional[str]]:
    """
    Check if user/organization has quota for additional file storage.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        user_id: User UUID string
        additional_bytes: Additional bytes to be uploaded

    Returns:
        Tuple of (is_allowed: bool, error_message: str or None)
    """
    from src.crud.file_usage import get_organization_usage, get_user_usage

    settings = await get_file_settings(session, organization_id)

    # Check user quota if set
    if settings.user_storage_quota_bytes is not None:
        user_usage = await get_user_usage(session, organization_id, user_id)
        current_usage = user_usage.total_size_bytes if user_usage else 0
        if current_usage + additional_bytes > settings.user_storage_quota_bytes:
            quota_mb = settings.user_storage_quota_bytes / (1024 * 1024)
            return False, f"Upload would exceed your storage quota of {quota_mb:.0f}MB"

    # Check organization quota if set
    if settings.org_storage_quota_bytes is not None:
        org_usage = await get_organization_usage(session, organization_id)
        current_usage = org_usage.get("total_size_bytes", 0)
        if current_usage + additional_bytes > settings.org_storage_quota_bytes:
            quota_mb = settings.org_storage_quota_bytes / (1024 * 1024)
            return (
                False,
                f"Upload would exceed organization storage quota of {quota_mb:.0f}MB",
            )

    return True, None


async def get_all_file_settings(
    session: AsyncSession,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[OrganizationFileSettings], int]:
    """
    Get all organization file settings (admin only).

    This is for super admin to view all organization settings.

    Args:
        session: Database session
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of settings, total count)
    """
    base_query = select(OrganizationFileSettings)

    # Count query
    count_query = select(func.count()).select_from(base_query.subquery())
    count_result = await session.execute(count_query)
    total_count = count_result.scalar()

    # Data query with organization eagerly loaded
    data_query = (
        base_query.options(selectinload(OrganizationFileSettings.organization))
        .order_by(OrganizationFileSettings.created_time.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    settings = result.scalars().all()

    return list(settings), total_count or 0
