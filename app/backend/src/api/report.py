"""
Report API endpoints.

Endpoints for generating, listing, and managing reports.
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
from src.crud.report import get_report_by_id, get_reports_list, soft_delete_report
from src.serialisers.report import (
    CreateReportResponse,
    DeleteReportResponse,
    ReportCreateRequest,
    ReportListResponse,
    ReportResponse,
    ReportTypeResponse,
    ReportTypesListResponse,
)
from src.services.files import get_file_manager
from src.services.reports import get_available_report_types, is_valid_report_type
from src.services.reports.report_service import report_service


# DSL configuration for reports
ALLOWED_FILTERS = {"report_type", "status", "created_time", "generated_by_user_id"}
ALLOWED_SORTS = {"created_time", "name", "report_type", "status", "completed_at"}

router = APIRouter(prefix="/reports", tags=["reports"])


async def report_to_response(
    report,
    session: AsyncSession,
    organization_id: str,
) -> ReportResponse:
    """
    Convert a Report model to response schema with download URL.
    """
    download_url = None

    # Generate download URL if report is completed and has a file
    if report.status == "completed" and report.file_id:
        fm = get_file_manager()
        if fm:
            signed_url = await fm.get_download_url(
                session=session,
                file_id=str(report.file_id),
                organization_id=organization_id,
            )
            if signed_url:
                download_url = signed_url.url

    return ReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        generated_by_user_id=report.generated_by_user_id,
        report_type=report.report_type,
        name=report.name,
        description=report.description,
        parameters=report.parameters,
        status=report.status,
        error_message=report.error_message,
        started_at=report.started_at,
        completed_at=report.completed_at,
        file_id=report.file_id,
        row_count=report.row_count,
        schedule_id=report.schedule_id,
        created_time=report.created_time,
        updated_time=report.updated_time,
        download_url=download_url,
    )


@router.get("/types", response_model=ReportTypesListResponse)
async def list_report_types(
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:read"))],
):
    """
    List available report types.

    Requires reports:read permission.
    """
    report_types = get_available_report_types()

    return ReportTypesListResponse(
        items=[
            ReportTypeResponse(
                code=rt.code,
                name=rt.name,
                description=rt.description,
            )
            for rt in report_types
        ]
    )


@router.get("", response_model=ReportListResponse)
async def list_reports(
    request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List reports for the organization with DSL filtering, sorting, and pagination.

    Requires reports:read permission.

    **Filter examples:**
    - `filter[report_type]=users_report` - exact match
    - `filter[status][in]=pending,processing` - value in list
    - `filter[created_time][gte]=2024-01-01T00:00:00Z` - date comparison

    **Sort:** `sort=created_time:desc` or `sort=name:asc,created_time:desc`

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

    reports, total = await get_reports_list(
        session=session,
        organization_id=current_user.organization_id,
        filters=filters,
        sorts=sorts,
        limit=limit,
        offset=offset,
    )

    items = []
    for report in reports:
        response = await report_to_response(
            report, session, current_user.organization_id
        )
        items.append(response)

    return ReportListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "", response_model=CreateReportResponse, status_code=status.HTTP_201_CREATED
)
async def create_report(
    request_data: ReportCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Generate a new report.

    Requires reports:write permission.

    The report will be generated asynchronously and the response will include
    the initial report record. Poll the GET endpoint to check status.
    """
    # Validate report type
    if not is_valid_report_type(request_data.report_type):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown report type: {request_data.report_type}",
            detail_code="reports.invalid_type",
        )

    # Generate report
    report = await report_service.generate_report(
        session=session,
        organization_id=current_user.organization_id,
        report_type=request_data.report_type,
        name=request_data.name,
        generated_by_user_id=current_user.id,
        description=request_data.description,
        parameters=request_data.parameters,
    )

    response = await report_to_response(report, session, current_user.organization_id)

    return CreateReportResponse(
        message="Report created successfully",
        message_code="reports.created",
        report=response,
    )


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single report by ID.

    Requires reports:read permission.
    """
    report = await get_report_by_id(
        session=session,
        report_id=str(report_id),
        organization_id=current_user.organization_id,
    )

    if not report:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
            detail_code="reports.not_found",
        )

    return await report_to_response(report, session, current_user.organization_id)


@router.delete("/{report_id}", response_model=DeleteReportResponse)
async def delete_report(
    report_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_permission("reports:delete"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a report.

    Requires reports:delete permission.
    """
    report = await soft_delete_report(
        session=session,
        report_id=str(report_id),
        organization_id=current_user.organization_id,
    )

    if not report:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
            detail_code="reports.not_found",
        )

    return DeleteReportResponse(
        message="Report deleted successfully",
        message_code="reports.deleted",
        report_id=report_id,
    )
