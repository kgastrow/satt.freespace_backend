"""
CRUD operations for Report model.

All report operations are tenant-scoped and require organization_id filtering.
Supports filtering by type, status, and date range.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.report import Report, ReportStatus


# Configuration for report DSL queries
REPORT_FILTER_FIELDS = {"report_type", "status", "created_time", "generated_by_user_id"}
REPORT_SORT_FIELDS = {"created_time", "name", "report_type", "status", "completed_at"}
REPORT_FIELD_MAPPING: dict[str, str] = {}


async def create_report(
    session: AsyncSession,
    organization_id: str,
    report_type: str,
    name: str,
    generated_by_user_id: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
    schedule_id: Optional[str] = None,
) -> Report:
    """
    Create a new report record.

    Args:
        session: Database session
        organization_id: Organization UUID string
        report_type: Type of report (e.g., "users_report")
        name: Report name
        generated_by_user_id: User ID who initiated the report
        description: Optional description
        parameters: Report-specific parameters/filters
        schedule_id: Optional schedule ID if generated from a schedule

    Returns:
        The created Report
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(generated_by_user_id) if generated_by_user_id else None
    sched_uuid = UUID(schedule_id) if schedule_id else None

    report = Report(
        organization_id=org_uuid,
        generated_by_user_id=user_uuid,
        report_type=report_type,
        name=name,
        description=description,
        parameters=parameters,
        status=ReportStatus.PENDING.value,
        schedule_id=sched_uuid,
    )

    session.add(report)
    try:
        await session.commit()
        await session.refresh(report)
    except Exception as e:
        await session.rollback()
        raise e

    return report


async def get_report_by_id(
    session: AsyncSession,
    report_id: str,
    organization_id: str,
    load_relationships: bool = True,
) -> Optional[Report]:
    """
    Get report by ID within organization context.

    Args:
        session: Database session
        report_id: Report UUID string
        organization_id: Organization UUID string
        load_relationships: Whether to eagerly load relationships

    Returns:
        The Report or None if not found
    """
    report_uuid = UUID(report_id)
    org_uuid = UUID(organization_id)

    conditions: list[ColumnElement[bool]] = [
        Report.id == report_uuid,
        Report.organization_id == org_uuid,
        Report.deleted_time.is_(None),
    ]

    query = select(Report).where(*conditions)

    if load_relationships:
        query = query.options(
            selectinload(Report.generated_by_user),
            selectinload(Report.file),
        )

    result = await session.execute(query)
    return result.scalars().first()


async def get_reports_list(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Report], int]:
    """
    Get paginated list of reports with DSL filtering and sorting.

    Args:
        session: Database session
        organization_id: Organization UUID string
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of reports, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with eager loading
    base_query = (
        select(Report)
        .where(
            Report.organization_id == org_uuid,
            Report.deleted_time.is_(None),
        )
        .options(
            selectinload(Report.generated_by_user),
            selectinload(Report.file),
        )
    )

    # Apply DSL filters
    if filters:
        base_query = apply_filters(base_query, Report, filters, REPORT_FIELD_MAPPING)

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(base_query, Report, sorts, REPORT_FIELD_MAPPING)
    else:
        base_query = base_query.order_by(Report.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    reports = result.scalars().all()

    return list(reports), total_count


async def update_report_status(
    session: AsyncSession,
    report_id: str,
    organization_id: str,
    status: str,
    error_message: Optional[str] = None,
    file_id: Optional[str] = None,
    row_count: Optional[int] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[Report]:
    """
    Update report status and related fields.

    Args:
        session: Database session
        report_id: Report UUID string
        organization_id: Organization UUID string
        status: New status value
        error_message: Error message if failed
        file_id: File ID if completed successfully
        row_count: Number of rows in the report
        started_at: When processing started
        completed_at: When processing completed

    Returns:
        The updated Report or None if not found
    """
    report = await get_report_by_id(
        session, report_id, organization_id, load_relationships=False
    )

    if not report:
        return None

    report.status = status

    if error_message is not None:
        report.error_message = error_message

    if file_id is not None:
        report.file_id = UUID(file_id)

    if row_count is not None:
        report.row_count = row_count

    if started_at is not None:
        report.started_at = started_at

    if completed_at is not None:
        report.completed_at = completed_at

    try:
        await session.commit()
        await session.refresh(report)
    except Exception as e:
        await session.rollback()
        raise e

    return report


async def soft_delete_report(
    session: AsyncSession,
    report_id: str,
    organization_id: str,
) -> Optional[Report]:
    """
    Soft delete a report.

    Args:
        session: Database session
        report_id: Report UUID string
        organization_id: Organization UUID string

    Returns:
        The deleted Report or None if not found
    """
    report = await get_report_by_id(
        session, report_id, organization_id, load_relationships=False
    )

    if not report:
        return None

    report.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(report)
    except Exception as e:
        await session.rollback()
        raise e

    return report
