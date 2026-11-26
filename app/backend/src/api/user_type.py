"""
User type management API endpoints.
User types are system-wide. Super admin only for write operations.
Public endpoint for active user types.
"""

from datetime import datetime, timezone
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.crud import user as user_crud
from src.crud import user_user_type as user_user_type_crud
from src.crud.user_type import (
    create,
    get_all,
    get_by_id,
    soft_delete,
    update,
)
from src.logger.logger import Logger
from src.models.user_user_type import OnboardingStatus
from src.serialisers.onboarding import (
    CreateUserTypeRequest,
    UpdateUserTypeRequest,
    UserTypeListResponse,
    UserTypeResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(tags=["user-types"])


@router.post(
    "/admin/user-types",
    response_model=UserTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user_type_endpoint(
    request: CreateUserTypeRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new user type (super admin only)."""
    try:
        new_type = await create(session=session, data=request.model_dump())

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserType",
            resource_id=str(new_type.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"name": new_type.name, "code": new_type.code},
        )

        return UserTypeResponse.model_validate(new_type)
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
        Logger.error(f"Failed to create user type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/admin/user-types", response_model=UserTypeListResponse)
async def list_user_types_admin_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all user types including inactive (super admin only)."""
    try:
        user_types, total = await get_all(session=session, limit=limit, offset=offset)
        type_responses = [UserTypeResponse.model_validate(ut) for ut in user_types]
        return UserTypeListResponse(
            items=type_responses, total=total, limit=limit, offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to list user types (admin): {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/admin/user-types/{user_type_id}", response_model=UserTypeResponse)
async def get_user_type_endpoint(
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a user type by ID (super admin only)."""
    try:
        user_type = await get_by_id(session=session, id=user_type_id)
        if not user_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )

        return UserTypeResponse.model_validate(user_type)
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
        Logger.error(f"Failed to get user type by ID: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/admin/user-types/{user_type_id}", response_model=UserTypeResponse)
async def update_user_type_endpoint(
    user_type_id: str,
    request: UpdateUserTypeRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a user type (super admin only)."""
    try:
        # Get current state for change tracking
        existing_type = await get_by_id(session=session, id=user_type_id)
        if not existing_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )
        old_values = {
            "name": existing_type.name,
            "code": existing_type.code,
            "is_active": existing_type.is_active,
        }

        updated_type = await update(
            session=session,
            id=user_type_id,
            data=request.model_dump(exclude_unset=True),
        )

        # Log audit event
        new_values = {
            "name": updated_type.name,
            "code": updated_type.code,
            "is_active": updated_type.is_active,
        }
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserType",
            resource_id=str(updated_type.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UserTypeResponse.model_validate(updated_type)
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
        Logger.error(f"Failed to update user type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete(
    "/admin/user-types/{user_type_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_user_type_endpoint(
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Soft delete a user type (super admin only)."""
    try:
        # Get type data before deletion for audit log
        existing_type = await get_by_id(session=session, id=user_type_id)
        if not existing_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )
        type_data = {
            "name": existing_type.name,
            "code": existing_type.code,
        }

        await soft_delete(session=session, id=user_type_id)

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserType",
            resource_id=user_type_id,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=type_data,
        )

        return None
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
        Logger.error(f"Failed to delete user type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/user-types", response_model=UserTypeListResponse)
async def list_active_user_types_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List active user types (public endpoint for authenticated users)."""
    try:
        user_types, _ = await get_all(session=session, limit=1000, offset=0)
        # Filter to only active types
        active_types = [ut for ut in user_types if ut.is_active]
        # Apply pagination after filtering
        total = len(active_types)
        paginated_types = active_types[offset : offset + limit]
        type_responses = [UserTypeResponse.model_validate(ut) for ut in paginated_types]
        return UserTypeListResponse(
            items=type_responses, total=total, limit=limit, offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to list active user types: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Admin User Type Assignment Endpoints
# =============================================================================


class AssignUserTypeResponse(BaseModel):
    """Response for user type assignment."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str
    user_type_id: str


class RevokeUserTypeResponse(BaseModel):
    """Response for user type revocation."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str
    user_type_id: str


class ResetOnboardingResponse(BaseModel):
    """Response for onboarding reset."""

    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    user_id: str
    user_type_id: str


@router.post(
    "/admin/users/{user_id}/user-types/{user_type_id}",
    response_model=AssignUserTypeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def admin_assign_user_type(
    user_id: str,
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Assign a user type to a user (super admin only).

    This allows admins to manually assign user types to users,
    which may trigger onboarding workflows.
    """
    try:
        organization_id = str(current_user.organization_id)

        # Verify user exists
        user = await user_crud.get_user_by_id(session, user_id, organization_id)
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Verify user type exists
        user_type = await get_by_id(session, user_type_id)
        if not user_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )

        # Check if already assigned
        existing = await user_user_type_crud.get_by_user_and_type(
            session, user_id, user_type_id, organization_id
        )
        if existing:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already has this user type assigned",
                detail_code="user_type.already_assigned",
            )

        # Create the assignment
        await user_user_type_crud.create(
            session,
            {"user_id": user_id, "user_type_id": user_type_id},
            organization_id,
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserUserType",
            resource_id=user_id,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_id": user_id,
                "user_type_id": user_type_id,
                "user_type_name": user_type.name,
            },
        )

        return AssignUserTypeResponse(
            message="User type assigned successfully",
            message_code="user_type.assigned",
            user_id=user_id,
            user_type_id=user_type_id,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to assign user type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete(
    "/admin/users/{user_id}/user-types/{user_type_id}",
    response_model=RevokeUserTypeResponse,
)
async def admin_revoke_user_type(
    user_id: str,
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Revoke a user type from a user (super admin only).

    This soft-deletes the user-user type association.
    """
    try:
        organization_id = str(current_user.organization_id)

        # Verify user exists
        user = await user_crud.get_user_by_id(session, user_id, organization_id)
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Verify user type exists
        user_type = await get_by_id(session, user_type_id)
        if not user_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )

        # Get the assignment
        existing = await user_user_type_crud.get_by_user_and_type(
            session, user_id, user_type_id, organization_id
        )
        if not existing:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User does not have this user type assigned",
                detail_code="user_type.not_assigned",
            )

        # Soft delete the assignment
        existing.deleted_time = datetime.now(timezone.utc)
        await session.commit()

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserUserType",
            resource_id=str(existing.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_id": user_id,
                "user_type_id": user_type_id,
                "user_type_name": user_type.name,
            },
        )

        return RevokeUserTypeResponse(
            message="User type revoked successfully",
            message_code="user_type.revoked",
            user_id=user_id,
            user_type_id=user_type_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to revoke user type: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post(
    "/admin/users/{user_id}/user-types/{user_type_id}/reset-onboarding",
    response_model=ResetOnboardingResponse,
)
async def admin_reset_user_type_onboarding(
    user_id: str,
    user_type_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Reset onboarding status for a user's user type (super admin only).

    This resets the onboarding status to pending, allowing the user
    to redo the onboarding process.
    """
    try:
        organization_id = str(current_user.organization_id)

        # Verify user exists
        user = await user_crud.get_user_by_id(session, user_id, organization_id)
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Verify user type exists
        user_type = await get_by_id(session, user_type_id)
        if not user_type:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User type not found",
                detail_code="user_type.not_found",
            )

        # Get the assignment
        existing = await user_user_type_crud.get_by_user_and_type(
            session, user_id, user_type_id, organization_id
        )
        if not existing:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User does not have this user type assigned",
                detail_code="user_type.not_assigned",
            )

        # Store old values for audit
        old_status = existing.onboarding_status.value
        old_onboarded_at = (
            existing.onboarded_at.isoformat() if existing.onboarded_at else None
        )

        # Reset onboarding status
        await user_user_type_crud.update_status(
            session=session,
            id=str(existing.id),
            status=OnboardingStatus.PENDING,
            organization_id=organization_id,
            onboarded_at=None,
            requires_admin_attention=False,
        )

        # Update onboarded_at to None (need to do this separately as update_status sets it)
        existing.onboarded_at = None
        await session.commit()

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserUserType",
            resource_id=str(existing.id),
            old_values={
                "onboarding_status": old_status,
                "onboarded_at": old_onboarded_at,
            },
            new_values={
                "onboarding_status": OnboardingStatus.PENDING.value,
                "onboarded_at": None,
            },
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return ResetOnboardingResponse(
            message="Onboarding reset successfully",
            message_code="user_type.onboarding_reset",
            user_id=user_id,
            user_type_id=user_type_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to reset onboarding: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
