"""
Request Log API endpoints.
Super admin-only endpoints for viewing and debugging API request logs.
"""

from datetime import datetime
import traceback
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.exceptions import create_http_exception
from src.crud.request_log import get_request_log_by_id, get_request_logs
from src.logger.logger import Logger
from src.serialisers.request_log import (
    ListRequestLogsResponse,
    RequestLoggingConfigResponse,
    RequestLogResponse,
    UpdateRequestLoggingConfigRequest,
)
from src.services.tasks import task_queue


router = APIRouter(prefix="/admin/request-logs", tags=["admin", "request-logs"])


@router.get("", response_model=ListRequestLogsResponse)
async def list_request_logs(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    method: Optional[str] = Query(
        None, description="Filter by HTTP method (GET, POST, etc.)"
    ),
    path: Optional[str] = Query(
        None, description="Filter by path pattern (uses SQL LIKE)"
    ),
    status_code_min: Optional[int] = Query(
        None, description="Filter by minimum status code"
    ),
    status_code_max: Optional[int] = Query(
        None, description="Filter by maximum status code"
    ),
    date_from: Optional[datetime] = Query(
        None, description="Filter from this date (ISO format)"
    ),
    date_to: Optional[datetime] = Query(
        None, description="Filter until this date (ISO format)"
    ),
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization ID"
    ),
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    user_email: Optional[str] = Query(
        None, description="Filter by user email (partial match)"
    ),
    limit: int = Query(
        50, ge=1, le=100, description="Number of items per page (max 100)"
    ),
    cursor: Optional[str] = Query(
        None, description="Cursor for pagination (from previous response)"
    ),
):
    """
    List API request logs for debugging purposes.

    Super admin only endpoint. Uses cursor-based pagination for consistent
    O(1) performance regardless of how deep into the result set you navigate.

    Supports filtering by:
    - **method**: HTTP method (GET, POST, etc.)
    - **path**: Path pattern (uses SQL LIKE)
    - **status_code_min/status_code_max**: Status code range
    - **date_from/date_to**: Date range
    - **organization_id**: Organization UUID (to filter by tenant)
    - **user_id**: User UUID (to filter by specific user)
    - **user_email**: User email (partial match, case-insensitive)

    Results are ordered by creation time (newest first).

    To paginate, pass the `next_cursor` from the response as the `cursor` parameter
    in the next request.
    """
    try:
        request_logs, next_cursor, has_more = await get_request_logs(
            session=session,
            limit=limit,
            cursor=cursor,
            method=method,
            path_pattern=path,
            status_code_min=status_code_min,
            status_code_max=status_code_max,
            date_from=date_from,
            date_to=date_to,
            organization_id=str(organization_id) if organization_id else None,
            user_id=str(user_id) if user_id else None,
            user_email=user_email,
        )
    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Invalid cursor for request logs: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="request_logs.invalid_cursor",
        )

    return ListRequestLogsResponse(
        items=[RequestLogResponse.model_validate(log) for log in request_logs],
        next_cursor=next_cursor,
        has_more=has_more,
        limit=limit,
    )


# NOTE: Static routes (/config, /cleanup) must be defined BEFORE dynamic routes (/{request_log_id})
# to ensure FastAPI matches them correctly


@router.get("/config", response_model=RequestLoggingConfigResponse)
async def get_logging_config(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
):
    """
    Get current request logging configuration.

    Super admin only endpoint.

    Returns the current configuration values:
    - **enabled**: Whether request logging is active
    - **db_enabled**: Whether logs are stored in the database
    - **max_body_size**: Maximum request/response body size captured (bytes)
    - **retention_days**: How long logs are retained before cleanup
    """
    from src.services.config_cache import get_request_logging_config

    config = await get_request_logging_config()

    return RequestLoggingConfigResponse(
        enabled=config.enabled,
        db_enabled=config.db_enabled,
        max_body_size=config.max_body_size,
        retention_days=config.retention_days,
    )


@router.put("/config", response_model=RequestLoggingConfigResponse)
async def update_logging_config(
    request: UpdateRequestLoggingConfigRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
):
    """
    Update request logging configuration.

    Super admin only endpoint.

    Updates the configuration and invalidates the cache so changes take effect immediately.

    Parameters:
    - **enabled**: Enable or disable request logging
    - **db_enabled**: Enable or disable database storage
    - **max_body_size**: Maximum body size in bytes (1KB - 100KB)
    - **retention_days**: Retention period in days (1-365)
    """
    from src.services.config_cache import update_request_logging_config

    config = await update_request_logging_config(
        enabled=request.enabled,
        db_enabled=request.db_enabled,
        max_body_size=request.max_body_size,
        retention_days=request.retention_days,
        user_id=str(current_user.id),
    )

    return RequestLoggingConfigResponse(
        enabled=config.enabled,
        db_enabled=config.db_enabled,
        max_body_size=config.max_body_size,
        retention_days=config.retention_days,
    )


@router.post("/cleanup", status_code=status.HTTP_202_ACCEPTED)
async def trigger_cleanup(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
):
    """
    Manually trigger cleanup of old request logs.

    Super admin only endpoint.

    Enqueues a background job to clean up request logs older than the
    configured retention period (from SystemConfig key 'request_logs.retention_days',
    default 30 days).

    Returns a 202 Accepted response with the job ID for tracking.
    """
    job_id = await task_queue.enqueue_job("cleanup_old_request_logs_task")

    if not job_id:
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enqueue cleanup job",
            detail_code="request_logs.cleanup_enqueue_failed",
        )

    return {
        "message": "Cleanup job enqueued successfully",
        "job_id": job_id,
    }


@router.get("/{request_log_id}", response_model=RequestLogResponse)
async def get_request_log(
    request_log_id: UUID,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single request log entry by ID.

    Super admin only endpoint.
    """
    request_log = await get_request_log_by_id(
        session=session,
        request_log_id=str(request_log_id),
    )

    if not request_log:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request log not found",
            detail_code="common.not_found",
        )

    return RequestLogResponse.model_validate(request_log)
