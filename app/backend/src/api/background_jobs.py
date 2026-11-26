"""
Background jobs monitoring API endpoints.
All endpoints require super admin access (get_current_super_admin dependency).
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.constants.job_types import (
    get_job_type,
    get_non_cron_job_types,
)
from src.crud.system_config import get_system_config_by_key, update_system_config
from src.logger.logger import Logger
from src.serialisers.background_jobs import (
    BackgroundJobsStatsResponse,
    JobTypeInfo,
    JobTypesListResponse,
    JobTypeStats,
    QueueHealthResponse,
    StuckJob,
    ToggleJobTypeRequest,
    ToggleJobTypeResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.job_stats import job_stats_service
from src.services.queue_health import queue_health_service


router = APIRouter(prefix="/background-jobs", tags=["background-jobs"])


async def _get_job_enabled(session: AsyncSession, job_type: str) -> bool:
    """Get job enabled status from SystemConfig."""
    config_key = f"jobs.{job_type}.enabled"
    config = await get_system_config_by_key(session, config_key)
    if config is None:
        return True  # Default to enabled if not configured
    return config.value is True


@router.get("/stats", response_model=BackgroundJobsStatsResponse)
async def get_background_jobs_stats(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get execution statistics for all background job types (super admin only).

    Returns execution counts, failure rates, and average durations for the last 24 hours.
    Excludes cron jobs which are managed via the dedicated cron jobs page.
    """
    try:
        # Get non-cron job types only
        non_cron_job_types = get_non_cron_job_types()
        non_cron_codes = [jt.code for jt in non_cron_job_types]

        # Get stats from database (persistent) instead of Redis
        from src.crud.background_job import get_bg_job_stats

        stats_by_type = await get_bg_job_stats(session, non_cron_codes)

        job_stats_list = []
        total_executions = 0
        total_failures = 0

        for job_def in non_cron_job_types:
            if job_def.is_cron:
                continue

            stats = stats_by_type.get(job_def.code, {})

            # Get enabled status from SystemConfig
            enabled = await _get_job_enabled(session, job_def.code)

            executions = stats.get("executions_24h", 0)
            failures = stats.get("failures_24h", 0)

            job_stats_list.append(
                JobTypeStats(
                    job_type=job_def.code,
                    name=job_def.name,
                    description=job_def.description,
                    category=job_def.category,
                    is_cron=job_def.is_cron,
                    enabled=enabled,
                    executions_24h=executions,
                    failures_24h=failures,
                    failure_rate=stats.get("failure_rate", 0.0),
                    avg_duration_ms=stats.get("avg_duration_ms") or 0.0,
                    last_execution=stats.get("last_execution"),
                )
            )

            total_executions += executions
            total_failures += failures

        return BackgroundJobsStatsResponse(
            job_stats=job_stats_list,
            total_executions_24h=total_executions,
            total_failures_24h=total_failures,
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in get_background_jobs_stats: {e}\n{error_tb}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/queue-health", response_model=QueueHealthResponse)
async def get_queue_health(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
):
    """
    Get queue health status (super admin only).

    Returns information about queue depth, stuck jobs, and worker status.
    """
    try:
        health = await queue_health_service.check_health()

        stuck_jobs = [
            StuckJob(
                job_id=job["job_id"],
                function=job["function"],
                start_time=job["start_time"],
                duration_minutes=job["duration_minutes"],
            )
            for job in health.get("stuck_jobs", [])
        ]

        return QueueHealthResponse(
            is_healthy=health["is_healthy"],
            issues=health.get("issues", []),
            queue_depth=health["queue_depth"],
            depth_threshold=health["depth_threshold"],
            stuck_jobs_count=health["stuck_jobs_count"],
            stuck_jobs=stuck_jobs,
            workers_online=health["workers_online"],
            workers_offline=health["workers_offline"],
            total_workers=health["total_workers"],
            checked_at=health["checked_at"],
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in get_queue_health: {e}\n{error_tb}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.get("/types", response_model=JobTypesListResponse)
async def list_job_types(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List all known job types with their enabled status (super admin only).
    Excludes cron jobs which are managed via the dedicated cron jobs page.
    """
    try:
        all_job_types = get_non_cron_job_types()
        job_types_list = []

        for job_def in all_job_types:
            enabled = await _get_job_enabled(session, job_def.code)
            job_types_list.append(
                JobTypeInfo(
                    code=job_def.code,
                    name=job_def.name,
                    description=job_def.description,
                    category=job_def.category,
                    is_cron=job_def.is_cron,
                    enabled=enabled,
                )
            )

        return JobTypesListResponse(items=job_types_list)
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in list_job_types: {e}\n{error_tb}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@router.patch("/types/{job_type}/toggle", response_model=ToggleJobTypeResponse)
async def toggle_job_type(
    job_type: str,
    request: ToggleJobTypeRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Enable or disable a job type (super admin only).

    When disabled, jobs of this type will be skipped when they would normally execute.
    """
    # Validate job type exists
    job_def = get_job_type(job_type)
    if job_def is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job type '{job_type}' not found",
        )

    try:
        config_key = f"jobs.{job_type}.enabled"

        # Get old value for audit
        old_config = await get_system_config_by_key(session, config_key)
        old_value = old_config.value if old_config else True

        # Update SystemConfig
        await update_system_config(
            session=session,
            key=config_key,
            value=request.enabled,
            description=f"Enable/disable {job_def.name} background job",
            updated_by_user_id=str(current_user.id),
        )

        # Update Redis cache for fast lookup in workers
        await job_stats_service.set_job_enabled_cache(job_type, request.enabled)

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="BackgroundJobConfig",
            resource_id=job_type,
            old_values={"enabled": old_value},
            new_values={"enabled": request.enabled},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        action = "enabled" if request.enabled else "disabled"
        return ToggleJobTypeResponse(
            job_type=job_type,
            enabled=request.enabled,
            message=f"Job type '{job_def.name}' has been {action}",
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in toggle_job_type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
