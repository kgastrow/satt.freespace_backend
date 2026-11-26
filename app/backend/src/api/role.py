"""
Global role management API endpoints.
Roles are system-wide. Read access via roles:read permission,
write/delete restricted to super admins only.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.role import (
    create_role,
    delete_role,
    get_role_by_id,
    list_roles,
    update_role,
)
from src.logger.logger import Logger
from src.serialisers.role import (
    CreateRoleRequest,
    CreateRoleResponse,
    DeleteRoleResponse,
    GetRoleResponse,
    ListRolesResponse,
    UpdateRoleRequest,
    UpdateRoleResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("", response_model=CreateRoleResponse)
async def create_role_endpoint(
    request: CreateRoleRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new global role (requires super admin access)."""
    try:
        new_role = await create_role(session=session, request=request.model_dump())

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(new_role.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "name": new_role.name,
                "description": new_role.description,
                "is_default_on_registration": new_role.is_default_on_registration,
            },
        )

        response = GetRoleResponse(
            id=new_role.id,
            name=new_role.name,
            description=new_role.description,
            is_default_on_registration=new_role.is_default_on_registration,
            created_time=new_role.created_time.isoformat(),
            updated_time=new_role.updated_time.isoformat(),
        )
        return CreateRoleResponse(
            message="Role created successfully",
            message_code=get_response_code("role.created"),
            role=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error creating role: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("", response_model=ListRolesResponse)
async def list_roles_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("roles:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all global roles (requires roles:read permission)."""
    try:
        roles, total = await list_roles(session=session, limit=limit, offset=offset)
        role_responses = [
            GetRoleResponse(
                id=role.id,
                name=role.name,
                description=role.description,
                is_default_on_registration=role.is_default_on_registration,
                created_time=role.created_time.isoformat(),
                updated_time=role.updated_time.isoformat(),
            )
            for role in roles
        ]
        return ListRolesResponse(
            items=role_responses, total=total, limit=limit, offset=offset
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error listing roles: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{role_id}", response_model=GetRoleResponse)
async def get_role_endpoint(
    role_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("roles:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a global role by ID (requires roles:read permission)."""
    try:
        role = await get_role_by_id(session=session, role_id=role_id)
        if not role:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
                detail_code="role.not_found",
            )

        return GetRoleResponse(
            id=role.id,
            name=role.name,
            description=role.description,
            is_default_on_registration=role.is_default_on_registration,
            created_time=role.created_time.isoformat(),
            updated_time=role.updated_time.isoformat(),
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
        Logger.error(f"Error getting role {role_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{role_id}", response_model=UpdateRoleResponse)
async def update_role_endpoint(
    role_id: str,
    request: UpdateRoleRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a global role (requires super admin access)."""
    try:
        # Get current state for change tracking
        existing_role = await get_role_by_id(session=session, role_id=role_id)
        if not existing_role:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
                detail_code="role.not_found",
            )
        old_values = {
            "name": existing_role.name,
            "description": existing_role.description,
            "is_default_on_registration": existing_role.is_default_on_registration,
        }

        updated_role = await update_role(
            session=session,
            role_id=role_id,
            request=request.model_dump(exclude_unset=True),
        )

        # Log audit event
        new_values = {
            "name": updated_role.name,
            "description": updated_role.description,
            "is_default_on_registration": updated_role.is_default_on_registration,
        }
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(updated_role.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        response = GetRoleResponse(
            id=updated_role.id,
            name=updated_role.name,
            description=updated_role.description,
            is_default_on_registration=updated_role.is_default_on_registration,
            created_time=updated_role.created_time.isoformat(),
            updated_time=updated_role.updated_time.isoformat(),
        )
        return UpdateRoleResponse(
            message="Role updated successfully",
            message_code=get_response_code("role.updated"),
            role=response,
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
        Logger.error(f"Error updating role {role_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{role_id}", response_model=DeleteRoleResponse)
async def delete_role_endpoint(
    role_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete a global role (requires super admin access)."""
    try:
        # Get role data before deletion for audit log
        existing_role = await get_role_by_id(session=session, role_id=role_id)
        if not existing_role:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
                detail_code="role.not_found",
            )
        role_data = {
            "name": existing_role.name,
            "description": existing_role.description,
            "is_default_on_registration": existing_role.is_default_on_registration,
        }

        deleted_role = await delete_role(session=session, role_id=role_id)

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Role",
            resource_id=str(deleted_role.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=role_data,
        )

        return DeleteRoleResponse(
            message="Role deleted successfully",
            message_code=get_response_code("role.deleted"),
            role_id=str(deleted_role.id),
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
        Logger.error(f"Error deleting role {role_id}: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
