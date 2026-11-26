"""
Cron job management API endpoints.
All endpoints require super admin access (get_current_super_admin dependency).
"""

import traceback
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.cron_job import (
    create_cron_job,
    get_cron_job_by_id,
    get_cron_job_stats,
    get_cron_jobs,
    get_executions,
    soft_delete_cron_job,
    update_cron_job,
)
from src.logger.logger import Logger
from src.serialisers.cron_job import (
    CreateCronJobRequest,
    CronJobConfigKeyResponse,
    CronJobConfigResponse,
    CronJobExecutionListResponse,
    CronJobExecutionResponse,
    CronJobListResponse,
    CronJobResponse,
    ToggleCronJobRequest,
    TriggerCronJobRequest,
    TriggerCronJobResponse,
    UpdateCronJobConfigRequest,
    UpdateCronJobRequest,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/cron-jobs", tags=["cron-jobs"])


@router.post("", response_model=CronJobResponse, status_code=status.HTTP_201_CREATED)
async def create_cron_job_endpoint(
    request: CreateCronJobRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new cron job definition (super admin only).

    Can create platform-wide jobs (organization_id=None) or organization-scoped jobs.
    """
    try:
        # Determine organization_id based on is_platform_wide flag
        organization_id = (
            None if request.is_platform_wide else current_user.organization_id
        )

        # Extract job data (exclude is_platform_wide as it's not part of model)
        job_data = request.model_dump(exclude={"is_platform_wide"})

        new_job = await create_cron_job(
            session=session,
            job_data=job_data,
            organization_id=organization_id,
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="CronJobDefinition",
            resource_id=str(new_job.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "name": new_job.name,
                "code": new_job.code,
                "schedule": new_job.schedule_expression,
                "is_platform_wide": new_job.organization_id is None,
            },
        )

        return CronJobResponse.from_orm_cron_job(new_job)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in create_cron_job_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("", response_model=CronJobListResponse)
async def list_cron_jobs_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    filter_is_active: Optional[bool] = Query(
        None, alias="filter[is_active]", description="Filter by active status"
    ),
    filter_organization_id: Optional[str] = Query(
        None, alias="filter[organization_id]", description="Filter by organization ID"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """
    List all cron jobs with optional filtering (super admin only).

    Super admins can see all platform-wide and organization-scoped jobs.
    Includes execution statistics from the last 24 hours.
    """
    try:
        # Super admin can filter by specific organization or see all (None)
        filter_org_id = filter_organization_id if filter_organization_id else None

        jobs, total = await get_cron_jobs(
            session=session,
            organization_id=filter_org_id,
            is_active=filter_is_active,
            include_platform_wide=True,
            limit=limit,
            offset=offset,
        )

        # Fetch execution stats from DB for the last 24 hours
        job_ids = [job.id for job in jobs]
        stats_by_id = await get_cron_job_stats(session, job_ids)

        cron_jobs = []
        for job in jobs:
            stats = stats_by_id.get(job.id, {})
            cron_jobs.append(
                CronJobResponse.from_orm_cron_job(
                    job,
                    executions_24h=stats.get("executions_24h", 0),
                    failures_24h=stats.get("failures_24h", 0),
                    failure_rate=stats.get("failure_rate", 0.0),
                    avg_duration_ms=stats.get("avg_duration_ms"),
                )
            )

        return CronJobListResponse(
            items=cron_jobs,
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in list_cron_jobs_endpoint: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{job_id}", response_model=CronJobResponse)
async def get_cron_job_endpoint(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a cron job by ID (super admin only)."""
    try:
        # Super admin can access all jobs (pass None for organization_id)
        job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )

        if not job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        return CronJobResponse.from_orm_cron_job(job)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in get_cron_job_endpoint: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{job_id}", response_model=CronJobResponse)
async def update_cron_job_endpoint(
    job_id: str,
    request: UpdateCronJobRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a cron job definition (super admin only).

    When schedule_expression is updated, next_run_time is automatically recalculated.
    """
    try:
        # Get current state for change tracking
        existing_job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not existing_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        old_values = {
            "name": existing_job.name,
            "schedule": existing_job.schedule_expression,
            "is_active": existing_job.is_active,
            "parameters": existing_job.parameters,
        }

        # Super admin can update any job
        updated_job = await update_cron_job(
            session=session,
            job_id=job_id,
            organization_id=None,
            job_data=request.model_dump(exclude_unset=True),
        )

        if not updated_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        # Log audit event
        new_values = {
            "name": updated_job.name,
            "schedule": updated_job.schedule_expression,
            "is_active": updated_job.is_active,
            "parameters": updated_job.parameters,
        }
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="CronJobDefinition",
            resource_id=str(updated_job.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return CronJobResponse.from_orm_cron_job(updated_job)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in update_cron_job_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{job_id}", status_code=status.HTTP_200_OK)
async def delete_cron_job_endpoint(
    job_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Soft delete a cron job definition (super admin only)."""
    try:
        # Get job data before deletion for audit log
        existing_job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not existing_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        job_data = {
            "name": existing_job.name,
            "code": existing_job.code,
            "schedule": existing_job.schedule_expression,
        }

        deleted_job = await soft_delete_cron_job(
            session=session,
            job_id=job_id,
            organization_id=None,
        )

        if not deleted_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="CronJobDefinition",
            resource_id=str(deleted_job.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=job_data,
        )

        return {
            "message": "Cron job deleted successfully",
            "message_code": get_response_code("cron_job.deleted"),
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in delete_cron_job_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.patch("/{job_id}/toggle", response_model=CronJobResponse)
async def toggle_cron_job_endpoint(
    job_id: str,
    request: ToggleCronJobRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Toggle a cron job's active status (super admin only).

    This is a convenience endpoint for enabling/disabling jobs.
    """
    try:
        existing_job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not existing_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        old_status = existing_job.is_active

        updated_job = await update_cron_job(
            session=session,
            job_id=job_id,
            organization_id=None,
            job_data={"is_active": request.is_active},
        )

        if not updated_job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="CronJobDefinition",
            resource_id=str(updated_job.id),
            old_values={"is_active": old_status},
            new_values={"is_active": updated_job.is_active},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return CronJobResponse.from_orm_cron_job(updated_job)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in toggle_cron_job_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{job_id}/executions", response_model=CronJobExecutionListResponse)
async def list_cron_job_executions_endpoint(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(50, ge=1, le=500, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """Get execution history for a cron job (super admin only)."""
    try:
        # Super admin can access all job executions
        executions, total = await get_executions(
            session=session,
            job_id=job_id,
            organization_id=None,
            limit=limit,
            offset=offset,
        )

        execution_responses = [
            CronJobExecutionResponse.model_validate(execution)
            for execution in executions
        ]

        return CronJobExecutionListResponse(
            items=execution_responses,
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in list_cron_job_executions_endpoint: {e}\n{error_tb}"
        )
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


def _ensure_cron_handlers_registered():
    """Ensure cron job handlers are registered for manual triggering."""
    from src.services.cron_scheduler import cron_scheduler_service

    cron_scheduler_service.register_all_handlers()


@router.post(
    "/{job_id}/trigger",
    response_model=TriggerCronJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_cron_job_endpoint(
    job_id: str,
    request: TriggerCronJobRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Manually trigger a cron job execution (super admin only).

    Executes the cron job handler immediately and returns the execution ID.
    """
    from src.services.cron_scheduler import cron_scheduler_service

    try:
        # Verify job exists
        job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        # Ensure handlers are registered
        _ensure_cron_handlers_registered()

        # Log audit event before execution
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="CronJobExecution",
            resource_id=str(job.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "cron_job_id": str(job.id),
                "cron_job_name": job.name,
                "manually_triggered": True,
            },
        )

        # Execute the job (this creates execution record, runs handler, and records result)
        await cron_scheduler_service.execute_cron_job(
            session,
            job_id=str(job.id),
            job_code=job.code,
            job_parameters=job.parameters or {},
        )

        # Get the latest execution to return its ID
        executions, _ = await get_executions(
            session=session,
            job_id=str(job.id),
            organization_id=None,  # Super admin endpoint
            limit=1,
        )
        execution_id = executions[0].id if executions else job.id

        return TriggerCronJobResponse(
            message="Cron job triggered successfully",
            message_code=get_response_code("cron_job.triggered"),
            execution_id=execution_id,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in trigger_cron_job_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{job_id}/config", response_model=CronJobConfigResponse)
async def get_cron_job_config_endpoint(
    job_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get configuration keys and current values for a cron job (super admin only).

    Returns the SystemConfig keys associated with this cron job, along with their
    current values and metadata for display in the UI.
    """
    from src.constants.cron_job_config import get_config_keys_for_job, has_config_keys
    from src.crud.system_config import get_system_config_by_key

    try:
        # Verify job exists
        job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        job_code = job.code
        config_keys = get_config_keys_for_job(job_code)

        # Build response with current values
        config_key_responses = []
        for config_key in config_keys:
            # Get current value from SystemConfig
            system_config = await get_system_config_by_key(session, config_key.key)
            current_value = system_config.value if system_config else None

            config_key_responses.append(
                CronJobConfigKeyResponse(
                    key=config_key.key,
                    value_type=config_key.value_type,
                    default=config_key.default,
                    current_value=current_value,
                    label=config_key.label,
                    description=config_key.description,
                    min_value=config_key.min_value,
                    max_value=config_key.max_value,
                )
            )

        return CronJobConfigResponse(
            job_code=job_code,
            has_config=has_config_keys(job_code),
            config_keys=config_key_responses,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in get_cron_job_config_endpoint: {e}\n{error_tb}"
        )
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{job_id}/config", response_model=CronJobConfigResponse)
async def update_cron_job_config_endpoint(
    job_id: str,
    request: UpdateCronJobConfigRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a configuration value for a cron job (super admin only).

    Updates the SystemConfig entry for the specified key. The key must be
    one of the valid config keys for this cron job.
    """
    from src.constants.cron_job_config import get_config_keys_for_job, has_config_keys
    from src.crud.system_config import get_system_config_by_key, update_system_config

    try:
        # Verify job exists
        job = await get_cron_job_by_id(
            session=session, job_id=job_id, organization_id=None
        )
        if not job:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Cron job not found",
                detail_code="cron_job.not_found",
            )

        job_code = job.code
        config_keys = get_config_keys_for_job(job_code)

        # Verify the key is valid for this job
        valid_keys = {ck.key for ck in config_keys}
        if request.key not in valid_keys:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid config key '{request.key}' for job '{job_code}'",
                detail_code="cron_job.invalid_config_key",
            )

        # Find the config key definition for validation
        config_key_def = next(ck for ck in config_keys if ck.key == request.key)

        # Validate value based on type
        validated_value = request.value
        if config_key_def.value_type == "integer":
            try:
                int_value = int(request.value)
                if (
                    config_key_def.min_value is not None
                    and int_value < config_key_def.min_value
                ):
                    raise create_http_exception(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Value must be at least {config_key_def.min_value}",
                        detail_code="cron_job.config_value_too_low",
                    )
                if (
                    config_key_def.max_value is not None
                    and int_value > config_key_def.max_value
                ):
                    raise create_http_exception(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Value must be at most {config_key_def.max_value}",
                        detail_code="cron_job.config_value_too_high",
                    )
            except ValueError:
                raise create_http_exception(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Value must be a valid integer",
                    detail_code="cron_job.config_value_invalid",
                )

        # Get old value for audit
        old_config = await get_system_config_by_key(session, request.key)
        old_value = old_config.value if old_config else None

        # Update the config
        await update_system_config(
            session=session,
            key=request.key,
            value=validated_value,
            description=config_key_def.description,
            updated_by_user_id=str(current_user.id),
        )

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemConfig",
            resource_id=request.key,
            old_values={"value": old_value},
            new_values={"value": validated_value},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        # Return updated config
        config_key_responses = []
        for config_key in config_keys:
            system_config = await get_system_config_by_key(session, config_key.key)
            current_value = system_config.value if system_config else None

            config_key_responses.append(
                CronJobConfigKeyResponse(
                    key=config_key.key,
                    value_type=config_key.value_type,
                    default=config_key.default,
                    current_value=current_value,
                    label=config_key.label,
                    description=config_key.description,
                    min_value=config_key.min_value,
                    max_value=config_key.max_value,
                )
            )

        return CronJobConfigResponse(
            job_code=job_code,
            has_config=has_config_keys(job_code),
            config_keys=config_key_responses,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in update_cron_job_config_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
