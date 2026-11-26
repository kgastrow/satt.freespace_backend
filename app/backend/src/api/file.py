"""
File Management API endpoints.
Handles file uploads, downloads, and management with multi-tenancy support.
"""

import traceback
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.api.deps import (
    CurrentUser,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.query_params import get_pagination_params, parse_filters, parse_sort
from src.core.response_codes import get_response_code
from src.crud.file import (
    get_file_by_id,
    get_files,
    soft_delete_file,
)
from src.crud.file_settings import (
    get_file_settings as get_organization_file_settings,
)
from src.crud.file_settings import (
    update_file_settings as update_organization_file_settings,
)
from src.crud.file_usage import (
    get_organization_usage as get_organization_file_usage,
)
from src.crud.file_usage import (
    get_user_usage as get_user_file_usage,
)
from src.logger.logger import Logger
from src.models.file import MediaUse as MediaUseModel
from src.serialisers.file import (
    DeleteFileResponse,
    DownloadUrlResponse,
    FileListResponse,
    FileResponse,
    FileSettingsResponse,
    FileUsageResponse,
    MediaUse,
    OrganizationFileUsageResponse,
    ThumbnailUrlResponse,
    UpdateFileSettingsRequest,
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadUrlRequest,
    UploadUrlResponse,
)
from src.services.files.file_manager import get_file_manager
from src.services.files.validators import file_validator


router = APIRouter(prefix="/files", tags=["files"])


# DSL configuration for file listing
ALLOWED_FILTERS = {"category", "status", "user_id"}
ALLOWED_SORTS = {"created_time", "original_filename", "size_bytes"}
FILE_FIELD_MAPPING = {
    "user_id": "uploaded_by_user_id",
    "file_name": "original_filename",
}


# ============================================================================
# Helper Functions
# ============================================================================


def _get_file_category(content_type: str, extension: str) -> str:
    """Determine file category based on content type and extension."""
    if content_type.startswith("image/"):
        return "image"
    elif content_type.startswith("video/"):
        return "video"
    elif content_type.startswith("audio/"):
        return "audio"
    elif content_type in [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ] or extension in [
        "pdf",
        "doc",
        "docx",
        "xls",
        "xlsx",
        "ppt",
        "pptx",
        "txt",
        "csv",
    ]:
        return "document"
    return "other"


async def _validate_file_upload(
    session: AsyncSession,
    organization_id: str,
    content_type: str,
    size_bytes: int,
    filename: str,
) -> None:
    """Validate file upload against organization settings."""
    file_settings = await get_organization_file_settings(session, organization_id)

    # Get file extension
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Validate extension
    if file_settings and file_settings.allowed_extensions:
        if extension not in file_settings.allowed_extensions:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '{extension}' is not allowed",
                detail_code="file.invalid_type",
            )

    # Validate size
    max_size = (
        file_settings.max_file_size_bytes if file_settings else 104857600
    )  # 100MB default

    # For videos, use video-specific limit
    if content_type.startswith("video/"):
        max_size = file_settings.max_video_size_bytes if file_settings else 104857600

    if size_bytes > max_size:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds maximum allowed size of {max_size} bytes",
            detail_code="file.too_large",
        )


def _can_delete_file(
    current_user: CurrentUser,
    file_uploaded_by_user_id: UUID,
) -> bool:
    """
    Check if the current user can delete a file.

    Users can delete files if:
    - They uploaded the file themselves, OR
    - They have the 'files:delete_others' permission
    """
    # Check if user is the uploader
    if str(current_user.id) == str(file_uploaded_by_user_id):
        return True

    # Check if user has permission to delete others' files
    if hasattr(current_user, "permissions") and current_user.permissions:
        if "files:delete_others" in current_user.permissions:
            return True
        # Also allow files:admin permission
        if "files:admin" in current_user.permissions:
            return True

    return False


# ============================================================================
# Upload Endpoints
# ============================================================================


@router.post(
    "/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED
)
async def upload_file_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    file: UploadFile = File(...),
    media_use: Optional[MediaUse] = Form(
        None, description="Media use case (avatar, announcement, help_article, other)"
    ),
    is_public: bool = Form(
        False,
        description="Whether the file should be publicly accessible without authentication",
    ),
):
    """
    Upload a file directly.

    Accepts multipart form data with the file, optional media_use, and is_public flag.
    Validates file type and size against organization settings.
    Also validates file content matches the declared extension using magic bytes.
    For image files, a thumbnail is automatically generated.
    Public files can be accessed without authentication (e.g., help center images).
    """
    organization_id = current_user.organization_id

    if not file.filename:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
            detail_code="common.validation_error",
        )

    # Get file size
    file.file.seek(0, 2)  # Seek to end
    size_bytes = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    content_type = file.content_type or "application/octet-stream"

    # Validate file metadata (extension, size)
    await _validate_file_upload(
        session=session,
        organization_id=organization_id,
        content_type=content_type,
        size_bytes=size_bytes,
        filename=file.filename,
    )

    # Validate file content matches extension using magic bytes (security fix)
    magic_validation = file_validator.validate_content_type_by_magic_bytes(
        filename=file.filename,
        file_data=file.file,
    )
    if not magic_validation.valid:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=magic_validation.error_message or "File content validation failed",
            detail_code="file.content_mismatch",
        )

    try:
        fm = get_file_manager()
        if fm is None:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service unavailable",
                detail_code="file.service_unavailable",
            )

        # Convert serializer enum to model enum if provided
        media_use_model = MediaUseModel(media_use.value) if media_use else None

        # Upload file using file manager (direct upload)
        upload_result = await fm.upload_direct(
            session=session,
            organization_id=organization_id,
            user_id=current_user.id,
            filename=file.filename,
            file_data=file.file,
            content_type=content_type,
            media_use=media_use_model,
            is_public=is_public,
        )

        if not upload_result.success:
            raise create_http_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=upload_result.error_message or "Failed to upload file",
                detail_code="common.internal_error",
            )

        return FileResponse.model_validate(upload_result.file)

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"File upload failed: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload file",
            detail_code="common.internal_error",
        )


@router.post("/upload-url", response_model=UploadUrlResponse)
async def get_presigned_upload_url(
    http_request: Request,
    request: UploadUrlRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a presigned URL for direct S3 upload.

    Returns a URL that can be used to upload the file directly to S3.
    After upload, call /upload-complete to confirm.
    """
    organization_id = current_user.organization_id

    # Validate file
    await _validate_file_upload(
        session=session,
        organization_id=organization_id,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        filename=request.filename,
    )

    try:
        fm = get_file_manager()
        if fm is None:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service unavailable",
                detail_code="file.service_unavailable",
            )

        # Convert serializer enum to model enum if provided
        media_use_model = (
            MediaUseModel(request.media_use.value) if request.media_use else None
        )

        # Use file manager to initiate upload (creates pending file and generates presigned URL)
        init_result = await fm.initiate_upload(
            session=session,
            organization_id=organization_id,
            user_id=current_user.id,
            filename=request.filename,
            size_bytes=request.size_bytes,
            content_type=request.content_type,
            media_use=media_use_model,
            is_public=request.is_public,
        )

        if not init_result.success:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=init_result.error_message or "Failed to initiate upload",
                detail_code="common.validation_error",
            )

        # These are guaranteed to be set when success is True
        if (
            init_result.upload_url is None
            or init_result.storage_key is None
            or init_result.upload_url_expires_at is None
            or init_result.file_id is None
        ):
            raise create_http_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate upload URL",
                detail_code="common.internal_error",
            )

        return UploadUrlResponse(
            upload_url=init_result.upload_url,
            storage_key=init_result.storage_key,
            expires_at=init_result.upload_url_expires_at,
            file_id=init_result.file_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to generate upload URL: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
            detail_code="common.internal_error",
        )


@router.post("/upload-complete", response_model=UploadCompleteResponse)
async def confirm_upload_complete(
    request: UploadCompleteRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Confirm that a presigned URL upload has completed.

    Verifies the file exists in storage and updates status to 'ready'.
    Also validates file content matches the declared extension.
    Records usage statistics.
    """
    organization_id = current_user.organization_id

    fm = get_file_manager()
    if fm is None:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage service unavailable",
            detail_code="file.service_unavailable",
        )

    # Use file manager to complete upload (verifies in storage, validates content, updates status, records usage)
    result = await fm.complete_upload(
        session=session,
        file_id=str(request.file_id),
        organization_id=organization_id,
    )

    if not result.success:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.error_message or "Failed to complete upload",
            detail_code="common.validation_error",
        )

    return UploadCompleteResponse(
        message="Upload confirmed",
        message_code=get_response_code("file.uploaded"),
        file=FileResponse.model_validate(result.file),
    )


# ============================================================================
# File Listing and Retrieval Endpoints
# ============================================================================


@router.get("", response_model=FileListResponse)
async def list_files(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List files uploaded by the current user with DSL filtering, sorting, and pagination.

    Returns only files belonging to the authenticated user.
    User ID is derived from the session token for security.

    **Filter examples:**
    - `filter[category]=image` - exact match by category
    - `filter[status]=ready` - exact match by status
    - `filter[category][in]=image,video` - value in list

    **Sort:** `sort=created_time:desc` or `sort=original_filename:asc,created_time:desc`

    **Pagination:** `limit=50&offset=0`
    """
    organization_id = current_user.organization_id

    # Parse DSL parameters from request
    filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request)

    files, total = await get_files(
        session=session,
        organization_id=organization_id,
        user_id=current_user.id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    return FileListResponse(
        items=[FileResponse.model_validate(f) for f in files],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/organization", response_model=FileListResponse)
async def list_organization_files(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("files:admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List all files in the organization with DSL filtering, sorting, and pagination.

    Requires files:admin permission.
    Returns all files across all users in the organization.

    **Filter examples:**
    - `filter[category]=image` - exact match by category
    - `filter[status]=ready` - exact match by status
    - `filter[user_id]=<uuid>` - filter by uploader
    - `filter[category][in]=image,video` - value in list

    **Sort:** `sort=created_time:desc` or `sort=size_bytes:desc,original_filename:asc`

    **Pagination:** `limit=50&offset=0`
    """
    organization_id = current_user.organization_id

    # Parse DSL parameters from request
    filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request)

    files, total = await get_files(
        session=session,
        organization_id=organization_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    return FileListResponse(
        items=[FileResponse.model_validate(f) for f in files],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/usage", response_model=FileUsageResponse)
async def get_user_usage(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the current user's file usage statistics.

    Returns counts and sizes by category, plus quota information if applicable.
    """
    organization_id = current_user.organization_id

    usage = await get_user_file_usage(
        session=session,
        organization_id=organization_id,
        user_id=current_user.id,
    )

    if not usage:
        return FileUsageResponse(
            total_files=0,
            total_size_bytes=0,
            image_count=0,
            image_size_bytes=0,
            video_count=0,
            video_size_bytes=0,
            document_count=0,
            document_size_bytes=0,
            other_count=0,
            other_size_bytes=0,
        )

    # Get quota information
    file_settings = await get_organization_file_settings(session, organization_id)
    user_quota = file_settings.user_storage_quota_bytes if file_settings else None
    quota_percent = None
    if user_quota and user_quota > 0:
        quota_percent = min(
            round((usage.total_size_bytes / user_quota) * 100, 2), 100.0
        )

    return FileUsageResponse(
        total_files=usage.total_files,
        total_size_bytes=usage.total_size_bytes,
        image_count=usage.image_count,
        image_size_bytes=usage.image_size_bytes,
        video_count=usage.video_count,
        video_size_bytes=usage.video_size_bytes,
        document_count=usage.document_count,
        document_size_bytes=usage.document_size_bytes,
        other_count=usage.other_count,
        other_size_bytes=usage.other_size_bytes,
        user_quota_bytes=user_quota,
        user_quota_used_percent=quota_percent,
    )


@router.get("/usage/organization", response_model=OrganizationFileUsageResponse)
async def get_organization_usage(
    current_user: Annotated[CurrentUser, Depends(require_permission("files:admin"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get organization-wide file usage statistics.

    Requires files:admin permission.
    """
    organization_id = current_user.organization_id

    usage = await get_organization_file_usage(
        session=session,
        organization_id=organization_id,
    )

    # Get quota information
    file_settings = await get_organization_file_settings(session, organization_id)
    org_quota = file_settings.org_storage_quota_bytes if file_settings else None
    quota_percent = None
    if org_quota and org_quota > 0 and usage:
        quota_percent = min(
            round((usage["total_size_bytes"] / org_quota) * 100, 2), 100.0
        )

    if not usage:
        return OrganizationFileUsageResponse(
            total_files=0,
            total_size_bytes=0,
            org_quota_bytes=org_quota,
            org_quota_used_percent=quota_percent,
            user_count=0,
        )

    return OrganizationFileUsageResponse(
        total_files=usage["total_files"],
        total_size_bytes=usage["total_size_bytes"],
        org_quota_bytes=org_quota,
        org_quota_used_percent=quota_percent,
        user_count=usage["user_count"],
    )


@router.get("/settings", response_model=FileSettingsResponse)
async def get_file_settings(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("file_settings:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get organization file settings.

    Requires file_settings:read permission.
    """
    organization_id = current_user.organization_id

    file_settings = await get_organization_file_settings(session, organization_id)

    if not file_settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File settings not found",
            detail_code="common.not_found",
        )

    return FileSettingsResponse.model_validate(file_settings)


@router.put("/settings", response_model=FileSettingsResponse)
async def update_file_settings_endpoint(
    request: UpdateFileSettingsRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("file_settings:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update organization file settings.

    Requires file_settings:write permission.
    """
    organization_id = current_user.organization_id

    try:
        updated_settings = await update_organization_file_settings(
            session=session,
            organization_id=organization_id,
            settings_data=request.model_dump(exclude_unset=True),
        )

        return FileSettingsResponse.model_validate(updated_settings)

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )


@router.get("/{file_id}", response_model=FileResponse)
async def get_file(
    file_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get file metadata by ID.
    """
    organization_id = current_user.organization_id

    file_record = await get_file_by_id(
        session=session,
        file_id=str(file_id),
        organization_id=organization_id,
    )

    if not file_record:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
            detail_code="file.not_found",
        )

    return FileResponse.model_validate(file_record)


@router.get("/{file_id}/download", response_model=DownloadUrlResponse)
async def get_download_url_endpoint(
    http_request: Request,
    file_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a signed download URL for a file.

    Increments the download count and updates last accessed time.
    """
    organization_id = current_user.organization_id

    # Get file to access filename for response
    file_record = await get_file_by_id(
        session=session,
        file_id=str(file_id),
        organization_id=organization_id,
    )

    if not file_record:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
            detail_code="file.not_found",
        )

    try:
        fm = get_file_manager()
        if fm is None:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service unavailable",
                detail_code="file.service_unavailable",
            )

        # Use file manager to get download URL (also increments download count)
        signed_url_result = await fm.get_download_url(
            session=session,
            file_id=str(file_id),
            organization_id=organization_id,
        )

        if not signed_url_result:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found or not ready for download",
                detail_code="file.not_found",
            )

        return DownloadUrlResponse(
            download_url=signed_url_result.url,
            expires_at=signed_url_result.expires_at,
            filename=file_record.original_filename,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to generate download URL: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate download URL",
            detail_code="common.internal_error",
        )


@router.get("/{file_id}/thumbnail", response_model=ThumbnailUrlResponse)
async def get_thumbnail_url_endpoint(
    http_request: Request,
    file_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a signed thumbnail URL for a file.

    Only available for image files that have a generated thumbnail.
    """
    organization_id = current_user.organization_id

    # Get file to access filename for response
    file_record = await get_file_by_id(
        session=session,
        file_id=str(file_id),
        organization_id=organization_id,
    )

    if not file_record:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
            detail_code="file.not_found",
        )

    if not file_record.thumbnail_storage_key:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thumbnail not available for this file",
            detail_code="file.no_thumbnail",
        )

    try:
        fm = get_file_manager()
        if fm is None:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File storage service unavailable",
                detail_code="file.service_unavailable",
            )

        # Use file manager to get thumbnail URL
        signed_url_result = await fm.get_thumbnail_url(
            session=session,
            file_id=str(file_id),
            organization_id=organization_id,
        )

        if not signed_url_result:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thumbnail not available",
                detail_code="file.no_thumbnail",
            )

        return ThumbnailUrlResponse(
            thumbnail_url=signed_url_result.url,
            expires_at=signed_url_result.expires_at,
            filename=f"{file_record.original_filename}_thumb.webp",
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to generate thumbnail URL: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate thumbnail URL",
            detail_code="common.internal_error",
        )


@router.delete("/{file_id}", response_model=DeleteFileResponse)
async def delete_file_endpoint(
    file_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a file.

    The file will be marked as deleted but retained for the configured retention period.
    Users can only delete files they uploaded, unless they have 'files:delete_others'
    or 'files:admin' permission.
    """
    organization_id = current_user.organization_id

    file_record = await get_file_by_id(
        session=session,
        file_id=str(file_id),
        organization_id=organization_id,
    )

    if not file_record:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
            detail_code="file.not_found",
        )

    # Check if user has permission to delete this file (security fix)
    if not _can_delete_file(current_user, file_record.uploaded_by_user_id):
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this file",
            detail_code="file.delete_forbidden",
        )

    try:
        await soft_delete_file(
            session=session,
            file_id=str(file_id),
            organization_id=organization_id,
        )

        return DeleteFileResponse(
            message="File deleted successfully",
            message_code=get_response_code("file.deleted"),
        )

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
