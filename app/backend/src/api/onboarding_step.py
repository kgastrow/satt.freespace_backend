"""
Onboarding step management API endpoints.
Onboarding steps are system-wide and scoped to user types.
Super admin only for write operations.
"""

import traceback
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.exceptions import create_http_exception
from src.crud.onboarding_step import (
    create,
    get_all_for_user_type,
    get_by_id,
    reorder,
    soft_delete,
    update,
)
from src.logger.logger import Logger
from src.serialisers.onboarding import (
    CreateOnboardingStepRequest,
    OnboardingStepListResponse,
    OnboardingStepResponse,
    ReorderStepsRequest,
    UpdateOnboardingStepRequest,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/admin/onboarding-steps", tags=["onboarding-steps"])


@router.post(
    "", response_model=OnboardingStepResponse, status_code=status.HTTP_201_CREATED
)
async def create_onboarding_step_endpoint(
    request: CreateOnboardingStepRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new onboarding step (super admin only)."""
    try:
        new_step = await create(session=session, data=request.model_dump())

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="OnboardingStep",
            resource_id=str(new_step.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "name": new_step.name,
                "code": new_step.code,
                "user_type_id": str(new_step.user_type_id),
            },
        )

        return OnboardingStepResponse.model_validate(new_step)
    except ValueError as e:
        Logger.warning(f"ValueError in create onboarding step: {e}")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data",
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error creating onboarding step: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/user-type/{user_type_id}", response_model=OnboardingStepListResponse)
async def list_steps_for_user_type_endpoint(
    user_type_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all onboarding steps for a user type (super admin only)."""
    try:
        steps = await get_all_for_user_type(
            session=session, user_type_id=str(user_type_id)
        )
        # Apply pagination
        total = len(steps)
        paginated_steps = steps[offset : offset + limit]
        step_responses = [
            OnboardingStepResponse.model_validate(step) for step in paginated_steps
        ]
        return OnboardingStepListResponse(
            items=step_responses, total=total, limit=limit, offset=offset
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error listing onboarding steps for user type {user_type_id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{step_id}", response_model=OnboardingStepResponse)
async def get_onboarding_step_endpoint(
    step_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get an onboarding step by ID (super admin only)."""
    try:
        step = await get_by_id(session=session, id=str(step_id))
        if not step:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding step not found",
                detail_code="onboarding_step.not_found",
            )

        return OnboardingStepResponse.model_validate(step)
    except ValueError as e:
        Logger.warning(f"ValueError in get onboarding step: {e}")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data",
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting onboarding step {step_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{step_id}", response_model=OnboardingStepResponse)
async def update_onboarding_step_endpoint(
    step_id: UUID,
    request: UpdateOnboardingStepRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update an onboarding step (super admin only)."""
    try:
        # Get current state for change tracking
        existing_step = await get_by_id(session=session, id=str(step_id))
        if not existing_step:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding step not found",
                detail_code="onboarding_step.not_found",
            )
        old_values = {
            "name": existing_step.name,
            "code": existing_step.code,
            "step_order": existing_step.step_order,
            "is_active": existing_step.is_active,
        }

        updated_step = await update(
            session=session,
            id=str(step_id),
            data=request.model_dump(exclude_unset=True),
        )

        # Log audit event
        new_values = {
            "name": updated_step.name,
            "code": updated_step.code,
            "step_order": updated_step.step_order,
            "is_active": updated_step.is_active,
        }
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="OnboardingStep",
            resource_id=str(updated_step.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return OnboardingStepResponse.model_validate(updated_step)
    except ValueError as e:
        Logger.warning(f"ValueError in update onboarding step: {e}")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data",
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error updating onboarding step {step_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post(
    "/user-type/{user_type_id}/reorder", status_code=status.HTTP_204_NO_CONTENT
)
async def reorder_steps_endpoint(
    user_type_id: UUID,
    request: ReorderStepsRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Reorder onboarding steps for a user type (super admin only)."""
    try:
        await reorder(
            session=session,
            user_type_id=str(user_type_id),
            step_orders=request.steps,
        )

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="OnboardingStep",
            resource_id=str(user_type_id),
            old_values={},
            new_values={"reordered_steps": request.steps},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return None
    except ValueError as e:
        Logger.warning(f"ValueError in reorder onboarding steps: {e}")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data",
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error reordering onboarding steps for user type {user_type_id}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_onboarding_step_endpoint(
    step_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Soft delete an onboarding step (super admin only)."""
    try:
        # Get step data before deletion for audit log
        existing_step = await get_by_id(session=session, id=str(step_id))
        if not existing_step:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Onboarding step not found",
                detail_code="onboarding_step.not_found",
            )
        step_data = {
            "name": existing_step.name,
            "code": existing_step.code,
            "user_type_id": str(existing_step.user_type_id),
        }

        await soft_delete(session=session, id=str(step_id))

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="OnboardingStep",
            resource_id=str(step_id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=step_data,
        )

        return None
    except ValueError as e:
        Logger.warning(f"ValueError in delete onboarding step: {e}")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request data",
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error deleting onboarding step {step_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
