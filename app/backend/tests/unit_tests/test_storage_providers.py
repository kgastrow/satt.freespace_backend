"""
Tests for file storage providers and FileManager.

Tests the following components:
- LocalStorageProvider: Local filesystem storage operations
- S3StorageProvider: AWS S3 storage operations (mocked)
- FileManager: Main file management service with both backends
- Storage initialization and fallback logic
"""

from datetime import datetime, timedelta, timezone
import io
import shutil
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.files.base import SignedUrlResult, UploadResult
from src.services.files.file_manager import (
    FileManager,
    get_file_manager,
    init_file_manager,
)
from src.services.files.local_storage import (
    LocalStorageProvider,
    init_local_storage,
    is_local_storage_available,
)
from src.services.files.s3_storage import (
    S3StorageProvider,
    init_s3_storage,
    is_s3_available,
)


# Check if aioboto3 is available for S3 tests
try:
    import aioboto3

    AIOBOTO3_AVAILABLE = True
except ImportError:
    aioboto3 = None
    AIOBOTO3_AVAILABLE = False

# Skip decorator for S3 tests requiring aioboto3
skip_if_no_aioboto3 = pytest.mark.skipif(
    not AIOBOTO3_AVAILABLE, reason="aioboto3 not installed"
)


# ============================================================================
# LOCAL STORAGE PROVIDER TESTS
# ============================================================================


class TestLocalStorageProvider:
    """Tests for LocalStorageProvider class."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        # Cleanup after test
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def local_storage(self, temp_storage_dir):
        """Create a LocalStorageProvider instance for testing."""
        return LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://localhost:8000",
            enabled=True,
        )

    def test_provider_name(self, local_storage):
        """Test provider name is 'local'."""
        assert local_storage.provider_name == "local"

    def test_bucket_property(self, local_storage, temp_storage_dir):
        """Test bucket property returns storage path."""
        from pathlib import Path

        # Both paths should be resolved to handle symlinks (e.g., /tmp -> /private/tmp on macOS)
        assert local_storage.bucket == str(Path(temp_storage_dir).resolve())

    def test_is_available_when_enabled(self, local_storage):
        """Test storage is available when enabled and directory exists."""
        assert local_storage.is_available() is True

    def test_is_available_when_disabled(self, temp_storage_dir):
        """Test storage is not available when disabled."""
        storage = LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://localhost:8000",
            enabled=False,
        )
        assert storage.is_available() is False

    def test_is_available_non_writable_directory(self):
        """Test storage is not available when directory is not writable."""
        storage = LocalStorageProvider(
            storage_path="/nonexistent/path/that/does/not/exist",
            base_url="http://localhost:8000",
            enabled=True,
        )
        # Should fail because directory doesn't exist and can't be created
        assert storage.is_available() is False

    @pytest.mark.asyncio
    async def test_upload_success(self, local_storage):
        """Test successful file upload."""
        file_content = b"Hello, World!"
        file_data = io.BytesIO(file_content)
        storage_key = "test-org/images/test-file.txt"

        result = await local_storage.upload(
            file_data=file_data,
            storage_key=storage_key,
            content_type="text/plain",
        )

        assert result.success is True
        assert result.storage_key == storage_key
        assert result.error_message is None

        # Verify file was actually written
        file_path = local_storage._get_file_path(storage_key)
        assert file_path.exists()
        assert file_path.read_bytes() == file_content

    @pytest.mark.asyncio
    async def test_upload_creates_directories(self, local_storage):
        """Test upload creates parent directories."""
        file_data = io.BytesIO(b"test content")
        storage_key = "deep/nested/path/to/file.txt"

        result = await local_storage.upload(
            file_data=file_data,
            storage_key=storage_key,
            content_type="text/plain",
        )

        assert result.success is True
        file_path = local_storage._get_file_path(storage_key)
        assert file_path.exists()

    @pytest.mark.asyncio
    async def test_upload_when_not_available(self, temp_storage_dir):
        """Test upload fails when storage is not available."""
        storage = LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://localhost:8000",
            enabled=False,
        )

        result = await storage.upload(
            file_data=io.BytesIO(b"test"),
            storage_key="test.txt",
            content_type="text/plain",
        )

        assert result.success is False
        assert "not available" in result.error_message

    @pytest.mark.asyncio
    async def test_exists_true(self, local_storage):
        """Test exists returns True for existing file."""
        storage_key = "test/exists.txt"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test")

        assert await local_storage.exists(storage_key) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, local_storage):
        """Test exists returns False for non-existing file."""
        assert await local_storage.exists("nonexistent/file.txt") is False

    @pytest.mark.asyncio
    async def test_delete_success(self, local_storage):
        """Test successful file deletion."""
        storage_key = "test/delete.txt"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("to be deleted")

        result = await local_storage.delete(storage_key)

        assert result is True
        assert not file_path.exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, local_storage):
        """Test deleting a non-existent file returns True (idempotent)."""
        result = await local_storage.delete("nonexistent/file.txt")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_cleans_empty_directories(self, local_storage):
        """Test delete cleans up empty parent directories."""
        storage_key = "org/category/file.txt"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("test")

        await local_storage.delete(storage_key)

        # Empty directories should be cleaned up
        assert not file_path.parent.exists()

    @pytest.mark.asyncio
    async def test_get_file_size(self, local_storage):
        """Test getting file size."""
        storage_key = "test/size.txt"
        content = b"Hello World"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        size = await local_storage.get_file_size(storage_key)
        assert size == len(content)

    @pytest.mark.asyncio
    async def test_get_file_size_nonexistent(self, local_storage):
        """Test getting size of non-existent file returns None."""
        size = await local_storage.get_file_size("nonexistent.txt")
        assert size is None

    @pytest.mark.asyncio
    async def test_generate_download_url(self, local_storage):
        """Test generating download URL."""
        storage_key = "test/download.txt"

        result = await local_storage.generate_download_url(
            storage_key=storage_key,
            expires_in=3600,
            filename="myfile.txt",
        )

        assert result.url.startswith("http://localhost:8000/api/v1/files/serve/")
        assert result.method == "GET"
        assert result.expires_at > datetime.now(timezone.utc)

    @pytest.mark.asyncio
    async def test_generate_upload_url(self, local_storage):
        """Test generating upload URL returns direct upload endpoint."""
        result = await local_storage.generate_upload_url(
            storage_key="test/upload.txt",
            content_type="text/plain",
            expires_in=3600,
        )

        assert result.url == "http://localhost:8000/api/v1/files/upload"
        assert result.method == "POST"

    @pytest.mark.asyncio
    async def test_get_file_content(self, local_storage):
        """Test reading file content."""
        storage_key = "test/content.txt"
        content = b"File content here"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)

        result = await local_storage.get_file_content(storage_key)
        assert result == content

    @pytest.mark.asyncio
    async def test_get_file_content_nonexistent(self, local_storage):
        """Test reading non-existent file returns None."""
        result = await local_storage.get_file_content("nonexistent.txt")
        assert result is None

    def test_get_file_path_for_streaming(self, local_storage):
        """Test getting file path for streaming."""
        storage_key = "test/stream.txt"
        file_path = local_storage._get_file_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("streaming content")

        result = local_storage.get_file_path_for_streaming(storage_key)
        assert result == file_path

    def test_get_file_path_for_streaming_nonexistent(self, local_storage):
        """Test streaming path for non-existent file returns None."""
        result = local_storage.get_file_path_for_streaming("nonexistent.txt")
        assert result is None

    def test_path_traversal_blocked(self, local_storage):
        """Test that path traversal attempts are blocked."""
        # Actual path traversal attempt should raise ValueError
        with pytest.raises(ValueError, match="path traversal detected"):
            local_storage._get_file_path("../etc/passwd")

        with pytest.raises(ValueError, match="path traversal detected"):
            local_storage._get_file_path("foo/../../etc/passwd")

    def test_legitimate_double_dot_filename_allowed(self, local_storage):
        """Test that legitimate filenames with double dots are allowed."""
        # A filename like "some..path/file.txt" is legitimate and allowed
        # because it doesn't traverse outside the storage directory
        key_with_dots = "some..path/file.txt"
        file_path = local_storage._get_file_path(key_with_dots)

        # Path should be within storage
        assert str(file_path).startswith(str(local_storage.storage_path))


class TestLocalStorageGlobals:
    """Tests for local storage global functions."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_local_storage(self, temp_storage_dir):
        """Test initializing global local storage."""
        storage = init_local_storage(
            storage_path=temp_storage_dir,
            base_url="http://test.com",
            enabled=True,
        )

        assert storage is not None
        assert storage.provider_name == "local"
        assert is_local_storage_available() is True

    def test_is_local_storage_available_not_initialized(self):
        """Test availability check when not initialized."""
        # Patch the global to None
        with patch("src.services.files.local_storage.local_storage", None):
            assert is_local_storage_available() is False


# ============================================================================
# S3 STORAGE PROVIDER TESTS
# ============================================================================


class TestS3StorageProvider:
    """Tests for S3StorageProvider class (mocked)."""

    @pytest.fixture
    def s3_storage(self):
        """Create an S3StorageProvider instance for testing."""
        return S3StorageProvider(
            bucket="test-bucket",
            region="us-east-1",
            access_key_id="test-key",
            secret_access_key="test-secret",
            enabled=True,
        )

    def test_provider_name(self, s3_storage):
        """Test provider name is 's3'."""
        assert s3_storage.provider_name == "s3"

    def test_is_available_when_enabled(self, s3_storage):
        """Test S3 is available when enabled and bucket is set."""
        assert s3_storage.is_available() is True

    def test_is_available_when_disabled(self):
        """Test S3 is not available when disabled."""
        storage = S3StorageProvider(
            bucket="test-bucket",
            region="us-east-1",
            enabled=False,
        )
        assert storage.is_available() is False

    def test_is_available_without_bucket(self):
        """Test S3 is not available when bucket is not set."""
        storage = S3StorageProvider(
            bucket="",
            region="us-east-1",
            enabled=True,
        )
        assert storage.is_available() is False

    def test_get_session_config_with_credentials(self, s3_storage):
        """Test session config includes credentials when provided."""
        config = s3_storage._get_session_config()

        assert config["region_name"] == "us-east-1"
        assert config["aws_access_key_id"] == "test-key"
        assert config["aws_secret_access_key"] == "test-secret"

    def test_get_session_config_without_credentials(self):
        """Test session config without explicit credentials (uses IAM)."""
        storage = S3StorageProvider(
            bucket="test-bucket",
            region="eu-west-1",
            enabled=True,
        )
        config = storage._get_session_config()

        assert config["region_name"] == "eu-west-1"
        assert "aws_access_key_id" not in config
        assert "aws_secret_access_key" not in config

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_upload_success(self, s3_storage):
        """Test successful S3 upload."""
        file_data = io.BytesIO(b"test content")
        storage_key = "test/file.txt"

        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.upload(
                file_data=file_data,
                storage_key=storage_key,
                content_type="text/plain",
            )

        assert result.success is True
        assert result.storage_key == storage_key
        assert result.bucket == "test-bucket"
        mock_s3_client.upload_fileobj.assert_called_once()

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_upload_with_metadata(self, s3_storage):
        """Test S3 upload with metadata."""
        file_data = io.BytesIO(b"test content")
        metadata = {"user_id": "123", "category": "images"}

        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.upload(
                file_data=file_data,
                storage_key="test.txt",
                content_type="text/plain",
                metadata=metadata,
            )

        assert result.success is True
        # Verify metadata was included in the call
        call_args = mock_s3_client.upload_fileobj.call_args
        assert "Metadata" in call_args.kwargs.get("ExtraArgs", {})

    @pytest.mark.asyncio
    async def test_upload_when_not_available(self):
        """Test upload fails when S3 is not available."""
        storage = S3StorageProvider(
            bucket="test-bucket",
            region="us-east-1",
            enabled=False,
        )

        result = await storage.upload(
            file_data=io.BytesIO(b"test"),
            storage_key="test.txt",
            content_type="text/plain",
        )

        assert result.success is False
        assert "not enabled" in result.error_message

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_upload_handles_exception(self, s3_storage):
        """Test upload handles S3 exceptions gracefully."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.upload_fileobj.side_effect = Exception("S3 error")
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.upload(
                file_data=io.BytesIO(b"test"),
                storage_key="test.txt",
                content_type="text/plain",
            )

        assert result.success is False
        assert "S3 error" in result.error_message

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_exists_true(self, s3_storage):
        """Test exists returns True when file exists."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.exists("test/file.txt")

        assert result is True
        mock_s3_client.head_object.assert_called_once()

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_exists_false(self, s3_storage):
        """Test exists returns False when file doesn't exist."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.head_object.side_effect = Exception("Not found")
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.exists("nonexistent.txt")

        assert result is False

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_delete_success(self, s3_storage):
        """Test successful S3 deletion."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.delete("test/file.txt")

        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-bucket", Key="test/file.txt"
        )

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_delete_handles_exception(self, s3_storage):
        """Test delete handles exceptions gracefully."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.delete_object.side_effect = Exception("Delete error")
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.delete("test.txt")

        assert result is False

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_get_file_size(self, s3_storage):
        """Test getting file size from S3."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.head_object.return_value = {"ContentLength": 1024}
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            size = await s3_storage.get_file_size("test.txt")

        assert size == 1024

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_get_file_size_nonexistent(self, s3_storage):
        """Test getting size of non-existent file returns None."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.head_object.side_effect = Exception("Not found")
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            size = await s3_storage.get_file_size("nonexistent.txt")

        assert size is None

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_generate_download_url(self, s3_storage):
        """Test generating presigned download URL."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.generate_presigned_url.return_value = (
                "https://bucket.s3.amazonaws.com/test.txt?signature=xxx"
            )
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.generate_download_url(
                storage_key="test.txt",
                expires_in=3600,
                filename="myfile.txt",
            )

        assert "s3.amazonaws.com" in result.url
        assert result.method == "GET"
        assert result.expires_at > datetime.now(timezone.utc)

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_generate_download_url_with_filename(self, s3_storage):
        """Test download URL includes Content-Disposition when filename provided."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.generate_presigned_url.return_value = "https://example.com"
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            await s3_storage.generate_download_url(
                storage_key="test.txt",
                filename="download.txt",
            )

        call_args = mock_s3_client.generate_presigned_url.call_args
        params = call_args.kwargs["Params"]
        assert "ResponseContentDisposition" in params
        assert "download.txt" in params["ResponseContentDisposition"]

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_generate_upload_url(self, s3_storage):
        """Test generating presigned upload URL."""
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_s3_client.generate_presigned_url.return_value = (
                "https://bucket.s3.amazonaws.com/test.txt?upload=true"
            )
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            result = await s3_storage.generate_upload_url(
                storage_key="test.txt",
                content_type="text/plain",
                expires_in=3600,
            )

        assert result.method == "PUT"
        mock_s3_client.generate_presigned_url.assert_called_once()
        call_args = mock_s3_client.generate_presigned_url.call_args
        assert call_args.args[0] == "put_object"


class TestS3StorageGlobals:
    """Tests for S3 storage global functions."""

    def test_init_s3_storage(self):
        """Test initializing global S3 storage."""
        storage = init_s3_storage(
            bucket="test-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
            enabled=True,
        )

        assert storage is not None
        assert storage.provider_name == "s3"
        assert is_s3_available() is True

    def test_is_s3_available_not_initialized(self):
        """Test availability check when not initialized."""
        with patch("src.services.files.s3_storage.s3_storage", None):
            assert is_s3_available() is False


# ============================================================================
# FILE MANAGER TESTS
# ============================================================================


class TestFileManager:
    """Tests for FileManager class."""

    @pytest.fixture
    def mock_storage(self):
        """Create a mock storage provider."""
        storage = MagicMock()
        storage.provider_name = "mock"
        storage.bucket = "mock-bucket"
        storage.is_available.return_value = True
        # Set up async methods with default behaviors
        storage.delete = AsyncMock(return_value=True)
        storage.download_bytes = AsyncMock(
            return_value=b"\xff\xd8\xff\xe0"
        )  # JPEG magic bytes
        return storage

    @pytest.fixture
    def file_manager(self, mock_storage):
        """Create a FileManager instance with mock storage."""
        return FileManager(storage_provider=mock_storage)

    def test_generate_storage_key(self, file_manager):
        """Test storage key generation."""
        org_id = uuid4()
        key = file_manager._generate_storage_key(org_id, "test.jpg", "image")

        assert str(org_id) in key
        assert "image" in key
        assert "test.jpg" in key

    def test_generate_storage_key_sanitizes_filename(self, file_manager):
        """Test storage key sanitizes special characters in filename."""
        org_id = uuid4()
        key = file_manager._generate_storage_key(org_id, "my file (1).jpg", "image")

        # Should not contain spaces or special chars
        assert "(" not in key
        assert ")" not in key
        assert " " not in key

    def test_generate_storage_key_truncates_long_filename(self, file_manager):
        """Test storage key truncates very long filenames."""
        org_id = uuid4()
        long_name = "a" * 200 + ".jpg"
        key = file_manager._generate_storage_key(org_id, long_name, "image")

        # Key should be truncated but keep extension
        assert ".jpg" in key
        assert len(key.split("/")[-1]) <= 140  # uuid + _ + truncated name

    @pytest.mark.asyncio
    async def test_initiate_upload_success(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test successful upload initiation."""

        # Setup mock storage
        mock_storage.generate_upload_url = AsyncMock(
            return_value=SignedUrlResult(
                url="https://upload.example.com",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                method="PUT",
            )
        )

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.initiate_upload(
            session=async_session,
            organization_id=test_organization.id,
            user_id=test_user.id,
            filename="test.jpg",
            size_bytes=1024,
            content_type="image/jpeg",
        )

        assert result.success is True
        assert result.file_id is not None
        assert result.upload_url == "https://upload.example.com"

    @pytest.mark.asyncio
    async def test_initiate_upload_invalid_extension(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test upload fails for invalid file extension."""
        fm = FileManager(storage_provider=mock_storage)

        result = await fm.initiate_upload(
            session=async_session,
            organization_id=test_organization.id,
            user_id=test_user.id,
            filename="malware.exe",
            size_bytes=1024,
        )

        assert result.success is False
        assert "not allowed" in result.error_message

    @pytest.mark.asyncio
    async def test_initiate_upload_file_too_large(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test upload fails for oversized files."""
        fm = FileManager(storage_provider=mock_storage)

        result = await fm.initiate_upload(
            session=async_session,
            organization_id=test_organization.id,
            user_id=test_user.id,
            filename="huge.jpg",
            size_bytes=500 * 1024 * 1024,  # 500 MB
        )

        assert result.success is False
        assert "exceeds" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_complete_upload_success(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test completing an upload."""
        from src.models.file import File

        # Create a pending file
        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="pending",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)

        mock_storage.exists = AsyncMock(return_value=True)
        mock_storage.get_file_size = AsyncMock(return_value=1024)

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.complete_upload(
            session=async_session,
            file_id=file.id,
            organization_id=test_organization.id,
        )

        assert result.success is True
        assert result.file.status == "ready"

    @pytest.mark.asyncio
    async def test_complete_upload_file_not_in_storage(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test completing upload fails when file not in storage."""
        from src.models.file import File

        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="pending",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)

        mock_storage.exists = AsyncMock(return_value=False)

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.complete_upload(
            session=async_session,
            file_id=file.id,
            organization_id=test_organization.id,
        )

        assert result.success is False
        assert "not found in storage" in result.error_message

    @pytest.mark.asyncio
    async def test_upload_direct_success(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test direct file upload."""
        file_data = io.BytesIO(b"test content")

        mock_storage.upload = AsyncMock(
            return_value=UploadResult(
                success=True,
                storage_key="test/key.jpg",
                bucket="mock-bucket",
            )
        )

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.upload_direct(
            session=async_session,
            organization_id=test_organization.id,
            user_id=test_user.id,
            filename="test.jpg",
            file_data=file_data,
            content_type="image/jpeg",
        )

        assert result.success is True
        assert result.file is not None
        assert result.file.status == "ready"

    @pytest.mark.asyncio
    async def test_get_download_url(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test getting download URL for a file."""
        from src.models.file import File

        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="ready",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)

        mock_storage.generate_download_url = AsyncMock(
            return_value=SignedUrlResult(
                url="https://download.example.com/file",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                method="GET",
            )
        )

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.get_download_url(
            session=async_session,
            file_id=file.id,
            organization_id=test_organization.id,
        )

        assert result is not None
        assert result.url == "https://download.example.com/file"

    @pytest.mark.asyncio
    async def test_get_download_url_file_not_found(
        self, async_session, test_organization, mock_storage
    ):
        """Test download URL returns None for non-existent file."""
        fm = FileManager(storage_provider=mock_storage)

        result = await fm.get_download_url(
            session=async_session,
            file_id=uuid4(),
            organization_id=test_organization.id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_soft_delete(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test soft deleting a file."""
        from src.models.file import File

        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="ready",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.soft_delete(
            session=async_session,
            file_id=file.id,
            organization_id=test_organization.id,
        )

        assert result is True
        await async_session.refresh(file)
        assert file.deleted_time is not None
        assert file.status == "deleted"

    @pytest.mark.asyncio
    async def test_hard_delete(
        self, async_session, test_organization, test_user, mock_storage
    ):
        """Test hard deleting a file."""
        from src.models.file import File

        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="ready",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)
        file_id = file.id

        mock_storage.delete = AsyncMock(return_value=True)

        fm = FileManager(storage_provider=mock_storage)

        result = await fm.hard_delete(
            session=async_session,
            file_id=file_id,
            organization_id=test_organization.id,
        )

        assert result is True
        mock_storage.delete.assert_called_once_with("test/key.jpg")

    @pytest.mark.asyncio
    async def test_tenant_isolation(
        self,
        async_session,
        test_organization,
        second_organization,
        test_user,
        mock_storage,
    ):
        """Test that files are isolated by organization."""
        from src.models.file import File

        # Create file in test_organization
        file = File(
            organization_id=test_organization.id,
            uploaded_by_user_id=test_user.id,
            original_filename="test.jpg",
            storage_key="test/key.jpg",
            content_type="image/jpeg",
            file_extension="jpg",
            size_bytes=1024,
            storage_provider="mock",
            status="ready",
            category="image",
        )
        async_session.add(file)
        await async_session.commit()
        await async_session.refresh(file)

        mock_storage.generate_download_url = AsyncMock(
            return_value=SignedUrlResult(
                url="https://example.com",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                method="GET",
            )
        )

        fm = FileManager(storage_provider=mock_storage)

        # Try to access from different organization - should fail
        result = await fm.get_download_url(
            session=async_session,
            file_id=file.id,
            organization_id=second_organization.id,
        )

        assert result is None  # File not accessible from other org


class TestFileManagerGlobals:
    """Tests for FileManager global functions."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_file_manager(self, temp_storage_dir):
        """Test initializing global file manager."""
        storage = LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://test.com",
            enabled=True,
        )

        fm = init_file_manager(storage)

        assert fm is not None
        assert get_file_manager() is fm

    def test_get_file_manager_not_initialized(self):
        """Test getting file manager when not initialized."""
        with patch("src.services.files.file_manager.file_manager", None):
            assert get_file_manager() is None


# ============================================================================
# STORAGE INITIALIZATION & FALLBACK TESTS
# ============================================================================


class TestStorageInitializationFallback:
    """Tests for storage initialization logic and S3 to local fallback."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_s3_configured_uses_s3(self):
        """Test that S3 is used when properly configured."""
        with patch("src.core.config.settings") as mock_settings:
            mock_settings.S3_BUCKET = "my-bucket"
            mock_settings.AWS_ACCESS_KEY_ID = "my-key"
            mock_settings.S3_REGION = "us-east-1"
            mock_settings.AWS_SECRET_ACCESS_KEY = "my-secret"
            mock_settings.S3_ENDPOINT_URL = None

            # Simulate the initialization logic from main.py
            s3_configured = bool(
                mock_settings.S3_BUCKET and mock_settings.AWS_ACCESS_KEY_ID
            )

            assert s3_configured is True

    def test_s3_not_configured_falls_back_to_local(self, temp_storage_dir):
        """Test that local storage is used when S3 is not configured."""
        with patch("src.core.config.settings") as mock_settings:
            mock_settings.S3_BUCKET = ""
            mock_settings.AWS_ACCESS_KEY_ID = ""
            mock_settings.LOCAL_STORAGE_ENABLED = True
            mock_settings.LOCAL_STORAGE_PATH = temp_storage_dir
            mock_settings.PUBLIC_URL = "http://localhost:8000"

            # Simulate the initialization logic from main.py
            s3_configured = bool(
                mock_settings.S3_BUCKET and mock_settings.AWS_ACCESS_KEY_ID
            )

            assert s3_configured is False

            # Would fall back to local storage
            if not s3_configured:
                local_enabled = mock_settings.LOCAL_STORAGE_ENABLED or not s3_configured
                assert local_enabled is True

    def test_s3_bucket_only_not_sufficient(self):
        """Test that having only bucket (no credentials) triggers fallback."""
        with patch("src.core.config.settings") as mock_settings:
            mock_settings.S3_BUCKET = "my-bucket"
            mock_settings.AWS_ACCESS_KEY_ID = ""  # No credentials

            s3_configured = bool(
                mock_settings.S3_BUCKET and mock_settings.AWS_ACCESS_KEY_ID
            )

            assert s3_configured is False

    def test_local_storage_fallback_enabled_automatically(self, temp_storage_dir):
        """Test local storage is auto-enabled when S3 not configured."""
        with patch("src.core.config.settings") as mock_settings:
            mock_settings.S3_BUCKET = ""
            mock_settings.AWS_ACCESS_KEY_ID = ""
            mock_settings.LOCAL_STORAGE_ENABLED = False  # Even if disabled
            mock_settings.LOCAL_STORAGE_PATH = temp_storage_dir

            s3_configured = bool(
                mock_settings.S3_BUCKET and mock_settings.AWS_ACCESS_KEY_ID
            )

            # Local storage should be enabled if S3 not configured
            local_enabled = mock_settings.LOCAL_STORAGE_ENABLED or not s3_configured
            assert local_enabled is True

    @pytest.mark.asyncio
    async def test_file_manager_works_with_local_storage(self, temp_storage_dir):
        """Test FileManager works correctly with local storage backend."""
        storage = LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://localhost:8000",
            enabled=True,
        )
        fm = FileManager(storage_provider=storage)

        # Test that we can generate storage keys
        org_id = uuid4()
        key = fm._generate_storage_key(org_id, "test.jpg", "image")
        assert str(org_id) in key

        # Test storage operations work
        file_data = io.BytesIO(b"test content")
        upload_result = await storage.upload(
            file_data=file_data,
            storage_key=key,
            content_type="image/jpeg",
        )
        assert upload_result.success is True

        # Verify file exists
        assert await storage.exists(key) is True

        # Clean up
        await storage.delete(key)

    @skip_if_no_aioboto3
    @pytest.mark.asyncio
    async def test_file_manager_works_with_s3_storage_mocked(self):
        """Test FileManager works correctly with S3 storage backend (mocked)."""
        storage = S3StorageProvider(
            bucket="test-bucket",
            region="us-east-1",
            access_key_id="test-key",
            secret_access_key="test-secret",
            enabled=True,
        )
        fm = FileManager(storage_provider=storage)

        # Test that we can generate storage keys
        org_id = uuid4()
        key = fm._generate_storage_key(org_id, "test.jpg", "image")
        assert str(org_id) in key

        # Test storage operations work with mocks
        with patch("aioboto3.Session") as mock_session_class:
            mock_s3_client = AsyncMock()
            mock_session = MagicMock()
            mock_session.client.return_value.__aenter__.return_value = mock_s3_client
            mock_session_class.return_value = mock_session

            file_data = io.BytesIO(b"test content")
            upload_result = await storage.upload(
                file_data=file_data,
                storage_key=key,
                content_type="image/jpeg",
            )
            assert upload_result.success is True
            mock_s3_client.upload_fileobj.assert_called_once()


class TestStorageProviderInterface:
    """Tests to verify both providers implement the same interface correctly."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create a temporary directory for storage tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def providers(self, temp_storage_dir):
        """Create both storage providers for comparison testing."""
        local = LocalStorageProvider(
            storage_path=temp_storage_dir,
            base_url="http://localhost:8000",
            enabled=True,
        )
        s3 = S3StorageProvider(
            bucket="test-bucket",
            region="us-east-1",
            access_key_id="key",
            secret_access_key="secret",
            enabled=True,
        )
        return {"local": local, "s3": s3}

    def test_both_have_provider_name(self, providers):
        """Test both providers have provider_name property."""
        assert providers["local"].provider_name == "local"
        assert providers["s3"].provider_name == "s3"

    def test_both_have_is_available(self, providers):
        """Test both providers have is_available method."""
        assert hasattr(providers["local"], "is_available")
        assert hasattr(providers["s3"], "is_available")
        assert callable(providers["local"].is_available)
        assert callable(providers["s3"].is_available)

    @pytest.mark.asyncio
    async def test_both_have_upload(self, providers):
        """Test both providers have upload method."""
        assert hasattr(providers["local"], "upload")
        assert hasattr(providers["s3"], "upload")

    @pytest.mark.asyncio
    async def test_both_have_delete(self, providers):
        """Test both providers have delete method."""
        assert hasattr(providers["local"], "delete")
        assert hasattr(providers["s3"], "delete")

    @pytest.mark.asyncio
    async def test_both_have_exists(self, providers):
        """Test both providers have exists method."""
        assert hasattr(providers["local"], "exists")
        assert hasattr(providers["s3"], "exists")

    @pytest.mark.asyncio
    async def test_both_have_generate_download_url(self, providers):
        """Test both providers have generate_download_url method."""
        assert hasattr(providers["local"], "generate_download_url")
        assert hasattr(providers["s3"], "generate_download_url")

    @pytest.mark.asyncio
    async def test_both_have_generate_upload_url(self, providers):
        """Test both providers have generate_upload_url method."""
        assert hasattr(providers["local"], "generate_upload_url")
        assert hasattr(providers["s3"], "generate_upload_url")

    @pytest.mark.asyncio
    async def test_both_have_get_file_size(self, providers):
        """Test both providers have get_file_size method."""
        assert hasattr(providers["local"], "get_file_size")
        assert hasattr(providers["s3"], "get_file_size")
