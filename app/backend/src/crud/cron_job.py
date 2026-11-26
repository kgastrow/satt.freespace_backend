"""
CRUD operations for CronJobDefinition and CronJobExecution models.

CronJobDefinition support mixed scope:
- organization_id=None: Platform-wide cron jobs (run globally once)
- organization_id=UUID: Organization-scoped cron jobs (run per org)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.cron_job import CronJobDefinition, CronJobExecution, CronJobStatus


async def create_cron_job(
    session: AsyncSession,
    job_data: dict[str, Any],
    organization_id: Optional[str],
) -> CronJobDefinition:
    """
    Create a cron job definition.

    Args:
        session: Database session
        job_data: Job data including name, description, code, schedule_expression,
                  is_active, is_enabled_by_default_for_new_orgs, parameters
        organization_id: Organization UUID string (None for platform-wide)

    Returns:
        The created CronJobDefinition

    Raises:
        ValueError: If code already exists or cron expression is invalid
    """
    org_uuid = UUID(organization_id) if organization_id else None

    # Validate cron expression
    schedule = job_data["schedule_expression"]
    if not is_valid_cron_expression(schedule):
        raise ValueError(f"Invalid cron expression: {schedule}")

    # Check for duplicate code within organization scope
    existing = await get_cron_job_by_code(session, job_data["code"], organization_id)
    if existing:
        scope = (
            "platform-wide"
            if organization_id is None
            else f"organization {organization_id}"
        )
        raise ValueError(
            f"Cron job with code '{job_data['code']}' already exists for {scope}"
        )

    # Calculate initial next_run_time
    next_run = calculate_next_run_time(schedule)

    job = CronJobDefinition(
        organization_id=org_uuid,
        name=job_data["name"],
        description=job_data.get("description"),
        code=job_data["code"],
        schedule_expression=schedule,
        is_active=job_data.get("is_active", True),
        is_enabled_by_default_for_new_orgs=job_data.get(
            "is_enabled_by_default_for_new_orgs", False
        ),
        parameters=job_data.get("parameters"),
        next_run_time=next_run,
    )

    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def get_cron_job_by_id(
    session: AsyncSession,
    job_id: str,
    organization_id: Optional[str],
) -> Optional[CronJobDefinition]:
    """
    Get cron job by ID within organization context.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The CronJobDefinition or None if not found
    """
    job_uuid = UUID(job_id)

    conditions: list[ColumnElement[bool]] = [
        CronJobDefinition.id == job_uuid,
        CronJobDefinition.deleted_time.is_(None),
    ]

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        conditions.append(
            or_(
                CronJobDefinition.organization_id == org_uuid,
                CronJobDefinition.organization_id.is_(None),
            )
        )

    result = await session.execute(select(CronJobDefinition).where(*conditions))
    return result.scalars().first()


async def get_cron_job_by_code(
    session: AsyncSession,
    code: str,
    organization_id: Optional[str],
) -> Optional[CronJobDefinition]:
    """
    Get cron job by code within organization context.

    Args:
        session: Database session
        code: Job code
        organization_id: Organization UUID string (None for platform-wide lookup)

    Returns:
        The CronJobDefinition or None if not found
    """
    org_uuid = UUID(organization_id) if organization_id else None

    conditions: list[ColumnElement[bool]] = [
        CronJobDefinition.code == code,
        CronJobDefinition.organization_id == org_uuid,
        CronJobDefinition.deleted_time.is_(None),
    ]

    result = await session.execute(select(CronJobDefinition).where(*conditions))
    return result.scalars().first()


async def get_cron_jobs(
    session: AsyncSession,
    organization_id: Optional[str],
    is_active: Optional[bool] = None,
    include_platform_wide: bool = True,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[CronJobDefinition], int]:
    """
    Get all cron jobs with pagination and filtering.

    Args:
        session: Database session
        organization_id: Organization UUID string (None for super admin)
        is_active: Filter by active status (None = all)
        include_platform_wide: Whether to include platform-wide jobs
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of cron jobs, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        CronJobDefinition.deleted_time.is_(None),
    ]

    if is_active is not None:
        conditions.append(CronJobDefinition.is_active.is_(is_active))

    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if include_platform_wide:
            conditions.append(
                or_(
                    CronJobDefinition.organization_id == org_uuid,
                    CronJobDefinition.organization_id.is_(None),
                )
            )
        else:
            conditions.append(CronJobDefinition.organization_id == org_uuid)

    # Count query
    count_query = select(func.count(CronJobDefinition.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query with ordering and pagination
    data_query = (
        select(CronJobDefinition)
        .where(*conditions)
        .order_by(
            CronJobDefinition.organization_id.desc().nulls_last(),
            CronJobDefinition.name.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    jobs = result.scalars().all()

    return list(jobs), total_count


async def update_cron_job(
    session: AsyncSession,
    job_id: str,
    organization_id: Optional[str],
    job_data: dict[str, Any],
) -> Optional[CronJobDefinition]:
    """
    Update a cron job definition.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string
        organization_id: Organization UUID string (None for super admin)
        job_data: Fields to update

    Returns:
        The updated CronJobDefinition or None if not found

    Raises:
        ValueError: If cron expression is invalid
    """
    job = await get_cron_job_by_id(session, job_id, organization_id)
    if not job:
        return None

    # Check organization ownership for updates
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if job.organization_id is not None and job.organization_id != org_uuid:
            return None

    # Validate cron expression if it's being updated
    if "schedule_expression" in job_data:
        schedule = job_data["schedule_expression"]
        if not is_valid_cron_expression(schedule):
            raise ValueError(f"Invalid cron expression: {schedule}")

    # Update allowed fields
    updatable_fields = [
        "name",
        "description",
        "schedule_expression",
        "is_active",
        "is_enabled_by_default_for_new_orgs",
        "parameters",
    ]

    schedule_changed = False
    for field in updatable_fields:
        if field in job_data:
            if field == "schedule_expression":
                schedule_changed = True
            setattr(job, field, job_data[field])

    # Recalculate next_run_time if schedule changed
    if schedule_changed:
        job.next_run_time = calculate_next_run_time(job.schedule_expression)

    await session.commit()
    await session.refresh(job)
    return job


async def soft_delete_cron_job(
    session: AsyncSession,
    job_id: str,
    organization_id: Optional[str],
) -> Optional[CronJobDefinition]:
    """
    Soft delete a cron job definition.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string
        organization_id: Organization UUID string (None for super admin)

    Returns:
        The deleted CronJobDefinition or None if not found
    """
    job = await get_cron_job_by_id(session, job_id, organization_id)
    if not job:
        return None

    # Check organization ownership
    if organization_id is not None:
        org_uuid = UUID(organization_id)
        if job.organization_id is not None and job.organization_id != org_uuid:
            return None

    job.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(job)
    return job


async def get_due_cron_jobs(
    session: AsyncSession,
) -> list[CronJobDefinition]:
    """
    Get all active cron jobs that are due to run (next_run_time <= now).

    This is used by the scheduler service and does NOT filter by organization
    since it processes all jobs across all organizations.

    Returns:
        List of CronJobDefinition instances ready to execute
    """
    now = datetime.now(timezone.utc)

    conditions: list[ColumnElement[bool]] = [
        CronJobDefinition.is_active.is_(True),
        CronJobDefinition.deleted_time.is_(None),
        CronJobDefinition.next_run_time <= now,
    ]

    result = await session.execute(
        select(CronJobDefinition)
        .where(*conditions)
        .order_by(CronJobDefinition.next_run_time.asc())
    )
    return list(result.scalars().all())


async def update_next_run_time(
    session: AsyncSession,
    job_id: str,
) -> Optional[CronJobDefinition]:
    """
    Update the next_run_time for a cron job based on its schedule expression.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string

    Returns:
        The updated CronJobDefinition or None if not found
    """
    job_uuid = UUID(job_id)

    result = await session.execute(
        select(CronJobDefinition).where(
            CronJobDefinition.id == job_uuid,
            CronJobDefinition.deleted_time.is_(None),
        )
    )
    job = result.scalars().first()

    if not job:
        return None

    job.next_run_time = calculate_next_run_time(job.schedule_expression)
    await session.commit()
    await session.refresh(job)
    return job


def calculate_next_run_time(schedule_expression: str) -> datetime:
    """
    Calculate the next run time from a cron expression.

    Args:
        schedule_expression: Cron expression string

    Returns:
        Next run datetime (timezone-aware UTC)

    Raises:
        ValueError: If cron expression is invalid
    """
    from croniter import croniter  # type: ignore[import-untyped]

    now = datetime.now(timezone.utc)

    try:
        cron = croniter(schedule_expression, now)
        next_run = cron.get_next(datetime)

        # Ensure timezone-aware UTC
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=timezone.utc)

        return next_run

    except Exception as exc:
        raise ValueError(f"Invalid cron expression: {schedule_expression}") from exc


def is_valid_cron_expression(expression: str) -> bool:
    """
    Validate a cron expression using croniter.

    Args:
        expression: Cron expression string

    Returns:
        True if valid, False otherwise
    """
    from croniter import croniter  # type: ignore[import-untyped]

    try:
        # Validate that the expression has exactly 5 fields (standard cron)
        fields = expression.split()
        if len(fields) != 5:
            return False

        # Try to create a croniter instance and get next time
        now = datetime.now(timezone.utc)
        cron = croniter(expression, now)
        cron.get_next()
        return True
    except Exception:
        return False


async def record_execution_start(
    session: AsyncSession,
    job_id: str,
) -> CronJobExecution:
    """
    Record the start of a cron job execution.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string

    Returns:
        The created CronJobExecution

    Raises:
        ValueError: If job not found
    """
    job_uuid = UUID(job_id)

    result = await session.execute(
        select(CronJobDefinition).where(
            CronJobDefinition.id == job_uuid,
            CronJobDefinition.deleted_time.is_(None),
        )
    )
    job = result.scalars().first()

    if not job:
        raise ValueError(f"Cron job {job_id} not found")

    # Update job status
    job.last_run_status = CronJobStatus.RUNNING.value
    job.last_run_time = datetime.now(timezone.utc)

    # Create execution record
    execution = CronJobExecution(
        cron_job_id=job_uuid,
        organization_id=job.organization_id,
        status=CronJobStatus.RUNNING.value,
        started_at=datetime.now(timezone.utc),
    )

    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    return execution


async def record_execution_complete(
    session: AsyncSession,
    execution_id: str,
    status: CronJobStatus,
    result: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> CronJobExecution:
    """
    Record the completion of a cron job execution.

    Args:
        session: Database session
        execution_id: CronJobExecution UUID string
        status: Final status (SUCCESS or ERROR)
        result: Optional result data
        error_message: Optional error message if status is ERROR

    Returns:
        The updated CronJobExecution

    Raises:
        ValueError: If execution not found
    """
    execution_uuid = UUID(execution_id)

    result_query = await session.execute(
        select(CronJobExecution).where(CronJobExecution.id == execution_uuid)
    )
    execution = result_query.scalars().first()

    if not execution:
        raise ValueError(f"Execution {execution_id} not found")

    # Update execution
    execution.completed_at = datetime.now(timezone.utc)
    execution.status = status.value
    execution.result = result
    execution.error_message = error_message

    # Update job definition status
    job_result = await session.execute(
        select(CronJobDefinition).where(CronJobDefinition.id == execution.cron_job_id)
    )
    job = job_result.scalars().first()

    if job:
        job.last_run_status = status.value
        job.last_run_error_message = error_message

    await session.commit()
    await session.refresh(execution)
    return execution


async def get_executions(
    session: AsyncSession,
    job_id: str,
    organization_id: Optional[str],
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CronJobExecution], int]:
    """
    Get execution history for a cron job.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string
        organization_id: Organization UUID string (None for super admin)
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of executions, total count)
    """
    job_uuid = UUID(job_id)

    # Verify job access
    job = await get_cron_job_by_id(session, job_id, organization_id)
    if not job:
        return [], 0

    conditions: list[ColumnElement[bool]] = [
        CronJobExecution.cron_job_id == job_uuid,
    ]

    # Count query
    count_query = select(func.count(CronJobExecution.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query with ordering and pagination
    data_query = (
        select(CronJobExecution)
        .where(*conditions)
        .order_by(CronJobExecution.created_time.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    executions = result.scalars().all()

    return list(executions), total_count


async def get_latest_execution(
    session: AsyncSession,
    job_id: str,
) -> Optional[CronJobExecution]:
    """
    Get the most recent execution for a cron job.

    Args:
        session: Database session
        job_id: CronJobDefinition UUID string

    Returns:
        The latest CronJobExecution or None
    """
    job_uuid = UUID(job_id)

    result = await session.execute(
        select(CronJobExecution)
        .where(CronJobExecution.cron_job_id == job_uuid)
        .order_by(CronJobExecution.created_time.desc())
        .limit(1)
    )
    return result.scalars().first()


async def get_cron_job_stats(
    session: AsyncSession,
    job_ids: list[UUID],
) -> dict[UUID, dict[str, Any]]:
    """
    Compute execution stats from cron_job_execution for the last 24 hours.

    Args:
        session: Database session
        job_ids: List of CronJobDefinition UUIDs to fetch stats for

    Returns:
        Dict keyed by cron_job_id with stats:
        executions_24h, failures_24h, failure_rate, avg_duration_ms, last_execution
    """
    if not job_ids:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    query = (
        select(
            CronJobExecution.cron_job_id,
            func.count().label("executions_24h"),
            func.count()
            .filter(CronJobExecution.status == CronJobStatus.ERROR.value)
            .label("failures_24h"),
            func.avg(
                extract(
                    "epoch",
                    CronJobExecution.completed_at - CronJobExecution.started_at,
                )
            )
            .filter(CronJobExecution.completed_at.isnot(None))
            .label("avg_duration_s"),
            func.max(CronJobExecution.started_at).label("last_execution"),
        )
        .where(
            CronJobExecution.cron_job_id.in_(job_ids),
            CronJobExecution.started_at >= cutoff,
        )
        .group_by(CronJobExecution.cron_job_id)
    )

    result = await session.execute(query)
    rows = result.all()

    stats: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        executions = row.executions_24h or 0
        failures = row.failures_24h or 0
        failure_rate = (failures / executions * 100) if executions > 0 else 0.0
        avg_duration_ms = (
            round(row.avg_duration_s * 1000) if row.avg_duration_s is not None else None
        )

        stats[row.cron_job_id] = {
            "executions_24h": executions,
            "failures_24h": failures,
            "failure_rate": failure_rate,
            "avg_duration_ms": avg_duration_ms,
            "last_execution": row.last_execution,
        }

    return stats
