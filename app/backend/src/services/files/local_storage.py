"""
Local filesystem storage provider implementation.
Provides file storage fallback for development environments without S3.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
from typing import Any, BinaryIO, Optional

from src.logger.logger import Logger
from src.services.files.base import SignedUrlResult, StorageProvider, UploadResult


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage provider."""

    def __init__(
        self,
        storage_path: str,
        base_url: str,
        enabled: bool = True,
    ):
        """
        Initialize local storage provider.

        Args:
            storage_path: Directory path for file storage
            base_url: Base URL for generating download URLs (e.g., "http://localhost:8000")
            enabled: Whether local storage is enabled
        """
        self.storage_path = Path(storage_path).resolve()
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled

        # Create storage directory if it doesn't exist
        if self.enabled:
            try:
                self.storage_path.mkdir(parents=True, exist_ok=True)
                Logger.info(f"Local storage directory: {self.storage_path}")
            except Exception as e:
                Logger.error(f"Failed to create storage directory: {e}")
                self.enabled = False

    @property
    def provider_name(self) -> str:
        return "local"

    @property
    def bucket(self) -> str:
        """Return storage path as 'bucket' for compatibility."""
        return str(self.storage_path)

    def is_available(self) -> bool:
        """
        Check if local storage is available and enabled.

        Returns:
            True if enabled and directory is writable, False otherwise
        """
        if not self.enabled:
            return False

        try:
            # Check if directory exists and is writable
            test_file = self.storage_path / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False

    def _get_file_path(self, storage_key: str) -> Path:
        """
        Get the full filesystem path for a storage key.

        This method uses path resolution and containment checking to prevent
        path traversal attacks (CWE-22).
        """
        # Strip leading slashes to prevent absolute path interpretation
        safe_key = storage_key.lstrip("/")

        # Resolve the path to eliminate any traversal sequences (../, ./, etc.)
        requested_path = (self.storage_path / safe_key).resolve()

        # Verify the resolved path is within the storage directory
        # This prevents path traversal attacks even with URL-encoded or nested sequences
        try:
            requested_path.relative_to(self.storage_path)
        except ValueError:
            raise ValueError("Invalid storage key - path traversal detected")

        return requested_path

    async def upload(
        self,
        file_data: BinaryIO,
        storage_key: str,
        content_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UploadResult:
        """Upload a file to local storage."""
        if not self.is_available():
            Logger.error("Local storage is not available")
            return UploadResult(
                success=False,
                storage_key=storage_key,
                bucket=str(self.storage_path),
                error_message="Local storage is not available",
            )

        try:
            file_path = self._get_file_path(storage_key)

            # Create parent directories if they don't exist
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file to disk
            with open(file_path, "wb") as f:
                # Read in chunks to handle large files
                shutil.copyfileobj(file_data, f)

            Logger.info(f"Uploaded file to local storage: {file_path}")
            return UploadResult(
                success=True,
                storage_key=storage_key,
                bucket=str(self.storage_path),
            )

        except Exception as e:
            Logger.error(f"Failed to upload file to local storage: {e}")
            return UploadResult(
                success=False,
                storage_key=storage_key,
                bucket=str(self.storage_path),
                error_message=str(e),
            )

    async def delete(self, storage_key: str) -> bool:
        """Delete a file from local storage."""
        try:
            file_path = self._get_file_path(storage_key)

            if file_path.exists():
                file_path.unlink()
                Logger.info(f"Deleted file from local storage: {file_path}")

                # Clean up empty parent directories (up to storage_path)
                parent = file_path.parent
                while parent != self.storage_path:
                    try:
                        if not any(parent.iterdir()):
                            parent.rmdir()
                            parent = parent.parent
                        else:
                            break
                    except Exception:
                        break

            return True

        except Exception as e:
            Logger.error(f"Failed to delete file from local storage: {e}")
            return False

    async def exists(self, storage_key: str) -> bool:
        """Check if a file exists in local storage."""
        try:
            file_path = self._get_file_path(storage_key)
            return file_path.exists() and file_path.is_file()
        except Exception:
            return False

    async def generate_download_url(
        self, storage_key: str, expires_in: int = 3600, filename: Optional[str] = None
    ) -> SignedUrlResult:
        """
        Generate a signed URL for downloading a file.

        For local storage, this returns a URL to the file serve endpoint with
        a signed token that allows access without requiring Authorization header.
        This enables <img> tags and other browser-native requests to access files.

        Args:
            storage_key: The key/path of the file (format: {org_id}/{category}/{uuid}_{filename})
            expires_in: Expiry time in seconds (default 1 hour)
            filename: Optional filename (not used for local storage URL)

        Returns:
            SignedUrlResult with the serve endpoint URL including access token
        """
        from urllib.parse import quote

        from src.core.security import create_file_access_token

        # Extract organization_id from storage_key (format: {org_id}/{category}/{uuid}_{filename})
        key_parts = storage_key.split("/")
        if len(key_parts) >= 1:
            organization_id = key_parts[0]
        else:
            organization_id = ""

        # Create a signed token for file access
        token = create_file_access_token(
            storage_key=storage_key,
            organization_id=organization_id,
            expires_in_seconds=expires_in,
        )

        # URL-encode the storage key for the path, preserving forward slashes
        # since the serve endpoint uses a path converter ({storage_key:path})
        encoded_key = quote(storage_key, safe="/")

        url = f"{self.base_url}/api/v1/files/serve/{encoded_key}?token={token}"

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return SignedUrlResult(url=url, expires_at=expires_at, method="GET")

    async def generate_upload_url(
        self, storage_key: str, content_type: str, expires_in: int = 3600
    ) -> SignedUrlResult:
        """
        Generate a URL for uploading a file.

        For local storage, presigned upload URLs are not supported.
        Use the direct upload endpoint instead (/files/upload).

        Args:
            storage_key: The key/path where the file will be stored
            content_type: Expected MIME type of the file
            expires_in: Expiry time in seconds (for interface compatibility)

        Returns:
            SignedUrlResult pointing to the direct upload endpoint
        """
        # Local storage doesn't support presigned uploads
        # Return the direct upload URL for interface compatibility
        url = f"{self.base_url}/api/v1/files/upload"

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        return SignedUrlResult(url=url, expires_at=expires_at, method="POST")

    async def get_file_size(self, storage_key: str) -> Optional[int]:
        """Get the size of a file in bytes."""
        try:
            file_path = self._get_file_path(storage_key)
            if file_path.exists():
                return file_path.stat().st_size
            return None
        except Exception:
            return None

    async def download_bytes(
        self, storage_key: str, max_bytes: Optional[int] = None
    ) -> Optional[bytes]:
        """
        Download file content as bytes from local storage.

        Args:
            storage_key: The key/path of the file
            max_bytes: Maximum number of bytes to download (None for all)

        Returns:
            File content as bytes, or None if file doesn't exist
        """
        try:
            file_path = self._get_file_path(storage_key)
            if file_path.exists():
                if max_bytes is not None:
                    with open(file_path, "rb") as f:
                        return f.read(max_bytes)
                return file_path.read_bytes()
            return None
        except Exception as e:
            Logger.error(f"Failed to read file from local storage: {e}")
            return None

    async def get_file_content(self, storage_key: str) -> Optional[bytes]:
        """
        Read file content from local storage.

        This method is specific to LocalStorageProvider and used by the serve endpoint.

        Args:
            storage_key: The key/path of the file

        Returns:
            File content as bytes, or None if file doesn't exist
        """
        return await self.download_bytes(storage_key)

    def get_file_path_for_streaming(self, storage_key: str) -> Optional[Path]:
        """
        Get the filesystem path for streaming a file.

        This method is specific to LocalStorageProvider and used by the serve endpoint
        for efficient file streaming without loading entire file into memory.

        Args:
            storage_key: The key/path of the file

        Returns:
            Path object if file exists, None otherwise
        """
        try:
            file_path = self._get_file_path(storage_key)
            if file_path.exists() and file_path.is_file():
                return file_path
            return None
        except ValueError:
            # Path traversal detected
            return None


# Default local storage instance (configured at startup)
local_storage: Optional[LocalStorageProvider] = None


def init_local_storage(
    storage_path: str,
    base_url: str,
    enabled: bool = True,
) -> LocalStorageProvider:
    """Initialize the global local storage provider."""
    global local_storage
    local_storage = LocalStorageProvider(
        storage_path=storage_path,
        base_url=base_url,
        enabled=enabled,
    )
    return local_storage


def is_local_storage_available() -> bool:
    """
    Check if local storage is available.

    Returns:
        True if local storage is configured and enabled, False otherwise
    """
    return local_storage is not None and local_storage.is_available()
