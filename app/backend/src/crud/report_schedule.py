"""
CRUD operations for ReportSchedule model.

All schedule operations are tenant-scoped and require organization_id filtering.
Supports filtering by type, status, and active state.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from croniter import croniter
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
from src.models.report_schedule import ReportSchedule


# Configuration for report schedule DSL queries
SCHEDULE_FILTER_FIELDS = {"report_type", "is_active", "created_time"}
SCHEDULE_SORT_FIELDS = {"created_time", "name", "report_type", "next_run_time"}
SCHEDULE_FIELD_MAPPING: dict[str, str] = {}


def calculate_next_run_time(schedule_expression: str) -> datetime:
    """
    Calculate the next run time from a cron expression.

    Args:
        schedule_expression: Cron expression string

    Returns:
        Next run time as datetime
    """
    now = datetime.now(timezone.utc)
    cron = croniter(schedule_expression, now)
    return cron.get_next(datetime)


async def create_report_schedule(
    session: AsyncSession,
    organization_id: str,
    report_type: str,
    name: str,
    schedule_expression: str,
    recipients: list[str],
    created_by_user_id: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
) -> ReportSchedule:
    """
    Create a new report schedule.

    Args:
        session: Database session
        organization_id: Organization UUID string
        report_type: Type of report (e.g., "users_report")
        name: Schedule name
        schedule_expression: Cron expression for scheduling
        recipients: List of email addresses
        created_by_user_id: User ID who created the schedule
        description: Optional description
        parameters: Report-specific parameters/filters

    Returns:
        The created ReportSchedule
    """
    org_uuid = UUID(organization_id)
    user_uuid = UUID(created_by_user_id) if created_by_user_id else None

    # Calculate initial next_run_time
    next_run = calculate_next_run_time(schedule_expression)

    schedule = ReportSchedule(
        organization_id=org_uuid,
        created_by_user_id=user_uuid,
        report_type=report_type,
        name=name,
        description=description,
        schedule_expression=schedule_expression,
        parameters=parameters,
        recipients=recipients,
        is_active=True,
        next_run_time=next_run,
    )

    session.add(schedule)
    try:
        await session.commit()
        await session.refresh(schedule)
    except Exception as e:
        await session.rollback()
        raise e

    return schedule


async def get_report_schedule_by_id(
    session: AsyncSession,
    schedule_id: str,
    organization_id: str,
    load_relationships: bool = True,
) -> Optional[ReportSchedule]:
    """
    Get report schedule by ID within organization context.

    Args:
        session: Database session
        schedule_id: Schedule UUID string
        organization_id: Organization UUID string
        load_relationships: Whether to eagerly load relationships

    Returns:
        The ReportSchedule or None if not found
    """
    schedule_uuid = UUID(schedule_id)
    org_uuid = UUID(organization_id)

    conditions: list[ColumnElement[bool]] = [
        ReportSchedule.id == schedule_uuid,
        ReportSchedule.organization_id == org_uuid,
        ReportSchedule.deleted_time.is_(None),
    ]

    query = select(ReportSchedule).where(*conditions)

    if load_relationships:
        query = query.options(
            selectinload(ReportSchedule.created_by_user),
        )

    result = await session.execute(query)
    return result.scalars().first()


async def get_report_schedules_list(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[ReportSchedule], int]:
    """
    Get paginated list of report schedules with DSL filtering and sorting.

    Args:
        session: Database session
        organization_id: Organization UUID string
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of schedules, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query with eager loading
    base_query = (
        select(ReportSchedule)
        .where(
            ReportSchedule.organization_id == org_uuid,
            ReportSchedule.deleted_time.is_(None),
        )
        .options(
            selectinload(ReportSchedule.created_by_user),
        )
    )

    # Apply DSL filters
    if filters:
        base_query = apply_filters(
            base_query, ReportSchedule, filters, SCHEDULE_FIELD_MAPPING
        )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(
            base_query, ReportSchedule, sorts, SCHEDULE_FIELD_MAPPING
        )
    else:
        base_query = base_query.order_by(ReportSchedule.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    schedules = result.scalars().all()

    return list(schedules), total_count


async def update_report_schedule(
    session: AsyncSession,
    schedule_id: str,
    organization_id: str,
    update_data: dict[str, Any],
) -> Optional[ReportSchedule]:
    """
    Update a report schedule.

    Args:
        session: Database session
        schedule_id: Schedule UUID string
        organization_id: Organization UUID string
        update_data: Dictionary of fields to update

    Returns:
        The updated ReportSchedule or None if not found
    """
    schedule = await get_report_schedule_by_id(
        session, schedule_id, organization_id, load_relationships=False
    )

    if not schedule:
        return None

    # Update allowed fields
    if "name" in update_data and update_data["name"] is not None:
        schedule.name = update_data["name"]

    if "description" in update_data:
        schedule.description = update_data["description"]

    if (
        "schedule_expression" in update_data
        and update_data["schedule_expression"] is not None
    ):
        schedule.schedule_expression = update_data["schedule_expression"]
        # Recalculate next_run_time when schedule changes
        schedule.next_run_time = calculate_next_run_time(
            update_data["schedule_expression"]
        )

    if "parameters" in update_data:
        schedule.parameters = update_data["parameters"]

    if "recipients" in update_data and update_data["recipients"] is not None:
        schedule.recipients = update_data["recipients"]

    if "is_active" in update_data and update_data["is_active"] is not None:
        schedule.is_active = update_data["is_active"]
        # Recalculate next_run_time when reactivating
        if update_data["is_active"]:
            schedule.next_run_time = calculate_next_run_time(
                schedule.schedule_expression
            )

    try:
        await session.commit()
        await session.refresh(schedule)
    except Exception as e:
        await session.rollback()
        raise e

    return schedule


async def soft_delete_report_schedule(
    session: AsyncSession,
    schedule_id: str,
    organization_id: str,
) -> Optional[ReportSchedule]:
    """
    Soft delete a report schedule.

    Args:
        session: Database session
        schedule_id: Schedule UUID string
        organization_id: Organization UUID string

    Returns:
        The deleted ReportSchedule or None if not found
    """
    schedule = await get_report_schedule_by_id(
        session, schedule_id, organization_id, load_relationships=False
    )

    if not schedule:
        return None

    schedule.deleted_time = datetime.now(timezone.utc)
    schedule.is_active = False

    try:
        await session.commit()
        await session.refresh(schedule)
    except Exception as e:
        await session.rollback()
        raise e

    return schedule


async def get_due_report_schedules(
    session: AsyncSession,
    current_time: Optional[datetime] = None,
) -> list[ReportSchedule]:
    """
    Get all active report schedules that are due to run.

    Used by the cron processor to find schedules that need execution.

    Args:
        session: Database session
        current_time: Current time (defaults to now)

    Returns:
        List of due ReportSchedule objects
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    query = (
        select(ReportSchedule)
        .where(
            ReportSchedule.is_active == True,  # noqa: E712
            ReportSchedule.deleted_time.is_(None),
            ReportSchedule.next_run_time <= current_time,
        )
        .options(
            selectinload(ReportSchedule.organization),
        )
    )

    result = await session.execute(query)
    return list(result.scalars().all())


async def update_schedule_run_status(
    session: AsyncSession,
    schedule_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> Optional[ReportSchedule]:
    """
    Update schedule after execution.

    Args:
        session: Database session
        schedule_id: Schedule UUID string
        status: Run status (success, error)
        error_message: Error message if failed

    Returns:
        The updated ReportSchedule or None if not found
    """
    schedule_uuid = UUID(schedule_id)

    result = await session.execute(
        select(ReportSchedule).where(
            ReportSchedule.id == schedule_uuid,
            ReportSchedule.deleted_time.is_(None),
        )
    )
    schedule = result.scalars().first()

    if not schedule:
        return None

    now = datetime.now(timezone.utc)

    schedule.last_run_time = now
    schedule.last_run_status = status
    schedule.last_run_error_message = error_message

    # Calculate next run time
    if schedule.is_active:
        schedule.next_run_time = calculate_next_run_time(schedule.schedule_expression)

    try:
        await session.commit()
        await session.refresh(schedule)
    except Exception as e:
        await session.rollback()
        raise e

    return schedule
