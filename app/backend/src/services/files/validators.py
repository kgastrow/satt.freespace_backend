"""
File validation service for type and size checks.
"""

from dataclasses import dataclass
import mimetypes
from typing import Any, BinaryIO, Optional, Union
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger
from src.models.organization_file_settings import OrganizationFileSettings


# Default allowed extensions
DEFAULT_ALLOWED_EXTENSIONS: set[str] = {
    # Images
    "jpg",
    "jpeg",
    "png",
    "gif",
    "webp",
    "svg",
    "bmp",
    "ico",
    # Documents
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "odt",
    "ods",
    "odp",
    # Videos
    "mp4",
    "mov",
    "avi",
    "webm",
    "mkv",
    "m4v",
    # Audio
    "mp3",
    "wav",
    "ogg",
    "m4a",
    "flac",
    # Other
    "zip",
    "txt",
    "csv",
    "json",
    "xml",
    "html",
    "css",
    "js",
}

# Default size limits
DEFAULT_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
DEFAULT_MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100 MB

# File categories based on extension
FILE_CATEGORIES = {
    "image": {"jpg", "jpeg", "png", "gif", "webp", "svg", "bmp", "ico"},
    "video": {"mp4", "mov", "avi", "webm", "mkv", "m4v"},
    "audio": {"mp3", "wav", "ogg", "m4a", "flac"},
    "document": {
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "odt",
        "ods",
        "odp",
        "txt",
        "csv",
    },
    "other": {"zip", "json", "xml", "html", "css", "js"},
}

# Mapping of MIME type prefixes/patterns to allowed extensions
# Used for magic byte validation
MIME_TO_EXTENSIONS: dict[str, set[str]] = {
    # Images
    "image/jpeg": {"jpg", "jpeg"},
    "image/png": {"png"},
    "image/gif": {"gif"},
    "image/webp": {"webp"},
    "image/svg+xml": {"svg"},
    "image/bmp": {"bmp"},
    "image/x-icon": {"ico"},
    "image/vnd.microsoft.icon": {"ico"},
    # Videos
    "video/mp4": {"mp4", "m4v"},
    "video/quicktime": {"mov"},
    "video/x-msvideo": {"avi"},
    "video/webm": {"webm"},
    "video/x-matroska": {"mkv"},
    # Audio
    "audio/mpeg": {"mp3"},
    "audio/wav": {"wav"},
    "audio/x-wav": {"wav"},
    "audio/ogg": {"ogg"},
    "audio/mp4": {"m4a"},
    "audio/x-m4a": {"m4a"},
    "audio/flac": {"flac"},
    # Documents
    "application/pdf": {"pdf"},
    "application/msword": {"doc"},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {"docx"},
    "application/vnd.ms-excel": {"xls"},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {"xlsx"},
    "application/vnd.ms-powerpoint": {"ppt"},
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": {
        "pptx"
    },
    "application/vnd.oasis.opendocument.text": {"odt"},
    "application/vnd.oasis.opendocument.spreadsheet": {"ods"},
    "application/vnd.oasis.opendocument.presentation": {"odp"},
    # Archives
    "application/zip": {"zip", "docx", "xlsx", "pptx", "odt", "ods", "odp"},
    "application/x-zip-compressed": {
        "zip",
        "docx",
        "xlsx",
        "pptx",
        "odt",
        "ods",
        "odp",
    },
    # Text
    "text/plain": {"txt", "csv", "json", "xml", "html", "css", "js"},
    "text/csv": {"csv"},
    "text/html": {"html"},
    "text/css": {"css"},
    "text/javascript": {"js"},
    "application/javascript": {"js"},
    "application/json": {"json"},
    "text/xml": {"xml"},
    "application/xml": {"xml"},
}


@dataclass
class ValidationResult:
    """Result of file validation."""

    valid: bool
    error_message: Optional[str] = None
    category: Optional[str] = None
    content_type: Optional[str] = None


class FileValidator:
    """Validates files based on type, size, and organization settings."""

    def __init__(self) -> None:
        """Initialize the file validator."""
        self._magic_available = False
        self._magic: Any = None
        try:
            import magic

            self._magic = magic
            self._magic_available = True
        except ImportError:
            Logger.warning(
                "python-magic not available, content type validation will be limited"
            )

    def get_file_extension(self, filename: str) -> str:
        """Extract lowercase file extension from filename."""
        if "." in filename:
            return filename.rsplit(".", 1)[1].lower()
        return ""

    def get_content_type(self, filename: str) -> str:
        """Get MIME type for a filename."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    def get_file_category(self, extension: str) -> str:
        """Determine the category of a file based on its extension."""
        ext = extension.lower()
        for category, extensions in FILE_CATEGORIES.items():
            if ext in extensions:
                return category
        return "other"

    def detect_content_type_from_bytes(self, file_data: bytes) -> Optional[str]:
        """
        Detect the actual content type of file data using magic bytes.

        Args:
            file_data: The raw bytes of the file (at least first 2048 bytes recommended)

        Returns:
            Detected MIME type or None if detection fails
        """
        if not self._magic_available or self._magic is None:
            return None

        try:
            detected_type = self._magic.from_buffer(file_data, mime=True)
            return detected_type
        except Exception as e:
            Logger.warning(f"Magic byte detection failed: {e}")
            return None

    def validate_content_type_by_magic_bytes(
        self, filename: str, file_data: BinaryIO
    ) -> ValidationResult:
        """
        Validate that file content matches its extension using magic bytes.

        Args:
            filename: The filename with extension
            file_data: File-like object to read bytes from

        Returns:
            ValidationResult with validity and error message
        """
        if not self._magic_available:
            # If magic is not available, skip this validation
            Logger.warning("Magic byte validation skipped - python-magic not available")
            return ValidationResult(valid=True)

        extension = self.get_file_extension(filename)
        if not extension:
            return ValidationResult(
                valid=False, error_message="File must have an extension"
            )

        # Read first 2048 bytes for magic detection
        original_position = file_data.tell()
        header_bytes = file_data.read(2048)
        file_data.seek(original_position)  # Reset position

        if not header_bytes:
            return ValidationResult(
                valid=False, error_message="File is empty or unreadable"
            )

        detected_type = self.detect_content_type_from_bytes(header_bytes)
        if detected_type is None:
            # Detection failed, log warning but allow upload
            Logger.warning(f"Could not detect content type for {filename}")
            return ValidationResult(valid=True)

        # Check if detected type allows this extension
        allowed_extensions = MIME_TO_EXTENSIONS.get(detected_type, set())

        # Handle generic types that can't be validated
        generic_types = {
            "application/octet-stream",
            "application/x-empty",
            "inode/x-empty",
        }
        if detected_type in generic_types:
            return ValidationResult(valid=True)

        # For text types, be more permissive as magic detection can be imprecise
        if detected_type.startswith("text/"):
            text_extensions = {"txt", "csv", "json", "xml", "html", "css", "js"}
            if extension in text_extensions:
                return ValidationResult(valid=True)

        if extension in allowed_extensions:
            return ValidationResult(valid=True)

        # Check for common acceptable variations
        # Office documents are zip-based, so zip detection is acceptable
        zip_based_extensions = {"docx", "xlsx", "pptx", "odt", "ods", "odp"}
        if detected_type in {"application/zip", "application/x-zip-compressed"}:
            if extension in zip_based_extensions or extension == "zip":
                return ValidationResult(valid=True)

        return ValidationResult(
            valid=False,
            error_message=f"File content does not match extension '.{extension}' (detected type: {detected_type})",
        )

    def validate_extension(
        self, filename: str, allowed_extensions: Optional[set[str]] = None
    ) -> ValidationResult:
        """
        Validate that a file extension is allowed.

        Args:
            filename: The filename to validate
            allowed_extensions: Set of allowed extensions (uses default if None)

        Returns:
            ValidationResult with validity and error message
        """
        if allowed_extensions is None:
            allowed_extensions = DEFAULT_ALLOWED_EXTENSIONS

        extension = self.get_file_extension(filename)
        if not extension:
            return ValidationResult(
                valid=False, error_message="File must have an extension"
            )

        if extension not in allowed_extensions:
            return ValidationResult(
                valid=False, error_message=f"File type '.{extension}' is not allowed"
            )

        category = self.get_file_category(extension)
        content_type = self.get_content_type(filename)

        return ValidationResult(
            valid=True, category=category, content_type=content_type
        )

    def validate_size(
        self,
        size_bytes: int,
        category: str,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_video_size: int = DEFAULT_MAX_VIDEO_SIZE,
    ) -> ValidationResult:
        """
        Validate file size against limits.

        Args:
            size_bytes: Size of the file in bytes
            category: File category (video, image, etc.)
            max_file_size: Maximum size for non-video files
            max_video_size: Maximum size for video files

        Returns:
            ValidationResult with validity and error message
        """
        if size_bytes <= 0:
            return ValidationResult(
                valid=False, error_message="File size must be greater than 0"
            )

        max_size = max_video_size if category == "video" else max_file_size

        if size_bytes > max_size:
            max_mb = max_size / (1024 * 1024)
            actual_mb = size_bytes / (1024 * 1024)
            return ValidationResult(
                valid=False,
                error_message=f"File size ({actual_mb:.1f}MB) exceeds maximum allowed ({max_mb:.1f}MB)",
            )

        return ValidationResult(valid=True, category=category)

    async def validate_file(
        self,
        session: AsyncSession,
        organization_id: Union[str, UUID],
        filename: str,
        size_bytes: int,
    ) -> ValidationResult:
        """
        Validate a file against organization settings.

        Args:
            session: Database session
            organization_id: Organization to validate against
            filename: Name of the file
            size_bytes: Size of the file in bytes

        Returns:
            ValidationResult with validity, error message, and file category
        """
        # Get organization settings
        org_id = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        result = await session.execute(
            select(OrganizationFileSettings).where(
                OrganizationFileSettings.organization_id == org_id
            )
        )
        settings = result.scalar_one_or_none()

        # Determine allowed extensions
        if settings and settings.allowed_extensions:
            allowed_extensions = set(settings.allowed_extensions)
        else:
            allowed_extensions = DEFAULT_ALLOWED_EXTENSIONS

        # Validate extension
        ext_result = self.validate_extension(filename, allowed_extensions)
        if not ext_result.valid:
            return ext_result

        # Get size limits from settings
        max_file_size = (
            settings.max_file_size_bytes if settings else DEFAULT_MAX_FILE_SIZE
        )
        max_video_size = (
            settings.max_video_size_bytes if settings else DEFAULT_MAX_VIDEO_SIZE
        )

        # Validate size
        size_result = self.validate_size(
            size_bytes, ext_result.category or "other", max_file_size, max_video_size
        )
        if not size_result.valid:
            return size_result

        return ValidationResult(
            valid=True,
            category=ext_result.category,
            content_type=ext_result.content_type,
        )

    def validate_content_type_matches_extension(
        self, filename: str, actual_content_type: str
    ) -> ValidationResult:
        """
        Validate that actual content type matches the file extension.
        This helps prevent disguised malicious files.

        Args:
            filename: The filename
            actual_content_type: The actual MIME type of the file content

        Returns:
            ValidationResult with validity and error message
        """
        expected_type = self.get_content_type(filename)

        # Normalize content types for comparison
        expected_base = expected_type.split(";")[0].strip()
        actual_base = actual_content_type.split(";")[0].strip()

        # Allow some flexibility for common mismatches
        type_equivalents = {
            "text/plain": {"text/csv", "application/csv"},
            "application/octet-stream": set(),  # Generic type, allow all
        }

        if expected_base == actual_base:
            return ValidationResult(valid=True)

        if expected_base in type_equivalents:
            if actual_base in type_equivalents[expected_base]:
                return ValidationResult(valid=True)

        # For application/octet-stream, we can't verify so allow it
        if actual_base == "application/octet-stream":
            return ValidationResult(valid=True)

        return ValidationResult(
            valid=False,
            error_message=f"Content type mismatch: expected {expected_base}, got {actual_base}",
        )


# Global validator instance
file_validator = FileValidator()
