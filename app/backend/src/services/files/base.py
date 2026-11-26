"""
Abstract base class for file storage providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO, Optional


@dataclass
class UploadResult:
    """Result from a file upload operation."""

    success: bool
    storage_key: str
    bucket: str
    error_message: Optional[str] = None


@dataclass
class SignedUrlResult:
    """Result containing a signed URL for file access."""

    url: str
    expires_at: datetime
    method: str  # 'GET' or 'PUT'


class StorageProvider(ABC):
    """Base class for file storage providers (S3, local, etc.)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique provider identifier."""
        pass

    @abstractmethod
    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UploadResult:
        """
        Upload a file to storage.

        Args:
            file_data: File-like object containing the file data
            storage_key: The key/path to store the file under
            content_type: MIME type of the file
            metadata: Optional metadata to attach to the file

        Returns:
            UploadResult with success status and storage details
        """
        pass

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """
        Delete a file from storage.

        Args:
            storage_key: The key/path of the file to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """
        Check if a file exists in storage.

        Args:
            storage_key: The key/path to check

        Returns:
            True if the file exists, False otherwise
        """
        pass

    @abstractmethod
    async def generate_download_url(
        self, storage_key: str, expires_in: int = 3600, filename: Optional[str] = None
    ) -> SignedUrlResult:
        """
        Generate a signed URL for downloading a file.

        Args:
            storage_key: The key/path of the file
            expires_in: Expiry time in seconds (default 1 hour)
            filename: Optional filename for Content-Disposition header

        Returns:
            SignedUrlResult with the download URL
        """
        pass

    @abstractmethod
    async def generate_upload_url(
        self, storage_key: str, content_type: str, expires_in: int = 3600
    ) -> SignedUrlResult:
        """
        Generate a signed URL for uploading a file directly to storage.

        Args:
            storage_key: The key/path where the file will be stored
            content_type: Expected MIME type of the file
            expires_in: Expiry time in seconds (default 1 hour)

        Returns:
            SignedUrlResult with the upload URL
        """
        pass

    @abstractmethod
    async def get_file_size(self, storage_key: str) -> Optional[int]:
        """
        Get the size of a file in bytes.

        Args:
            storage_key: The key/path of the file

        Returns:
            File size in bytes, or None if file doesn't exist
        """
        pass

    @abstractmethod
    async def download_bytes(
        self, storage_key: str, max_bytes: Optional[int] = None
    ) -> Optional[bytes]:
        """
        Download file content as bytes.

        Args:
            storage_key: The key/path of the file
            max_bytes: Maximum number of bytes to download (None for all)

        Returns:
            File content as bytes, or None if file doesn't exist
        """
        pass
