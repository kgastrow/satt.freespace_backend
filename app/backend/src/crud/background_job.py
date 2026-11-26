"""
CRUD operations for BackgroundJobExecution.
Provides persistent execution tracking for ARQ background tasks.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.background_job import BackgroundJobExecution


async def record_bg_job_execution(
    session: AsyncSession,
    job_type: str,
    status: str,
    duration_ms: float,
    error_type: str | None = None,
    error_message: str | None = None,
) -> BackgroundJobExecution:
    """
    Insert a single background job execution record.

    Args:
        session: Database session
        job_type: Task function name (e.g. "send_email_task")
        status: "success" or "failure"
        duration_ms: Execution duration in milliseconds
        error_type: Exception class name on failure
        error_message: Error message on failure

    Returns:
        The created BackgroundJobExecution record
    """
    now = datetime.now(timezone.utc)
    started_at = now - timedelta(milliseconds=duration_ms)

    execution = BackgroundJobExecution(
        job_type=job_type,
        started_at=started_at,
        completed_at=now,
        status=status,
        duration_ms=duration_ms,
        error_type=error_type,
        error_message=error_message,
    )
    session.add(execution)
    await session.commit()
    return execution


async def get_bg_job_stats(
    session: AsyncSession,
    job_types: list[str],
    window_hours: int = 24,
) -> dict[str, dict[str, Any]]:
    """
    Compute execution stats from background_job_execution for the given window.

    Args:
        session: Database session
        job_types: List of job type codes to fetch stats for
        window_hours: Lookback window in hours (default: 24)

    Returns:
        Dict keyed by job_type with stats:
        executions_24h, failures_24h, failure_rate, avg_duration_ms, last_execution
    """
    if not job_types:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    query = (
        select(
            BackgroundJobExecution.job_type,
            func.count().label("executions_24h"),
            func.count()
            .filter(BackgroundJobExecution.status == "failure")
            .label("failures_24h"),
            func.avg(BackgroundJobExecution.duration_ms)
            .filter(BackgroundJobExecution.duration_ms.isnot(None))
            .label("avg_duration_ms"),
            func.max(BackgroundJobExecution.started_at).label("last_execution"),
        )
        .where(
            BackgroundJobExecution.job_type.in_(job_types),
            BackgroundJobExecution.started_at >= cutoff,
        )
        .group_by(BackgroundJobExecution.job_type)
    )

    result = await session.execute(query)
    rows = result.all()

    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        executions = row.executions_24h or 0
        failures = row.failures_24h or 0
        failure_rate = (failures / executions * 100) if executions > 0 else 0.0
        avg_duration = (
            round(row.avg_duration_ms) if row.avg_duration_ms is not None else None
        )

        stats[row.job_type] = {
            "executions_24h": executions,
            "failures_24h": failures,
            "failure_rate": failure_rate,
            "avg_duration_ms": avg_duration,
            "last_execution": row.last_execution,
        }

    return stats


async def cleanup_old_bg_job_executions(
    session: AsyncSession,
    retention_hours: int = 168,
) -> int:
    """
    Delete background job execution records older than retention period.

    Args:
        session: Database session
        retention_hours: Hours to retain records (default: 168 = 7 days)

    Returns:
        Number of deleted records
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)

    result = await session.execute(
        delete(BackgroundJobExecution).where(
            BackgroundJobExecution.created_time < cutoff
        )
    )
    await session.commit()
    return result.rowcount or 0
