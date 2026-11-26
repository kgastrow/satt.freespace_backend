"""
User data export and deletion API endpoints.
Implements GDPR-compliant data export and account deletion functionality.
"""

from datetime import datetime, timedelta, timezone
import os
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.data_deletion_request import (
    cancel_deletion_request,
    create_data_deletion_request,
    get_data_deletion_request,
)
from src.crud.data_export_request import (
    create_data_export_request,
    get_export_request_by_id,
    get_user_export_requests,
    increment_download_count,
)
from src.logger.logger import Logger
from src.serialisers.data_export import (
    CancelDeletionRequestResponse,
    CreateDeletionRequestResponse,
    CreateExportRequestResponse,
    DataDeletionRequestResponse,
    DataExportRequestResponse,
    ExportDownloadUrlResponse,
    GetDeletionStatusResponse,
    ListExportRequestsResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.files import s3_storage
from src.services.tasks import task_queue


router = APIRouter(prefix="/users/me", tags=["user-data"])


@router.post(
    "/export",
    response_model=CreateExportRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_data_export(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new data export request for the current user.

    The export will be generated asynchronously and the user will be able to
    download it once completed. Exports expire after 30 days.
    """
    try:
        export_request = await create_data_export_request(
            session=session,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
        )

        # Audit log
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="DataExportRequest",
            resource_id=str(export_request.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            resource_data={"user_id": str(current_user.id)},
        )

        # Enqueue background task to generate the export
        await task_queue.enqueue_job(
            "process_data_export_task",
            str(export_request.id),
        )

        return CreateExportRequestResponse(
            message="Export request created successfully. You will receive a notification when ready.",
            message_code=get_response_code("data_export.request_created"),
            request_id=export_request.id,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to create data export request for user {current_user.id}: {e}\n{error_tb}"
        )
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again later.",
            detail_code="data_export.request_failed",
        )


@router.get("/exports", response_model=ListExportRequestsResponse)
async def list_data_exports(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all data export requests for the current user.

    Returns export requests ordered by creation time (newest first).
    """
    exports, total = await get_user_export_requests(
        session=session,
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
        limit=limit,
        offset=offset,
    )

    return ListExportRequestsResponse(
        items=[DataExportRequestResponse.model_validate(exp) for exp in exports],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/exports/{export_id}/download", response_model=ExportDownloadUrlResponse)
async def get_export_download_url(
    export_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Generate a signed download URL for a completed export.

    The URL is valid for 1 hour. This endpoint increments the download count.
    """
    export_request = await get_export_request_by_id(
        session=session,
        export_request_id=export_id,
        organization_id=str(current_user.organization_id),
    )

    if not export_request:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export request not found",
            detail_code="data_export.not_found",
        )

    # Security fix: Verify user ownership to prevent IDOR
    # Convert UUID to string for comparison since current_user.id is a string
    if str(export_request.user_id) != current_user.id:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this export",
            detail_code="data_export.access_denied",
        )

    if export_request.status != "completed":
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export is not ready for download. Current status: {export_request.status}",
            detail_code="data_export.not_ready",
        )

    if not export_request.file_path:
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Export file path is missing",
            detail_code="data_export.file_missing",
        )

    # Handle local storage (dev environment fallback)
    if export_request.file_path.startswith("local:"):
        # For local storage, return a direct download endpoint URL with full host
        # Use the request's base URL to construct a full URL
        base_url = str(request.base_url).rstrip("/")
        download_url = f"{base_url}/api/v1/users/me/exports/{export_id}/download-file"
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        signed_url_result = type(
            "Result",
            (),
            {
                "success": True,
                "url": download_url,
                "expires_at": expires_at,
            },
        )()
    elif s3_storage and s3_storage.is_available():
        # Generate signed URL (1 hour validity)
        signed_url_result = await s3_storage.generate_download_url(
            storage_key=export_request.file_path,
            expires_in=3600,
            filename=f"data_export_{current_user.id}.zip",
        )
    else:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage service not available",
            detail_code="file.service_unavailable",
        )

    # Increment download count
    await increment_download_count(
        session=session,
        export_request_id=export_id,
        organization_id=str(current_user.organization_id),
    )

    # Audit log
    await audit_service.log_create(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="DataExportDownload",
        resource_id=str(export_request.id),
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        resource_data={"export_request_id": export_id},
    )

    return ExportDownloadUrlResponse(
        message="Download URL generated successfully",
        message_code=get_response_code("data_export.download_url_generated"),
        download_url=signed_url_result.url,
        expires_at=signed_url_result.expires_at,
    )


@router.get("/exports/{export_id}/download-file")
async def download_export_file(
    export_id: str,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Direct file download for local storage exports (dev environment only).
    """
    export_request = await get_export_request_by_id(
        session=session,
        export_request_id=export_id,
        organization_id=str(current_user.organization_id),
    )

    if not export_request:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export request not found",
            detail_code="data_export.not_found",
        )

    # Security fix: Verify user ownership to prevent IDOR
    # Convert UUID to string for comparison since current_user.id is a string
    if str(export_request.user_id) != current_user.id:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this export",
            detail_code="data_export.access_denied",
        )

    if export_request.status != "completed":
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Export is not ready for download",
            detail_code="data_export.not_ready",
        )

    if not export_request.file_path or not export_request.file_path.startswith(
        "local:"
    ):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only for local storage exports",
            detail_code="data_export.invalid_storage",
        )

    # Extract local path from "local:/path/to/file.zip"
    local_path = export_request.file_path[6:]  # Remove "local:" prefix

    # Security fix: Canonicalize and validate the path to prevent path traversal
    real_path = os.path.realpath(local_path)
    allowed_base_dir = os.path.realpath(settings.LOCAL_STORAGE_PATH)
    if (
        not real_path.startswith(allowed_base_dir + os.sep)
        and real_path != allowed_base_dir
    ):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid export file path",
            detail_code="data_export.invalid_path",
        )

    # Verify file extension
    if not real_path.endswith(".zip"):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid export file format",
            detail_code="data_export.invalid_format",
        )

    if not os.path.exists(real_path):
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found on disk",
            detail_code="data_export.file_not_found",
        )

    # Increment download count
    await increment_download_count(
        session=session,
        export_request_id=export_id,
        organization_id=str(current_user.organization_id),
    )

    # Audit log
    await audit_service.log_create(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="DataExportDownload",
        resource_id=str(export_request.id),
        actor_id=current_user.id,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        resource_data={"export_request_id": export_id, "storage": "local"},
    )

    return FileResponse(
        path=real_path,
        filename=f"data_export_{current_user.id}.zip",
        media_type="application/zip",
    )


@router.post(
    "/delete",
    response_model=CreateDeletionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def request_account_deletion(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Request account deletion for the current user.

    This triggers an immediate soft delete and schedules hard deletion after 30 days.
    The user can cancel the request during this grace period.
    """
    try:
        deletion_request = await create_data_deletion_request(
            session=session,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
        )

        # Audit log
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="DataDeletionRequest",
            resource_id=str(deletion_request.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
            resource_data={"user_id": str(current_user.id)},
        )

        # scheduled_hard_delete_at should always be set, but handle None for type safety
        if deletion_request.scheduled_hard_delete_at is None:
            raise create_http_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Scheduled deletion time not set",
                detail_code="data_deletion.request_failed",
            )

        return CreateDeletionRequestResponse(
            message="Account deletion requested. You have 30 days to cancel before permanent deletion.",
            message_code=get_response_code("data_deletion.request_created"),
            request_id=deletion_request.id,
            scheduled_hard_delete_at=deletion_request.scheduled_hard_delete_at,
        )

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="data_deletion.already_exists",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to create data deletion request for user {current_user.id}: {e}\n{error_tb}"
        )
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again later.",
            detail_code="data_deletion.request_failed",
        )


@router.post("/delete/cancel", response_model=CancelDeletionRequestResponse)
async def cancel_account_deletion(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Cancel a pending account deletion request.

    This can only be done during the 30-day grace period.
    """
    try:
        deletion_request = await cancel_deletion_request(
            session=session,
            user_id=str(current_user.id),
            organization_id=str(current_user.organization_id),
            cancellation_reason="User requested cancellation",
        )

        # Audit log
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="DataDeletionRequest",
            resource_id=str(deletion_request.id),
            old_values={"status": "pending"},
            new_values={"status": "cancelled"},
            actor_id=current_user.id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        return CancelDeletionRequestResponse(
            message="Account deletion cancelled successfully",
            message_code=get_response_code("data_deletion.cancelled"),
        )

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="data_deletion.not_found",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Failed to cancel data deletion request for user {current_user.id}: {e}\n{error_tb}"
        )
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request. Please try again later.",
            detail_code="data_deletion.cancel_failed",
        )


@router.get("/delete", response_model=GetDeletionStatusResponse)
async def get_deletion_status(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the current account deletion status for the current user.

    Returns the active deletion request if one exists.
    """
    deletion_request = await get_data_deletion_request(
        session=session,
        user_id=str(current_user.id),
        organization_id=str(current_user.organization_id),
    )

    if deletion_request:
        return GetDeletionStatusResponse(
            has_active_request=True,
            request=DataDeletionRequestResponse.model_validate(deletion_request),
        )

    return GetDeletionStatusResponse(
        has_active_request=False,
        request=None,
    )
