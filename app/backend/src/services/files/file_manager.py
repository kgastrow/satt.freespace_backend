"""
Main file management service.
Coordinates uploads, downloads, and deletions.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import io
from typing import BinaryIO, Optional, Union
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger
from src.models.file import File, MediaUse
from src.models.organization_file_settings import OrganizationFileSettings
from src.services.files.base import SignedUrlResult, StorageProvider
from src.services.files.usage_tracker import (
    UsageTracker,
    usage_tracker,
)
from src.services.files.validators import (
    MIME_TO_EXTENSIONS,
    FileValidator,
    file_validator,
)
from src.services.thumbnail import thumbnail_service


@dataclass
class UploadInitResult:
    """Result of initiating an upload."""

    success: bool
    file_id: Optional[UUID] = None
    storage_key: Optional[str] = None
    upload_url: Optional[str] = None
    upload_url_expires_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class UploadCompleteResult:
    """Result of completing an upload."""

    success: bool
    file: Optional[File] = None
    error_message: Optional[str] = None


@dataclass
class DirectUploadResult:
    """Result of a direct file upload."""

    success: bool
    file: Optional[File] = None
    error_message: Optional[str] = None
    thumbnail_storage_key: Optional[str] = None


class FileManager:
    """
    Main file management service.
    Handles uploads, downloads, and deletions with validation and quota tracking.
    """

    def __init__(
        self,
        storage_provider: StorageProvider,
        validator: Optional[FileValidator] = None,
        tracker: Optional[UsageTracker] = None,
    ):
        """
        Initialize file manager.

        Args:
            storage_provider: The storage provider to use (S3, etc.)
            validator: File validator (uses global if not provided)
            tracker: Usage tracker (uses global if not provided)
        """
        self.storage = storage_provider
        self.validator = validator or file_validator
        self.tracker = tracker or usage_tracker

    def _generate_storage_key(
        self, organization_id: UUID, filename: str, category: Optional[str] = None
    ) -> str:
        """
        Generate a unique storage key for a file.

        Format: {org_id}/{category}/{uuid}_{filename}
        """
        file_uuid = uuid.uuid4()
        category = category or "other"

        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        if len(safe_filename) > 100:
            # Keep extension and truncate name
            if "." in safe_filename:
                name, ext = safe_filename.rsplit(".", 1)
                safe_filename = f"{name[:90]}.{ext}"
            else:
                safe_filename = safe_filename[:100]

        return f"{organization_id}/{category}/{file_uuid}_{safe_filename}"

    async def _get_signed_url_expiry(
        self, session: AsyncSession, organization_id: UUID
    ) -> int:
        """Get the signed URL expiry time for an organization."""
        result = await session.execute(
            select(OrganizationFileSettings).where(
                OrganizationFileSettings.organization_id == organization_id
            )
        )
        settings = result.scalar_one_or_none()

        if settings and settings.signed_url_expiry_seconds:
            return settings.signed_url_expiry_seconds
        return 3600  # Default 1 hour

    async def _validate_uploaded_content(
        self, storage_key: str, original_filename: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that uploaded file content matches its declared extension.

        Downloads the first 2048 bytes and checks magic bytes against the extension.

        Args:
            storage_key: The storage key of the uploaded file
            original_filename: The original filename with extension

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Download first 2048 bytes for magic detection
            header_bytes = await self.storage.download_bytes(
                storage_key, max_bytes=2048
            )
            if header_bytes is None:
                return False, "Failed to read uploaded file for validation"

            # Get the extension
            extension = self.validator.get_file_extension(original_filename)
            if not extension:
                return False, "File must have an extension"

            # Detect content type from bytes
            detected_type = self.validator.detect_content_type_from_bytes(header_bytes)
            if detected_type is None:
                # Detection failed, log warning but allow
                Logger.warning(f"Could not detect content type for {original_filename}")
                return True, None

            # Check if detected type is allowed for this extension
            allowed_extensions = MIME_TO_EXTENSIONS.get(detected_type, set())

            # Handle generic types that can't be validated
            generic_types = {
                "application/octet-stream",
                "application/x-empty",
                "inode/x-empty",
            }
            if detected_type in generic_types:
                return True, None

            # For text types, be more permissive
            if detected_type.startswith("text/"):
                text_extensions = {"txt", "csv", "json", "xml", "html", "css", "js"}
                if extension in text_extensions:
                    return True, None

            if extension in allowed_extensions:
                return True, None

            # Check for common acceptable variations
            zip_based_extensions = {"docx", "xlsx", "pptx", "odt", "ods", "odp"}
            if detected_type in {"application/zip", "application/x-zip-compressed"}:
                if extension in zip_based_extensions or extension == "zip":
                    return True, None

            return (
                False,
                f"File content does not match extension '.{extension}' (detected type: {detected_type})",
            )

        except Exception as e:
            Logger.error(f"Content validation failed: {e}")
            # On error, fail safe by rejecting
            return False, "Failed to validate file content"

    async def _generate_and_upload_thumbnail(
        self,
        file_data: bytes,
        storage_key: str,
        organization_id: UUID,
    ) -> Optional[str]:
        """
        Generate and upload a thumbnail for an image file.

        Args:
            file_data: Original image bytes
            storage_key: Storage key of the original file
            organization_id: Organization ID

        Returns:
            Thumbnail storage key if successful, None otherwise
        """
        if not thumbnail_service.is_available():
            Logger.warning("Thumbnail service not available (Pillow not installed)")
            return None

        try:
            # Generate thumbnail
            file_io = io.BytesIO(file_data)
            thumbnail_result = thumbnail_service.generate_thumbnail(file_io)

            if not thumbnail_result.success or not thumbnail_result.thumbnail_data:
                Logger.warning(
                    f"Thumbnail generation failed: {thumbnail_result.error_message}"
                )
                return None

            # Generate thumbnail storage key
            # Transform: {org_id}/{category}/{uuid}_{filename}
            # Into:      {org_id}/{category}/{uuid}_thumb.webp
            parts = storage_key.rsplit("_", 1)
            if len(parts) == 2:
                thumbnail_storage_key = f"{parts[0]}_thumb.webp"
            else:
                thumbnail_storage_key = f"{storage_key}_thumb.webp"

            # Upload thumbnail to storage
            upload_result = await self.storage.upload(
                thumbnail_result.thumbnail_data,
                thumbnail_storage_key,
                "image/webp",
            )

            if not upload_result.success:
                Logger.warning(
                    f"Thumbnail upload failed: {upload_result.error_message}"
                )
                return None

            Logger.info(f"Thumbnail generated and uploaded: {thumbnail_storage_key}")
            return thumbnail_storage_key

        except Exception as e:
            Logger.error(f"Thumbnail generation/upload failed: {e}")
            return None

    async def initiate_upload(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
        filename: str,
        size_bytes: int,
        content_type: Optional[str] = None,
        media_use: Optional[MediaUse] = None,
        is_public: bool = False,
    ) -> UploadInitResult:
        """
        Initiate a presigned URL upload.
        Creates a pending file record and returns a presigned upload URL.

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID
            filename: Original filename
            size_bytes: Expected file size in bytes
            content_type: MIME type (auto-detected if not provided)
            media_use: Optional media use case (avatar, announcement, etc.)
            is_public: Whether the file should be publicly accessible

        Returns:
            UploadInitResult with upload URL and file ID
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        uid = UUID(user_id) if isinstance(user_id, str) else user_id

        # Validate file
        validation = await self.validator.validate_file(
            session, org_id, filename, size_bytes
        )
        if not validation.valid:
            return UploadInitResult(
                success=False, error_message=validation.error_message
            )

        # Check quotas
        user_quota = await self.tracker.check_user_quota(
            session, org_id, uid, size_bytes
        )
        if not user_quota.allowed:
            return UploadInitResult(
                success=False, error_message=user_quota.error_message
            )

        org_quota = await self.tracker.check_organization_quota(
            session, org_id, size_bytes
        )
        if not org_quota.allowed:
            return UploadInitResult(
                success=False, error_message=org_quota.error_message
            )

        # Determine content type
        file_content_type = (
            content_type or validation.content_type or "application/octet-stream"
        )

        # Generate storage key
        storage_key = self._generate_storage_key(org_id, filename, validation.category)

        # Create pending file record
        file = File(
            organization_id=org_id,
            uploaded_by_user_id=uid,
            original_filename=filename,
            storage_key=storage_key,
            content_type=file_content_type,
            file_extension=self.validator.get_file_extension(filename),
            size_bytes=size_bytes,
            storage_provider=self.storage.provider_name,
            bucket_name=getattr(self.storage, "bucket", None),
            status="pending",
            category=validation.category,
            media_use=media_use,
            is_public=is_public,
        )
        session.add(file)
        await session.flush()

        # Generate presigned upload URL
        expiry_seconds = await self._get_signed_url_expiry(session, org_id)
        signed_url = await self.storage.generate_upload_url(
            storage_key, file_content_type, expires_in=expiry_seconds
        )

        return UploadInitResult(
            success=True,
            file_id=file.id,
            storage_key=storage_key,
            upload_url=signed_url.url,
            upload_url_expires_at=signed_url.expires_at,
        )

    async def complete_upload(
        self,
        session: AsyncSession,
        file_id: Union[str, UUID],
        organization_id: Union[str, UUID],
        verify_upload: bool = True,
        validate_content: bool = True,
    ) -> UploadCompleteResult:
        """
        Complete a presigned URL upload.
        Verifies the file exists in storage, validates content, and updates the file record.

        Args:
            session: Database session
            file_id: ID of the pending file
            organization_id: Organization ID (for security)
            verify_upload: Whether to verify the file exists in storage
            validate_content: Whether to validate file content matches extension

        Returns:
            UploadCompleteResult with the updated file
        """
        fid = UUID(file_id) if isinstance(file_id, str) else file_id
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get the file record
        result = await session.execute(
            select(File)
            .where(File.id == fid)
            .where(File.organization_id == org_id)
            .where(File.deleted_time.is_(None))
        )
        file = result.scalar_one_or_none()

        if not file:
            return UploadCompleteResult(success=False, error_message="File not found")

        if file.status != "pending":
            return UploadCompleteResult(
                success=False,
                error_message=f"File is not pending upload (status: {file.status})",
            )

        # Verify the file exists in storage
        if verify_upload:
            exists = await self.storage.exists(file.storage_key)
            if not exists:
                file.status = "failed"
                await session.flush()
                return UploadCompleteResult(
                    success=False, error_message="File not found in storage"
                )

            # Get actual file size from storage
            actual_size = await self.storage.get_file_size(file.storage_key)
            if actual_size and actual_size != file.size_bytes:
                file.size_bytes = actual_size

        # Validate that the uploaded file content matches the declared extension
        # This prevents attackers from uploading malicious files via presigned URLs
        if validate_content:
            is_valid, error_msg = await self._validate_uploaded_content(
                file.storage_key, file.original_filename
            )
            if not is_valid:
                file.status = "failed"
                await session.flush()
                # Delete the invalid file from storage
                await self.storage.delete(file.storage_key)
                return UploadCompleteResult(
                    success=False,
                    error_message=error_msg or "File content validation failed",
                )

        # Generate thumbnail for images
        if file.category == "image" and file.content_type.startswith("image/"):
            # Download file content for thumbnail generation
            file_data = await self.storage.download_bytes(file.storage_key)
            if file_data:
                thumbnail_key = await self._generate_and_upload_thumbnail(
                    file_data, file.storage_key, org_id
                )
                if thumbnail_key:
                    file.thumbnail_storage_key = thumbnail_key

        # Mark as ready
        file.status = "ready"

        # Update usage tracking
        await self.tracker.record_upload(
            session,
            file.organization_id,
            file.uploaded_by_user_id,
            file.size_bytes,
            file.category or "other",
        )

        await session.flush()

        return UploadCompleteResult(success=True, file=file)

    async def upload_direct(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        user_id: Union[str, UUID],
        filename: str,
        file_data: BinaryIO,
        content_type: Optional[str] = None,
        media_use: Optional[MediaUse] = None,
        generate_thumbnail: bool = True,
        is_public: bool = False,
    ) -> DirectUploadResult:
        """
        Upload a file directly (server-side upload).

        Args:
            session: Database session
            organization_id: Organization ID
            user_id: User ID
            filename: Original filename
            file_data: File-like object with file content
            content_type: MIME type (auto-detected if not provided)
            media_use: Optional media use case (avatar, announcement, etc.)
            generate_thumbnail: Whether to generate thumbnail for images (default True)
            is_public: Whether the file should be publicly accessible

        Returns:
            DirectUploadResult with the created file
        """
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        uid = UUID(user_id) if isinstance(user_id, str) else user_id

        # Get file size
        file_data.seek(0, 2)  # Seek to end
        size_bytes = file_data.tell()
        file_data.seek(0)  # Seek back to start

        # Validate file
        validation = await self.validator.validate_file(
            session, org_id, filename, size_bytes
        )
        if not validation.valid:
            return DirectUploadResult(
                success=False, error_message=validation.error_message
            )

        # Check quotas
        user_quota = await self.tracker.check_user_quota(
            session, org_id, uid, size_bytes
        )
        if not user_quota.allowed:
            return DirectUploadResult(
                success=False, error_message=user_quota.error_message
            )

        org_quota = await self.tracker.check_organization_quota(
            session, org_id, size_bytes
        )
        if not org_quota.allowed:
            return DirectUploadResult(
                success=False, error_message=org_quota.error_message
            )

        # Determine content type
        file_content_type = (
            content_type or validation.content_type or "application/octet-stream"
        )

        # Generate storage key
        storage_key = self._generate_storage_key(org_id, filename, validation.category)

        # Read file data for upload and potential thumbnail generation
        file_bytes = file_data.read()
        file_data_io = io.BytesIO(file_bytes)

        # Upload to storage
        upload_result = await self.storage.upload(
            file_data_io, storage_key, file_content_type
        )

        if not upload_result.success:
            return DirectUploadResult(
                success=False, error_message=upload_result.error_message
            )

        # Generate thumbnail for images
        thumbnail_storage_key = None
        if (
            generate_thumbnail
            and validation.category == "image"
            and file_content_type.startswith("image/")
        ):
            thumbnail_storage_key = await self._generate_and_upload_thumbnail(
                file_bytes, storage_key, org_id
            )

        # Create file record
        file = File(
            organization_id=org_id,
            uploaded_by_user_id=uid,
            original_filename=filename,
            storage_key=storage_key,
            content_type=file_content_type,
            file_extension=self.validator.get_file_extension(filename),
            size_bytes=size_bytes,
            storage_provider=self.storage.provider_name,
            bucket_name=upload_result.bucket,
            status="ready",
            category=validation.category,
            media_use=media_use,
            is_public=is_public,
            thumbnail_storage_key=thumbnail_storage_key,
        )
        session.add(file)

        # Update usage tracking
        await self.tracker.record_upload(
            session, org_id, uid, size_bytes, validation.category or "other"
        )

        await session.flush()

        return DirectUploadResult(
            success=True,
            file=file,
            thumbnail_storage_key=thumbnail_storage_key,
        )

    async def get_thumbnail_url(
        self,
        session: AsyncSession,
        file_id: Union[str, UUID],
        organization_id: Union[str, UUID],
    ) -> Optional[SignedUrlResult]:
        """
        Get a presigned download URL for a file's thumbnail.

        Args:
            session: Database session
            file_id: File ID
            organization_id: Organization ID (for security)

        Returns:
            SignedUrlResult with thumbnail URL, or None if file/thumbnail not found
        """
        fid = UUID(file_id) if isinstance(file_id, str) else file_id
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get the file record
        result = await session.execute(
            select(File)
            .where(File.id == fid)
            .where(File.organization_id == org_id)
            .where(File.deleted_time.is_(None))
            .where(File.status == "ready")
        )
        file = result.scalar_one_or_none()

        if not file or not file.thumbnail_storage_key:
            return None

        # Get signed URL expiry
        expiry_seconds = await self._get_signed_url_expiry(session, org_id)

        # Generate download URL for thumbnail
        return await self.storage.generate_download_url(
            file.thumbnail_storage_key,
            expires_in=expiry_seconds,
            filename=f"{file.original_filename}_thumb.webp",
        )

    async def get_download_url(
        self,
        session: AsyncSession,
        file_id: Union[str, UUID],
        organization_id: Union[str, UUID],
        include_filename: bool = True,
    ) -> Optional[SignedUrlResult]:
        """
        Get a presigned download URL for a file.

        Args:
            session: Database session
            file_id: File ID
            organization_id: Organization ID (for security)
            include_filename: Whether to include Content-Disposition header

        Returns:
            SignedUrlResult with download URL, or None if file not found
        """
        fid = UUID(file_id) if isinstance(file_id, str) else file_id
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get the file record
        result = await session.execute(
            select(File)
            .where(File.id == fid)
            .where(File.organization_id == org_id)
            .where(File.deleted_time.is_(None))
            .where(File.status == "ready")
        )
        file = result.scalar_one_or_none()

        if not file:
            return None

        # Update access tracking
        file.download_count += 1
        file.last_accessed_time = datetime.now(timezone.utc)
        await session.flush()

        # Get signed URL expiry
        expiry_seconds = await self._get_signed_url_expiry(session, org_id)

        # Generate download URL
        filename = file.original_filename if include_filename else None
        return await self.storage.generate_download_url(
            file.storage_key, expires_in=expiry_seconds, filename=filename
        )

    async def soft_delete(
        self,
        session: AsyncSession,
        file_id: Union[str, UUID],
        organization_id: Union[str, UUID],
    ) -> bool:
        """
        Soft delete a file (marks as deleted but keeps in storage).

        Args:
            session: Database session
            file_id: File ID
            organization_id: Organization ID (for security)

        Returns:
            True if file was deleted, False if not found
        """
        fid = UUID(file_id) if isinstance(file_id, str) else file_id
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get the file record
        result = await session.execute(
            select(File)
            .where(File.id == fid)
            .where(File.organization_id == org_id)
            .where(File.deleted_time.is_(None))
        )
        file = result.scalar_one_or_none()

        if not file:
            return False

        # Mark as deleted
        file.deleted_time = datetime.now(timezone.utc)
        file.status = "deleted"

        # Update usage tracking
        await self.tracker.record_deletion(
            session,
            file.organization_id,
            file.uploaded_by_user_id,
            file.size_bytes,
            file.category or "other",
        )

        await session.flush()
        return True

    async def hard_delete(
        self,
        session: AsyncSession,
        file_id: Union[str, UUID],
        organization_id: Union[str, UUID],
    ) -> bool:
        """
        Permanently delete a file from storage and database.

        Args:
            session: Database session
            file_id: File ID
            organization_id: Organization ID (for security)

        Returns:
            True if file was deleted, False if not found
        """
        fid = UUID(file_id) if isinstance(file_id, str) else file_id
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

        # Get the file record
        result = await session.execute(
            select(File).where(File.id == fid).where(File.organization_id == org_id)
        )
        file = result.scalar_one_or_none()

        if not file:
            return False

        # Delete from storage
        await self.storage.delete(file.storage_key)

        # If not already soft-deleted, update usage tracking
        if file.deleted_time is None:
            await self.tracker.record_deletion(
                session,
                file.organization_id,
                file.uploaded_by_user_id,
                file.size_bytes,
                file.category or "other",
            )

        # Delete from database
        await session.delete(file)
        await session.flush()

        return True


# Global file manager (initialized at app startup)
file_manager: Optional[FileManager] = None


def init_file_manager(storage_provider: StorageProvider) -> FileManager:
    """Initialize the global file manager."""
    global file_manager
    file_manager = FileManager(storage_provider)
    return file_manager


def get_file_manager() -> Optional[FileManager]:
    """Get the global file manager instance."""
    return file_manager
