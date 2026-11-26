"""
Report Schedule API endpoints.

Endpoints for managing report schedules.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.api.deps import CurrentUser, get_session, require_permission
from src.core.exceptions import create_http_exception
from src.core.query_params import (
    get_pagination_params,
    parse_filters,
    parse_sort,
)
from src.crud.report_schedule import (
    create_report_schedule,
    get_report_schedule_by_id,
    get_report_schedules_list,
    soft_delete_report_schedule,
    update_report_schedule,
)
from src.serialisers.report_schedule import (
    CreateReportScheduleResponse,
    DeleteReportScheduleResponse,
    ReportScheduleCreateRequest,
    ReportScheduleListResponse,
    ReportScheduleResponse,
    ReportScheduleUpdateRequest,
    UpdateReportScheduleResponse,
)
from src.services.reports import is_valid_report_type


# DSL configuration for report schedules
ALLOWED_FILTERS = {"report_type", "is_active", "created_time"}
ALLOWED_SORTS = {"created_time", "name", "report_type", "next_run_time"}

router = APIRouter(prefix="/report-schedules", tags=["report-schedules"])


def schedule_to_response(schedule) -> ReportScheduleResponse:
    """Convert a ReportSchedule model to response schema."""
    return ReportScheduleResponse(
        id=schedule.id,
        organization_id=schedule.organization_id,
        created_by_user_id=schedule.created_by_user_id,
        report_type=schedule.report_type,
        name=schedule.name,
        description=schedule.description,
        schedule_expression=schedule.schedule_expression,
        is_active=schedule.is_active,
        parameters=schedule.parameters,
        recipients=schedule.recipients,
        last_run_time=schedule.last_run_time,
        next_run_time=schedule.next_run_time,
        last_run_status=schedule.last_run_status,
        last_run_error_message=schedule.last_run_error_message,
        created_time=schedule.created_time,
        updated_time=schedule.updated_time,
    )


@router.get("", response_model=ReportScheduleListResponse)
async def list_report_schedules(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("reports:schedule"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List report schedules for the organization with DSL filtering, sorting, and pagination.

    Requires reports:schedule permission.

    **Filter examples:**
    - `filter[report_type]=users_report` - exact match
    - `filter[is_active]=true` - boolean filter
    - `filter[created_time][gte]=2024-01-01T00:00:00Z` - date comparison

    **Sort:** `sort=created_time:desc` or `sort=name:asc,next_run_time:asc`

    **Pagination:** `limit=50&offset=0`
    """
    # Parse DSL parameters from request
    filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    limit, offset = get_pagination_params(request)

    schedules, total = await get_report_schedules_list(
        session=session,
        organization_id=current_user.organization_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    return ReportScheduleListResponse(
        items=[schedule_to_response(s) for s in schedules],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "", response_model=CreateReportScheduleResponse, status_code=status.HTTP_201_CREATED
)
async def create_schedule(
    request_data: ReportScheduleCreateRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("reports:schedule"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new report schedule.

    Requires reports:schedule permission.

    The schedule will automatically generate reports based on the cron expression
    and send them to the specified recipients.
    """
    # Validate report type
    if not is_valid_report_type(request_data.report_type):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown report type: {request_data.report_type}",
            detail_code="reports.invalid_type",
        )

    # Create schedule
    schedule = await create_report_schedule(
        session=session,
        organization_id=current_user.organization_id,
        report_type=request_data.report_type,
        name=request_data.name,
        schedule_expression=request_data.schedule_expression,
        recipients=[str(email) for email in request_data.recipients],
        created_by_user_id=current_user.id,
        description=request_data.description,
        parameters=request_data.parameters,
    )

    return CreateReportScheduleResponse(
        message="Report schedule created successfully",
        message_code="report_schedules.created",
        schedule=schedule_to_response(schedule),
    )


@router.get("/{schedule_id}", response_model=ReportScheduleResponse)
async def get_schedule(
    schedule_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("reports:schedule"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single report schedule by ID.

    Requires reports:schedule permission.
    """
    schedule = await get_report_schedule_by_id(
        session=session,
        schedule_id=str(schedule_id),
        organization_id=current_user.organization_id,
    )

    if not schedule:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report schedule not found",
            detail_code="report_schedules.not_found",
        )

    return schedule_to_response(schedule)


@router.patch("/{schedule_id}", response_model=UpdateReportScheduleResponse)
async def update_schedule(
    schedule_id: UUID,
    request_data: ReportScheduleUpdateRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("reports:schedule"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a report schedule.

    Requires reports:schedule permission.
    """
    # Build update data from request
    update_data = request_data.model_dump(exclude_unset=True)

    # Convert EmailStr list to string list if present
    if "recipients" in update_data and update_data["recipients"] is not None:
        update_data["recipients"] = [str(email) for email in update_data["recipients"]]

    schedule = await update_report_schedule(
        session=session,
        schedule_id=str(schedule_id),
        organization_id=current_user.organization_id,
        update_data=update_data,
    )

    if not schedule:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report schedule not found",
            detail_code="report_schedules.not_found",
        )

    return UpdateReportScheduleResponse(
        message="Report schedule updated successfully",
        message_code="report_schedules.updated",
        schedule=schedule_to_response(schedule),
    )


@router.delete("/{schedule_id}", response_model=DeleteReportScheduleResponse)
async def delete_schedule(
    schedule_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:delete"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a report schedule.

    Requires reports:delete permission.
    """
    schedule = await soft_delete_report_schedule(
        session=session,
        schedule_id=str(schedule_id),
        organization_id=current_user.organization_id,
    )

    if not schedule:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report schedule not found",
            detail_code="report_schedules.not_found",
        )

    return DeleteReportScheduleResponse(
        message="Report schedule deleted successfully",
        message_code="report_schedules.deleted",
        schedule_id=schedule_id,
    )
