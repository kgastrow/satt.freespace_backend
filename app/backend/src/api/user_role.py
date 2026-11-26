"""
User role management API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.user_role import (
    assign_role,
    get_all_user_roles_history,
    get_role_by_id,
    get_user_role_names,
    get_user_roles,
    revoke_role,
    validate_role_hierarchy,
)
from src.logger.logger import Logger as logger
from src.serialisers.user_role import (
    AssignRoleRequest,
    AssignRoleResponse,
    ListUserRolesResponse,
    RevokeRoleRequest,
    RevokeRoleResponse,
    UserRoleResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.cache import cache_service


router = APIRouter(prefix="/user-roles", tags=["user-roles"])


@router.post("/assign", response_model=AssignRoleResponse)
async def assign_role_endpoint(
    request: AssignRoleRequest,
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("user_roles:assign"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Assign a role to a user (requires user_roles:assign permission)"""
    try:
        organization_id = current_user.organization_id

        # Security: Prevent self-assignment of roles (super admins can still self-assign)
        if str(request.user_id) == str(current_user.id) and not current_user.is_admin:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot assign roles to yourself",
                detail_code="user_role.self_assignment_forbidden",
            )

        # Security: Validate role hierarchy - users can only assign roles at or below their level
        # Super admins bypass hierarchy checks
        if not current_user.is_admin:
            target_role = await get_role_by_id(session, str(request.role_id))
            if target_role:
                current_user_roles = await get_user_role_names(
                    session, str(current_user.id), organization_id
                )
                if not validate_role_hierarchy(current_user_roles, target_role.name):
                    raise create_http_exception(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot assign a role with higher privileges than your own",
                        detail_code="user_role.hierarchy_violation",
                    )

        user_role = await assign_role(
            session=session,
            request=request.model_dump(),
            assigned_by_user_id=current_user.id,
            organization_id=organization_id,
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=organization_id,
            resource_type="UserRole",
            resource_id=str(user_role.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_id": str(user_role.user_id),
                "role_id": str(user_role.role_id),
                "role_name": user_role.role.name,
            },
        )

        # Invalidate user's cached roles and JWT claims
        await cache_service.invalidate_user_roles(organization_id, str(request.user_id))

        response = UserRoleResponse(
            id=user_role.id,
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            role_name=user_role.role.name,
            assigned_by=user_role.assigned_by,
            assigned_by_email=(
                user_role.assigned_by_user.email if user_role.assigned_by_user else None
            ),
            created_time=user_role.created_time.isoformat(),
        )

        return AssignRoleResponse(
            message="Role assigned successfully",
            message_code=get_response_code("user_role.assigned"),
            user_role=response,
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
        logger.error(f"Error assigning role: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("/revoke", response_model=RevokeRoleResponse)
async def revoke_role_endpoint(
    request: RevokeRoleRequest,
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("user_roles:revoke"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Revoke a role from a user (requires user_roles:revoke permission)"""
    try:
        organization_id = current_user.organization_id

        # Security: Validate role hierarchy - users can only revoke roles at or
        # below their own privilege level. Without this an org admin could strip
        # the owner role from the organization owner.
        # Super admins bypass hierarchy checks.
        if not current_user.is_admin:
            target_role = await get_role_by_id(session, str(request.role_id))
            if target_role:
                current_user_roles = await get_user_role_names(
                    session, str(current_user.id), organization_id
                )
                if not validate_role_hierarchy(current_user_roles, target_role.name):
                    raise create_http_exception(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Cannot revoke a role with higher privileges than your own",
                        detail_code="user_role.hierarchy_violation",
                    )

        user_role = await revoke_role(
            session=session,
            request=request.model_dump(),
            organization_id=organization_id,
        )

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=organization_id,
            resource_type="UserRole",
            resource_id=str(user_role.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_id": str(user_role.user_id),
                "role_id": str(user_role.role_id),
                "role_name": user_role.role.name,
            },
        )

        # Invalidate user's cached roles and JWT claims
        await cache_service.invalidate_user_roles(organization_id, str(request.user_id))

        response = UserRoleResponse(
            id=user_role.id,
            user_id=user_role.user_id,
            role_id=user_role.role_id,
            role_name=user_role.role.name,
            assigned_by=user_role.assigned_by,
            assigned_by_email=(
                user_role.assigned_by_user.email if user_role.assigned_by_user else None
            ),
            created_time=user_role.created_time.isoformat(),
            deleted_time=(
                user_role.deleted_time.isoformat() if user_role.deleted_time else None
            ),
        )

        return RevokeRoleResponse(
            message="Role revoked successfully",
            message_code=get_response_code("user_role.removed"),
            user_role=response,
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
        logger.error(f"Error revoking role: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/users/{user_id}/roles", response_model=ListUserRolesResponse)
async def get_user_roles_endpoint(
    user_id: str,
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("user_roles:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Get active roles for a user (requires user_roles:read permission)"""
    try:
        organization_id = current_user.organization_id
        user_roles, total = await get_user_roles(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )

        role_responses = [
            UserRoleResponse(
                id=ur.id,
                user_id=ur.user_id,
                role_id=ur.role_id,
                role_name=ur.role.name,
                assigned_by=ur.assigned_by,
                assigned_by_email=(
                    ur.assigned_by_user.email if ur.assigned_by_user else None
                ),
                created_time=ur.created_time.isoformat(),
                deleted_time=ur.deleted_time.isoformat() if ur.deleted_time else None,
            )
            for ur in user_roles
        ]

        return ListUserRolesResponse(
            items=role_responses, total=total, limit=limit, offset=offset
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"Error getting user roles: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/users/{user_id}/roles/history", response_model=ListUserRolesResponse)
async def get_user_roles_history_endpoint(
    user_id: str,
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("user_roles:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Get role history for a user (requires user_roles:read permission)"""
    try:
        organization_id = current_user.organization_id
        user_roles, total = await get_all_user_roles_history(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )

        role_responses = [
            UserRoleResponse(
                id=ur.id,
                user_id=ur.user_id,
                role_id=ur.role_id,
                role_name=ur.role.name,
                assigned_by=ur.assigned_by,
                assigned_by_email=(
                    ur.assigned_by_user.email if ur.assigned_by_user else None
                ),
                created_time=ur.created_time.isoformat(),
                deleted_time=ur.deleted_time.isoformat() if ur.deleted_time else None,
            )
            for ur in user_roles
        ]

        return ListUserRolesResponse(
            items=role_responses, total=total, limit=limit, offset=offset
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        logger.error(f"Error getting user roles history: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
