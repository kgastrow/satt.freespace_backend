"""
API key management endpoints.
Allows users with appropriate permissions to create, view, update, and revoke API keys.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_session,
    require_feature_flag,
    require_permission,
)
from src.core.datetime_utils import serialize_datetime, serialize_datetime_required
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.api_key import (
    assign_permissions,
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_key_permissions,
    get_api_keys_by_organization,
    update_api_key,
)
from src.crud.role_permission import get_user_permissions
from src.logger.logger import Logger
from src.models.api_key import ApiKeyScope
from src.models.audit_log import AuditAction
from src.serialisers.api_key import (
    ApiKeyDetailResponse,
    ApiKeyListResponse,
    AssignablePermissionsResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    DeleteApiKeyResponse,
    UpdateApiKeyRequest,
    UpdateApiKeyResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("/assignable-permissions", response_model=AssignablePermissionsResponse)
async def get_assignable_permissions_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get all permissions that the current user can assign to API keys.

    Super admins can assign any permission.
    Regular users can only assign permissions they have.
    """
    try:
        # Super admins can assign any permission
        if current_user.is_admin:
            from src.models.permission import Permission

            result = await session.execute(
                select(Permission)
                .where(Permission.deleted_time.is_(None))
                .order_by(Permission.display_order, Permission.code)
            )
            all_permissions = result.scalars().all()
            from src.serialisers.permission import PermissionResponse

            permission_responses = [
                PermissionResponse(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    description=p.description,
                    resource=p.resource,
                    action=p.action,
                    display_order=p.display_order,
                    created_time=serialize_datetime_required(p.created_time),
                )
                for p in all_permissions
            ]
        else:
            # Regular users can only assign permissions they have
            permission_codes = await get_user_permissions(
                session, current_user.id, current_user.organization_id
            )
            # Fetch full permission objects for the user's permission codes
            from src.models.permission import Permission

            result = await session.execute(
                select(Permission)
                .where(
                    Permission.code.in_(permission_codes),
                    Permission.deleted_time.is_(None),
                )
                .order_by(Permission.display_order, Permission.code)
            )
            user_permissions = result.scalars().all()
            from src.serialisers.permission import PermissionResponse

            permission_responses = [
                PermissionResponse(
                    id=p.id,
                    code=p.code,
                    name=p.name,
                    description=p.description,
                    resource=p.resource,
                    action=p.action,
                    display_order=p.display_order,
                    created_time=serialize_datetime_required(p.created_time),
                )
                for p in user_permissions
            ]

        return AssignablePermissionsResponse(permissions=permission_responses)

    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to get assignable permissions: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post(
    "", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED
)
async def create_api_key_endpoint(
    request_body: CreateApiKeyRequest,
    http_request: Request,
    _feature_flag: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    current_user: Annotated[CurrentUser, Depends(require_permission("api_keys:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new API key (requires api_keys:write permission and api_keys feature flag).

    The full API key is returned ONLY in this response and cannot be retrieved later.
    Store it securely.

    Permissions assigned to the API key cannot exceed those of the creating user.
    """
    try:
        organization_id = current_user.organization_id

        # Validate that at least one permission is provided
        if not request_body.permissions or len(request_body.permissions) == 0:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one permission must be assigned to an API key",
                detail_code="api_key.no_permissions",
            )

        # Validate requested permissions don't exceed user's permissions
        if request_body.permissions:
            # Super admins can assign any permission
            if not current_user.is_admin:
                user_permissions = await get_user_permissions(
                    session, current_user.id, organization_id
                )
                invalid_permissions = [
                    p for p in request_body.permissions if p not in user_permissions
                ]
                if invalid_permissions:
                    raise create_http_exception(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Cannot assign permissions you don't have: {', '.join(invalid_permissions)}",
                        detail_code="api_key.permission_denied",
                    )

        # Create the API key with user scope (created through user endpoint)
        api_key, full_key = await create_api_key(
            session=session,
            name=request_body.name,
            organization_id=organization_id,
            created_by=current_user.id,
            expires_at=request_body.expires_at,
            scope=ApiKeyScope.USER,
        )

        # Assign permissions if provided
        if request_body.permissions:
            await assign_permissions(
                session=session,
                api_key_id=str(api_key.id),
                organization_id=organization_id,
                permissions=request_body.permissions,
            )

        # Audit log
        await audit_service.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.CREATE,
            resource_type="api_key",
            resource_id=str(api_key.id),
            actor_id=current_user.id,
            changes={
                "name": api_key.name,
                "prefix": api_key.prefix,
                "permissions": request_body.permissions,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return CreateApiKeyResponse(
            id=str(api_key.id),
            name=api_key.name,
            key=full_key,
            prefix=api_key.prefix,
            scope=api_key.scope,
            expires_at=serialize_datetime(api_key.expires_at),
            permissions=request_body.permissions,
            created_time=serialize_datetime_required(api_key.created_time),
            message="API key created successfully. Store this key securely - it cannot be retrieved later.",
            message_code=get_response_code("api_key.created"),
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
        Logger.error(f"Failed to create API key: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("", response_model=ApiKeyListResponse)
async def list_api_keys_endpoint(
    http_request: Request,
    _feature_flag: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    current_user: Annotated[CurrentUser, Depends(require_permission("api_keys:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all API keys in the organization (requires api_keys:read permission and api_keys feature flag)"""
    try:
        organization_id = current_user.organization_id
        api_keys, total = await get_api_keys_by_organization(
            session=session,
            organization_id=organization_id,
            limit=limit,
            offset=offset,
        )

        # Build response with permissions for each key
        api_key_responses = []
        for api_key in api_keys:
            permissions = await get_api_key_permissions(
                session, str(api_key.id), organization_id
            )

            api_key_responses.append(
                ApiKeyDetailResponse(
                    id=str(api_key.id),
                    name=api_key.name,
                    prefix=api_key.prefix,
                    scope=api_key.scope,
                    expires_at=serialize_datetime(api_key.expires_at),
                    last_used_at=serialize_datetime(api_key.last_used_at),
                    created_by=str(api_key.created_by),
                    created_time=serialize_datetime_required(api_key.created_time),
                    updated_time=serialize_datetime(api_key.updated_time),
                    permissions=permissions,
                )
            )

        return ApiKeyListResponse(
            items=api_key_responses, total=total, limit=limit, offset=offset
        )

    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to list API keys: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{api_key_id}", response_model=ApiKeyDetailResponse)
async def get_api_key_endpoint(
    api_key_id: str,
    http_request: Request,
    _feature_flag: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    current_user: Annotated[CurrentUser, Depends(require_permission("api_keys:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get API key details by ID (requires api_keys:read permission and api_keys feature flag)"""
    try:
        organization_id = current_user.organization_id
        api_key = await get_api_key_by_id(
            session=session,
            api_key_id=api_key_id,
            organization_id=organization_id,
        )

        if not api_key:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
                detail_code="common.not_found",
            )

        # Get permissions for this key
        permissions = await get_api_key_permissions(
            session, str(api_key.id), organization_id
        )

        return ApiKeyDetailResponse(
            id=str(api_key.id),
            name=api_key.name,
            prefix=api_key.prefix,
            scope=api_key.scope,
            expires_at=serialize_datetime(api_key.expires_at),
            last_used_at=serialize_datetime(api_key.last_used_at),
            created_by=str(api_key.created_by),
            created_time=serialize_datetime_required(api_key.created_time),
            updated_time=serialize_datetime(api_key.updated_time),
            permissions=permissions,
        )

    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to get API key: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.patch("/{api_key_id}", response_model=UpdateApiKeyResponse)
async def update_api_key_endpoint(
    api_key_id: str,
    request_body: UpdateApiKeyRequest,
    http_request: Request,
    _feature_flag: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    current_user: Annotated[CurrentUser, Depends(require_permission("api_keys:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update API key name (requires api_keys:write permission and api_keys feature flag). Expiration cannot be modified after creation."""
    try:
        organization_id = current_user.organization_id

        # Get the API key before update for audit logging
        api_key = await get_api_key_by_id(session, api_key_id, organization_id)
        if not api_key:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
                detail_code="api_key.not_found",
            )

        # Update the API key (name only - expiration cannot be modified)
        updated_key = await update_api_key(
            session=session,
            api_key_id=api_key_id,
            organization_id=organization_id,
            name=request_body.name,
        )

        # Audit log
        await audit_service.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.UPDATE,
            resource_type="api_key",
            resource_id=api_key_id,
            actor_id=current_user.id,
            changes={
                "name": updated_key.name,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UpdateApiKeyResponse(
            id=str(updated_key.id),
            name=updated_key.name,
            prefix=updated_key.prefix,
            updated_time=serialize_datetime(updated_key.updated_time),
            message="API key updated successfully",
            message_code=get_response_code("api_key.updated"),
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
        Logger.error(f"Failed to update API key: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{api_key_id}", response_model=DeleteApiKeyResponse)
async def delete_api_key_endpoint(
    api_key_id: str,
    http_request: Request,
    _feature_flag: Annotated[CurrentUser, Depends(require_feature_flag("api_keys"))],
    current_user: Annotated[
        CurrentUser, Depends(require_permission("api_keys:delete"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Revoke (soft delete) an API key (requires api_keys:delete permission and api_keys feature flag)"""
    try:
        organization_id = current_user.organization_id

        # Get the API key before deletion for audit logging
        api_key = await get_api_key_by_id(session, api_key_id, organization_id)
        if not api_key:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found",
                detail_code="api_key.not_found",
            )

        # Delete (revoke) the API key
        await delete_api_key(
            session=session,
            api_key_id=api_key_id,
            organization_id=organization_id,
        )

        # Audit log
        await audit_service.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.DELETE,
            resource_type="api_key",
            resource_id=api_key_id,
            actor_id=current_user.id,
            changes={"name": api_key.name, "prefix": api_key.prefix},
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return DeleteApiKeyResponse(
            message="API key revoked successfully",
            message_code=get_response_code("api_key.deleted"),
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
        Logger.error(f"Failed to delete API key: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# NOTE: Permissions are read-only after API key creation
# POST /{api_key_id}/permissions and DELETE /{api_key_id}/permissions
# endpoints have been removed to enforce this constraint
