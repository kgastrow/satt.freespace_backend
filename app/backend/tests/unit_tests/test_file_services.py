"""
Unit tests for file services.
"""

import pytest

from src.services.files.usage_tracker import UsageTracker
from src.services.files.validators import (
    FileValidator,
)


class TestFileValidator:
    """Tests for FileValidator class."""

    def test_get_file_extension(self):
        """Test file extension extraction."""
        validator = FileValidator()

        assert validator.get_file_extension("test.jpg") == "jpg"
        assert validator.get_file_extension("test.PDF") == "pdf"
        assert validator.get_file_extension("archive.tar.gz") == "gz"
        assert validator.get_file_extension("noextension") == ""
        assert validator.get_file_extension("") == ""

    def test_get_content_type(self):
        """Test MIME type detection."""
        validator = FileValidator()

        assert validator.get_content_type("test.jpg") == "image/jpeg"
        assert validator.get_content_type("test.png") == "image/png"
        assert validator.get_content_type("test.pdf") == "application/pdf"
        assert validator.get_content_type("test.mp4") == "video/mp4"
        # .xyz has a known MIME type in some systems, use truly unknown extension
        result = validator.get_content_type("unknown.zzzzz")
        assert result == "application/octet-stream"

    def test_get_file_category(self):
        """Test file category determination."""
        validator = FileValidator()

        assert validator.get_file_category("jpg") == "image"
        assert validator.get_file_category("png") == "image"
        assert validator.get_file_category("mp4") == "video"
        assert validator.get_file_category("mov") == "video"
        assert validator.get_file_category("pdf") == "document"
        assert validator.get_file_category("docx") == "document"
        assert validator.get_file_category("mp3") == "audio"
        assert validator.get_file_category("wav") == "audio"
        assert validator.get_file_category("zip") == "other"
        assert validator.get_file_category("xyz") == "other"

    def test_validate_extension_allowed(self):
        """Test extension validation with allowed extension."""
        validator = FileValidator()

        result = validator.validate_extension("photo.jpg")
        assert result.valid is True
        assert result.category == "image"
        assert result.content_type == "image/jpeg"

    def test_validate_extension_not_allowed(self):
        """Test extension validation with disallowed extension."""
        validator = FileValidator()

        result = validator.validate_extension("script.exe")
        assert result.valid is False
        assert "not allowed" in result.error_message

    def test_validate_extension_custom_allowed(self):
        """Test extension validation with custom allowed list."""
        validator = FileValidator()

        # Only allow txt
        result = validator.validate_extension("doc.pdf", allowed_extensions={"txt"})
        assert result.valid is False

        result = validator.validate_extension("readme.txt", allowed_extensions={"txt"})
        assert result.valid is True

    def test_validate_extension_no_extension(self):
        """Test validation of file with no extension."""
        validator = FileValidator()

        result = validator.validate_extension("noextension")
        assert result.valid is False
        assert "must have an extension" in result.error_message

    def test_validate_size_valid(self):
        """Test size validation with valid size."""
        validator = FileValidator()

        # 10 MB file for image
        result = validator.validate_size(10 * 1024 * 1024, "image")
        assert result.valid is True

    def test_validate_size_too_large(self):
        """Test size validation with file too large."""
        validator = FileValidator()

        # 200 MB file (exceeds 100 MB default)
        result = validator.validate_size(200 * 1024 * 1024, "image")
        assert result.valid is False
        assert "exceeds maximum" in result.error_message

    def test_validate_size_video(self):
        """Test size validation for video files."""
        validator = FileValidator()

        # 90 MB video (under 100 MB limit)
        result = validator.validate_size(
            90 * 1024 * 1024, "video", max_video_size=100 * 1024 * 1024
        )
        assert result.valid is True

        # 150 MB video (exceeds 100 MB limit)
        result = validator.validate_size(
            150 * 1024 * 1024, "video", max_video_size=100 * 1024 * 1024
        )
        assert result.valid is False

    def test_validate_size_zero(self):
        """Test validation of zero-size file."""
        validator = FileValidator()

        result = validator.validate_size(0, "document")
        assert result.valid is False
        assert "greater than 0" in result.error_message

    def test_validate_content_type_matches_extension(self):
        """Test content type matching."""
        validator = FileValidator()

        # Matching types
        result = validator.validate_content_type_matches_extension(
            "test.jpg", "image/jpeg"
        )
        assert result.valid is True

        # Mismatched types
        result = validator.validate_content_type_matches_extension(
            "test.jpg", "application/pdf"
        )
        assert result.valid is False

        # Generic type is allowed
        result = validator.validate_content_type_matches_extension(
            "test.jpg", "application/octet-stream"
        )
        assert result.valid is True


class TestUsageTracker:
    """Tests for UsageTracker class."""

    @pytest.mark.asyncio
    async def test_get_or_create_user_usage(
        self, async_session, test_organization, test_user
    ):
        """Test getting or creating user usage record."""
        tracker = UsageTracker()

        # First call should create
        usage = await tracker.get_or_create_user_usage(
            async_session, test_organization.id, test_user.id
        )
        assert usage is not None
        assert usage.total_files == 0
        assert usage.total_size_bytes == 0

        # Second call should return existing
        usage2 = await tracker.get_or_create_user_usage(
            async_session, test_organization.id, test_user.id
        )
        assert usage2.id == usage.id

    @pytest.mark.asyncio
    async def test_check_user_quota_allowed(
        self, async_session, test_organization, test_user
    ):
        """Test quota check when upload is allowed."""
        tracker = UsageTracker()

        result = await tracker.check_user_quota(
            async_session,
            test_organization.id,
            test_user.id,
            additional_bytes=1024 * 1024,  # 1 MB
        )
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_record_upload(self, async_session, test_organization, test_user):
        """Test recording a file upload."""
        tracker = UsageTracker()

        # Record an image upload
        usage = await tracker.record_upload(
            async_session,
            test_organization.id,
            test_user.id,
            size_bytes=1024 * 1024,  # 1 MB
            category="image",
        )

        assert usage.total_files == 1
        assert usage.total_size_bytes == 1024 * 1024
        assert usage.image_count == 1
        assert usage.image_size_bytes == 1024 * 1024
        assert usage.video_count == 0

        # Record a video upload
        usage = await tracker.record_upload(
            async_session,
            test_organization.id,
            test_user.id,
            size_bytes=10 * 1024 * 1024,  # 10 MB
            category="video",
        )

        assert usage.total_files == 2
        assert usage.total_size_bytes == 11 * 1024 * 1024
        assert usage.image_count == 1
        assert usage.video_count == 1
        assert usage.video_size_bytes == 10 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_record_deletion(self, async_session, test_organization, test_user):
        """Test recording a file deletion."""
        tracker = UsageTracker()

        # First record an upload
        await tracker.record_upload(
            async_session,
            test_organization.id,
            test_user.id,
            size_bytes=1024 * 1024,
            category="document",
        )

        # Then record a deletion
        usage = await tracker.record_deletion(
            async_session,
            test_organization.id,
            test_user.id,
            size_bytes=1024 * 1024,
            category="document",
        )

        assert usage.total_files == 0
        assert usage.total_size_bytes == 0
        assert usage.document_count == 0

    @pytest.mark.asyncio
    async def test_get_user_usage_stats(
        self, async_session, test_organization, test_user
    ):
        """Test getting user usage statistics."""
        tracker = UsageTracker()

        # Record some uploads
        await tracker.record_upload(
            async_session, test_organization.id, test_user.id, 1000, "image"
        )
        await tracker.record_upload(
            async_session, test_organization.id, test_user.id, 2000, "video"
        )
        await tracker.record_upload(
            async_session, test_organization.id, test_user.id, 3000, "document"
        )

        stats = await tracker.get_user_usage_stats(
            async_session, test_organization.id, test_user.id
        )

        assert stats.total_files == 3
        assert stats.total_size_bytes == 6000
        assert stats.image_count == 1
        assert stats.image_size_bytes == 1000
        assert stats.video_count == 1
        assert stats.video_size_bytes == 2000
        assert stats.document_count == 1
        assert stats.document_size_bytes == 3000
