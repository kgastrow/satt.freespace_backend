"""
Local file serving endpoint.
Serves files from local storage with authentication.
Supports public files that can be accessed without authentication.
"""

import mimetypes
from typing import Annotated, Optional
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_session
from src.core.exceptions import create_http_exception
from src.core.security import decode_file_access_token
from src.models.file import File
from src.services.files.file_manager import get_file_manager
from src.services.files.local_storage import LocalStorageProvider


router = APIRouter(prefix="/files", tags=["files"])

# MIME types that are considered safe for inline display
# All other types will be forced as attachment downloads (CWE-436 mitigation)
SAFE_INLINE_MIME_TYPES = frozenset(
    [
        # Images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/bmp",
        # Documents (PDF is common for inline viewing)
        "application/pdf",
        # Plain text
        "text/plain",
    ]
)


class SecureFileResponse(FileResponse):
    """
    FileResponse with security headers to prevent XSS and MIME type attacks.

    Adds:
    - X-Content-Type-Options: nosniff - Prevents MIME type sniffing
    - Content-Disposition: attachment for unsafe MIME types
    """

    def __init__(
        self,
        path,
        media_type=None,
        filename=None,
        force_attachment=False,
        **kwargs,
    ):
        super().__init__(
            path=path,
            media_type=media_type,
            filename=filename,
            **kwargs,
        )

        # Always add nosniff header to prevent MIME type sniffing (CWE-436)
        self.headers["X-Content-Type-Options"] = "nosniff"

        # Force attachment download for unsafe MIME types to prevent XSS
        if force_attachment or media_type not in SAFE_INLINE_MIME_TYPES:
            # Ensure Content-Disposition is attachment
            if filename:
                self.headers["Content-Disposition"] = (
                    f'attachment; filename="{filename}"'
                )
            else:
                self.headers["Content-Disposition"] = "attachment"


@router.get("/serve/{storage_key:path}")
async def serve_file(
    storage_key: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    token: Optional[str] = Query(
        None, description="File access token for browser requests"
    ),
):
    """
    Serve a file from local storage.

    This endpoint directly serves files stored locally. Authentication is handled as follows:
    1. Public files (is_public=True): No authentication required
    2. Private files: Require a signed file access token in the query parameter

    The storage_key format is: {org_id}/{category}/{uuid}_{filename}
    """
    # URL-decode the storage key
    storage_key = unquote(storage_key)

    # Validate file manager is available
    file_manager = get_file_manager()
    if file_manager is None:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File manager not initialized",
            detail_code="file.service_unavailable",
        )

    # Check if we're using local storage
    if not isinstance(file_manager.storage, LocalStorageProvider):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local file serving is only available with local storage",
            detail_code="file.invalid_storage_provider",
        )

    # Extract organization ID from storage key (format: {org_id}/{category}/{uuid}_{filename})
    try:
        key_parts = storage_key.split("/")
        if len(key_parts) < 2:
            raise ValueError("Invalid storage key format")
        file_org_id = key_parts[0]
    except (ValueError, IndexError):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage key format",
            detail_code="common.validation_error",
        )

    # Look up the file to check if it's public
    file_record = await session.scalar(
        select(File).where(
            File.storage_key == storage_key,
            File.deleted_time.is_(None),
        )
    )

    is_public_file = file_record is not None and file_record.is_public

    # For private files, require and validate token
    if not is_public_file:
        if not token:
            raise create_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="File access token required",
                detail_code="common.unauthorized",
            )

        # Validate the file access token
        try:
            token_data = decode_file_access_token(token)
        except ValueError as e:
            raise create_http_exception(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e),
                detail_code="common.unauthorized",
            )

        # Verify the token is for this specific file
        if token_data.get("storage_key") != storage_key:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token not valid for this file",
                detail_code="common.forbidden",
            )

        token_org_id = token_data.get("organization_id")

        # Validate organization ownership matches token
        if token_org_id != file_org_id:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file",
                detail_code="common.forbidden",
            )

    # Get the file path from local storage
    # This will raise ValueError if path traversal is detected (CWE-22 mitigation)
    local_storage: LocalStorageProvider = file_manager.storage
    try:
        file_path = local_storage.get_file_path_for_streaming(storage_key)
    except ValueError:
        # Path traversal detected - log and return generic error
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid storage key",
            detail_code="common.validation_error",
        )

    if file_path is None:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
            detail_code="file.not_found",
        )

    # For private files with token, re-validate organization after path resolution (CWE-639 mitigation)
    if not is_public_file:
        resolved_relative = file_path.relative_to(local_storage.storage_path)
        resolved_parts = resolved_relative.parts
        if len(resolved_parts) < 1 or resolved_parts[0] != token_data.get(
            "organization_id"
        ):
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this file",
                detail_code="common.forbidden",
            )

    # Extract filename from storage key for Content-Disposition
    # Format: {org_id}/{category}/{uuid}_{filename}
    try:
        filename_part = key_parts[-1]  # {uuid}_{filename}
        # Find the first underscore after the UUID and get everything after it
        underscore_idx = filename_part.find("_")
        if underscore_idx != -1:
            original_filename = filename_part[underscore_idx + 1 :]
        else:
            original_filename = filename_part
    except (ValueError, IndexError):
        original_filename = "download"

    # Determine content type from file extension
    content_type, _ = mimetypes.guess_type(str(file_path))
    if content_type is None:
        content_type = "application/octet-stream"

    # Use SecureFileResponse with security headers (CWE-436 mitigation)
    return SecureFileResponse(
        path=file_path,
        media_type=content_type,
        filename=original_filename,
    )
