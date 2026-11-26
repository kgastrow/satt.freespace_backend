"""
File usage tracking and quota enforcement service.
"""

from dataclasses import dataclass
from typing import Optional, Union
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.file import File
from src.models.file_usage import FileUsage
from src.models.organization_file_settings import OrganizationFileSettings


@dataclass
class QuotaCheckResult:
    """Result of a quota check."""

    allowed: bool
    current_usage_bytes: int
    quota_bytes: Optional[int]  # None = unlimited
    error_message: Optional[str] = None


@dataclass
class UsageStats:
    """File usage statistics."""

    total_files: int
    total_size_bytes: int
    image_count: int
    image_size_bytes: int
    video_count: int
    video_size_bytes: int
    document_count: int
    document_size_bytes: int
    audio_count: int
    audio_size_bytes: int
    other_count: int
    other_size_bytes: int


class UsageTracker:
    """Tracks file storage usage and enforces quotas."""

    async def get_or_create_user_usage(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
    ) -> FileUsage:
        """
        Get or create a usage record for a user.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID

        Returns:
            FileUsage record
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        uid = UUID(user_id) if isinstance(user_id, str) else user_id

        result = await session.execute(
            select(FileUsage)
            .where(FileUsage.organization_id == org_id)
            .where(FileUsage.user_id == uid)
        )
        usage = result.scalar_one_or_none()

        if not usage:
            usage = FileUsage(organization_id=org_id, user_id=uid)
            session.add(usage)
            await session.flush()

        return usage

    async def check_user_quota(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
        additional_bytes: int = 0,
    ) -> QuotaCheckResult:
        """
        Check if a user has quota available for an upload.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID
            additional_bytes: Size of the file to be uploaded

        Returns:
            QuotaCheckResult with quota status
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        uid = UUID(user_id) if isinstance(user_id, str) else user_id

        # Get organization settings
        result = await session.execute(
            select(OrganizationFileSettings).where(
                OrganizationFileSettings.organization_id == org_id
            )
        )
        settings = result.scalar_one_or_none()

        # Get current user usage
        usage = await self.get_or_create_user_usage(session, org_id, uid)
        current_usage = usage.total_size_bytes

        # Check user quota
        user_quota = settings.user_storage_quota_bytes if settings else None

        if user_quota is not None:
            if current_usage + additional_bytes > user_quota:
                return QuotaCheckResult(
                    allowed=False,
                    current_usage_bytes=current_usage,
                    quota_bytes=user_quota,
                    error_message=f"User storage quota exceeded. "
                    f"Current: {current_usage / (1024*1024):.1f}MB, "
                    f"Limit: {user_quota / (1024*1024):.1f}MB",
                )

        return QuotaCheckResult(
            allowed=True, current_usage_bytes=current_usage, quota_bytes=user_quota
        )

    async def check_organization_quota(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        additional_bytes: int = 0,
    ) -> QuotaCheckResult:
        """
        Check if an organization has quota available for an upload.

        Args:
            session: Database session
            organization_id: Organization ID
            additional_bytes: Size of the file to be uploaded

        Returns:
            QuotaCheckResult with quota status
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get organization settings
        result = await session.execute(
            select(OrganizationFileSettings).where(
                OrganizationFileSettings.organization_id == org_id
            )
        )
        settings = result.scalar_one_or_none()

        # Calculate total org usage
        usage_result = await session.execute(
            select(func.coalesce(func.sum(File.size_bytes), 0))
            .where(File.organization_id == org_id)
            .where(File.deleted_time.is_(None))
            .where(File.status != "failed")
        )
        current_usage = usage_result.scalar() or 0

        # Check org quota
        org_quota = settings.org_storage_quota_bytes if settings else None

        if org_quota is not None:
            if current_usage + additional_bytes > org_quota:
                return QuotaCheckResult(
                    allowed=False,
                    current_usage_bytes=current_usage,
                    quota_bytes=org_quota,
                    error_message=f"Organization storage quota exceeded. "
                    f"Current: {current_usage / (1024*1024):.1f}MB, "
                    f"Limit: {org_quota / (1024*1024):.1f}MB",
                )

        return QuotaCheckResult(
            allowed=True, current_usage_bytes=current_usage, quota_bytes=org_quota
        )

    async def record_upload(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
        size_bytes: int,
        category: str,
    ) -> FileUsage:
        """
        Record a file upload in usage tracking.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID
            size_bytes: Size of the uploaded file
            category: File category (image, video, document, etc.)

        Returns:
            Updated FileUsage record
        """
        usage = await self.get_or_create_user_usage(session, organization_id, user_id)

        # Update totals
        usage.total_files += 1
        usage.total_size_bytes += size_bytes

        # Update category-specific counts
        category = category.lower()
        if category == "image":
            usage.image_count += 1
            usage.image_size_bytes += size_bytes
        elif category == "video":
            usage.video_count += 1
            usage.video_size_bytes += size_bytes
        elif category == "document":
            usage.document_count += 1
            usage.document_size_bytes += size_bytes
        elif category == "audio":
            usage.audio_count += 1
            usage.audio_size_bytes += size_bytes
        else:
            usage.other_count += 1
            usage.other_size_bytes += size_bytes

        await session.flush()
        return usage

    async def record_deletion(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
        size_bytes: int,
        category: str,
    ) -> FileUsage:
        """
        Record a file deletion in usage tracking.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID
            size_bytes: Size of the deleted file
            category: File category

        Returns:
            Updated FileUsage record
        """
        usage = await self.get_or_create_user_usage(session, organization_id, user_id)

        # Update totals
        usage.total_files = max(0, usage.total_files - 1)
        usage.total_size_bytes = max(0, usage.total_size_bytes - size_bytes)

        # Update category-specific counts
        category = category.lower()
        if category == "image":
            usage.image_count = max(0, usage.image_count - 1)
            usage.image_size_bytes = max(0, usage.image_size_bytes - size_bytes)
        elif category == "video":
            usage.video_count = max(0, usage.video_count - 1)
            usage.video_size_bytes = max(0, usage.video_size_bytes - size_bytes)
        elif category == "document":
            usage.document_count = max(0, usage.document_count - 1)
            usage.document_size_bytes = max(0, usage.document_size_bytes - size_bytes)
        elif category == "audio":
            usage.audio_count = max(0, usage.audio_count - 1)
            usage.audio_size_bytes = max(0, usage.audio_size_bytes - size_bytes)
        else:
            usage.other_count = max(0, usage.other_count - 1)
            usage.other_size_bytes = max(0, usage.other_size_bytes - size_bytes)

        await session.flush()
        return usage

    async def get_user_usage_stats(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
    ) -> UsageStats:
        """
        Get usage statistics for a user.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID

        Returns:
            UsageStats with current usage
        """
        usage = await self.get_or_create_user_usage(session, organization_id, user_id)

        return UsageStats(
            total_files=usage.total_files,
            total_size_bytes=usage.total_size_bytes,
            image_count=usage.image_count,
            image_size_bytes=usage.image_size_bytes,
            video_count=usage.video_count,
            video_size_bytes=usage.video_size_bytes,
            document_count=usage.document_count,
            document_size_bytes=usage.document_size_bytes,
            audio_count=usage.audio_count,
            audio_size_bytes=usage.audio_size_bytes,
            other_count=usage.other_count,
            other_size_bytes=usage.other_size_bytes,
        )

    async def recalculate_user_usage(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
    ) -> FileUsage:
        """
        Recalculate usage from actual files (for data integrity).

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID

        Returns:
            Updated FileUsage record
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        uid = UUID(user_id) if isinstance(user_id, str) else user_id

        usage = await self.get_or_create_user_usage(session, org_id, uid)

        # Reset all counters
        usage.total_files = 0
        usage.total_size_bytes = 0
        usage.image_count = 0
        usage.image_size_bytes = 0
        usage.video_count = 0
        usage.video_size_bytes = 0
        usage.document_count = 0
        usage.document_size_bytes = 0
        usage.audio_count = 0
        usage.audio_size_bytes = 0
        usage.other_count = 0
        usage.other_size_bytes = 0

        # Query actual files
        result = await session.execute(
            select(File)
            .where(File.organization_id == org_id)
            .where(File.uploaded_by_user_id == uid)
            .where(File.deleted_time.is_(None))
            .where(File.status != "failed")
        )
        files = result.scalars().all()

        for file in files:
            usage.total_files += 1
            usage.total_size_bytes += file.size_bytes

            category = (file.category or "other").lower()
            if category == "image":
                usage.image_count += 1
                usage.image_size_bytes += file.size_bytes
            elif category == "video":
                usage.video_count += 1
                usage.video_size_bytes += file.size_bytes
            elif category == "document":
                usage.document_count += 1
                usage.document_size_bytes += file.size_bytes
            elif category == "audio":
                usage.audio_count += 1
                usage.audio_size_bytes += file.size_bytes
            else:
                usage.other_count += 1
                usage.other_size_bytes += file.size_bytes

        await session.flush()
        return usage


# Global usage tracker instance
usage_tracker = UsageTracker()
