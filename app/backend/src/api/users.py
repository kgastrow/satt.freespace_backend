"""
User management API endpoints for administrators.
Allows user_admin and super_admin to manage users within their organization.
"""

import traceback
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.query_params import FilterSpec
from src.core.response_codes import get_response_code
from src.crud import audit_log as audit_log_crud
from src.crud import user_notification_preference as notif_pref_crud
from src.crud.user import (
    count_super_admins,
    create_user,
    delete_user,
    get_user_by_id,
    get_user_full_detail,
    get_users_cursor,
    get_users_enhanced,
    get_users_last_login_batch,
    get_users_storage_batch,
    invalidate_user_session,
    suspend_user,
    unsuspend_user,
    update_user,
)
from src.crud.user_role import user_has_role
from src.logger.logger import Logger
from src.serialisers.user import (
    AdminCreateUserRequest,
    AdminNotificationPreferencesResponse,
    AdminPasswordResetResponse,
    AdminUpdateNotificationPreferencesRequest,
    AdminUpdateUserRequest,
    AdminUpdateUserResponse,
    CreateUserApiResponse,
    DataExportInfo,
    DeleteUserApiResponse,
    FeedbackSummaryInfo,
    FileUsageInfo,
    IdentityProviderInfo,
    ImpersonationHistoryInfo,
    InvalidateSessionResponse,
    LoginHistoryEntry,
    LoginHistoryResponse,
    NotificationPreferencesFullInfo,
    NotificationPreferencesInfo,
    SuspendUserRequest,
    SuspendUserResponse,
    SuspensionInfo,
    TwoFactorStatusInfo,
    UnsuspendUserResponse,
    UserCursorListResponse,
    UserDetailResponse,
    UserEnhancedListResponse,
    UserFullDetailResponse,
    UserListItemResponse,
    UserRoleInfo,
    UserSessionInfo,
    UserTypeOnboardingInfo,
    validate_password_complexity,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.cache import cache_service


router = APIRouter(prefix="/users", tags=["users"])


def get_avatar_url_for_user(user) -> str | None:
    """Get avatar URL for a user if they have one."""
    if user.avatar and user.avatar.storage_key:
        return f"/api/v1/files/{user.avatar.id}"
    return None


def get_active_roles_for_user(user, organization_id: str) -> list[UserRoleInfo]:
    """Extract active roles for a user within an organization."""
    from uuid import UUID

    org_uuid = UUID(organization_id)
    active_roles = []
    for user_role in user.user_roles:
        # Only include active roles (not deleted, matching org)
        if (
            user_role.deleted_time is None
            and user_role.organization_id == org_uuid
            and user_role.role is not None
            and user_role.role.deleted_time is None
        ):
            active_roles.append(
                UserRoleInfo(id=str(user_role.role.id), name=user_role.role.name)
            )
    return active_roles


@router.get("", response_model=UserEnhancedListResponse)
async def list_users_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    fields: str | None = Query(
        default=None, description="Comma-separated list of fields to include"
    ),
    filter_status: str | None = Query(default=None, alias="filter[status]"),
    filter_user_type_id: str | None = Query(default=None, alias="filter[user_type_id]"),
    filter_created_via: str | None = Query(default=None, alias="filter[created_via]"),
    filter_email_verified: bool | None = Query(
        default=None, alias="filter[email_verified]"
    ),
    sort: str | None = Query(
        default=None, description="Sort field:direction (e.g., created_time:desc)"
    ),
    q: str | None = Query(
        default=None, description="Search query for name, email, phone"
    ),
):
    """
    List users in the organization with filtering, sorting, search, and sparse fieldsets.

    Requires users:read permission.
    """
    try:
        organization_id = current_user.organization_id
        field_list = fields.split(",") if fields else None

        users, total, needs_storage, needs_user_types, needs_last_login = (
            await get_users_enhanced(
                session=session,
                organization_id=organization_id,
                limit=limit,
                offset=offset,
                fields=field_list,
                filter_status=filter_status,
                filter_user_type_id=filter_user_type_id,
                filter_created_via=filter_created_via,
                filter_email_verified=filter_email_verified,
                sort=sort,
                search=q,
            )
        )

        # Batch fetch storage and last_login data to avoid N+1 queries
        user_ids = [str(user.id) for user in users]
        storage_map: dict[str, int | None] = {}
        last_login_map: dict[str, Any] = {}

        if needs_storage and user_ids:
            storage_map = await get_users_storage_batch(
                session, user_ids, organization_id
            )

        if needs_last_login and user_ids:
            last_login_map = await get_users_last_login_batch(
                session, user_ids, organization_id
            )

        # Build response items with sparse fieldsets
        user_responses = []
        for user in users:
            item = UserListItemResponse(id=str(user.id))

            # Always include basic fields if no specific fields requested
            if field_list is None or "email" in field_list:
                item.email = user.email
            if field_list is None or "email_verified" in field_list:
                item.email_verified = user.email_verified or False
            if field_list is None or "email_deliverable" in field_list:
                item.email_deliverable = (
                    getattr(user, "email_deliverable", True) or True
                )
            if field_list is None or "phone" in field_list:
                item.phone = user.phone
            if field_list is None or "phone_verified" in field_list:
                item.phone_verified = user.phone_verified or False
            if field_list is None or "first_name" in field_list:
                item.first_name = user.first_name
            if field_list is None or "last_name" in field_list:
                item.last_name = user.last_name
            if field_list is None or "is_admin" in field_list:
                item.is_admin = user.is_admin or False
            if field_list is None or "created_time" in field_list:
                item.created_time = (
                    user.created_time.isoformat() if user.created_time else None
                )
            if field_list is None or "updated_time" in field_list:
                item.updated_time = (
                    user.updated_time.isoformat() if user.updated_time else None
                )
            if field_list is None or "suspension_status" in field_list:
                item.suspension_status = (
                    user.suspension_status.value if user.suspension_status else None
                )
            if field_list is None or "created_via" in field_list:
                item.created_via = user.created_via.value if user.created_via else None
            if field_list is None or "roles" in field_list:
                item.roles = get_active_roles_for_user(user, organization_id)
            if field_list is None or "avatar_url" in field_list:
                item.avatar_url = get_avatar_url_for_user(user)

            # User types (if needed and available)
            if needs_user_types and hasattr(user, "user_user_types"):
                item.user_types = get_user_types_for_user(user, organization_id)

            # Storage (from batch query)
            if needs_storage:
                item.total_storage_bytes = storage_map.get(str(user.id))

            # Last login (from batch query)
            if needs_last_login:
                last_login = last_login_map.get(str(user.id))
                item.last_login = last_login.isoformat() if last_login else None

            user_responses.append(item)

        return UserEnhancedListResponse(
            items=user_responses, total=total, limit=limit, offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error listing users: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/cursor", response_model=UserCursorListResponse)
async def list_users_cursor_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=10, ge=1, le=100),
    cursor: str | None = Query(
        default=None,
        description="Cursor from previous response for pagination",
    ),
    fields: str | None = Query(
        default=None, description="Comma-separated list of fields to include"
    ),
    filter_status: str | None = Query(default=None, alias="filter[status]"),
    filter_user_type_id: str | None = Query(default=None, alias="filter[user_type_id]"),
    filter_created_via: str | None = Query(default=None, alias="filter[created_via]"),
    filter_email_verified: bool | None = Query(
        default=None, alias="filter[email_verified]"
    ),
    q: str | None = Query(
        default=None, description="Search query for name, email, phone"
    ),
):
    """
    List users with cursor-based pagination for large datasets.

    Cursor pagination provides O(1) performance regardless of page depth,
    unlike offset pagination which degrades linearly (page 1000 scans 100K rows).

    Use the `next_cursor` from the response as the `cursor` parameter for the next page.

    Requires users:read permission.
    """
    try:
        organization_id = current_user.organization_id
        field_list = fields.split(",") if fields else None

        users, total, needs_storage, needs_user_types, needs_last_login, next_cursor = (
            await get_users_cursor(
                session=session,
                organization_id=organization_id,
                limit=limit,
                cursor=cursor,
                fields=field_list,
                filter_status=filter_status,
                filter_user_type_id=filter_user_type_id,
                filter_created_via=filter_created_via,
                filter_email_verified=filter_email_verified,
                search=q,
            )
        )

        # Batch fetch storage and last_login data to avoid N+1 queries
        user_ids = [str(user.id) for user in users]
        storage_map: dict[str, int | None] = {}
        last_login_map: dict[str, Any] = {}

        if needs_storage and user_ids:
            storage_map = await get_users_storage_batch(
                session, user_ids, organization_id
            )

        if needs_last_login and user_ids:
            last_login_map = await get_users_last_login_batch(
                session, user_ids, organization_id
            )

        # Build response items with sparse fieldsets
        user_responses = []
        for user in users:
            item = UserListItemResponse(id=str(user.id))

            # Always include basic fields if no specific fields requested
            if field_list is None or "email" in field_list:
                item.email = user.email
            if field_list is None or "email_verified" in field_list:
                item.email_verified = user.email_verified or False
            if field_list is None or "email_deliverable" in field_list:
                item.email_deliverable = (
                    getattr(user, "email_deliverable", True) or True
                )
            if field_list is None or "phone" in field_list:
                item.phone = user.phone
            if field_list is None or "phone_verified" in field_list:
                item.phone_verified = user.phone_verified or False
            if field_list is None or "first_name" in field_list:
                item.first_name = user.first_name
            if field_list is None or "last_name" in field_list:
                item.last_name = user.last_name
            if field_list is None or "is_admin" in field_list:
                item.is_admin = user.is_admin or False
            if field_list is None or "created_time" in field_list:
                item.created_time = (
                    user.created_time.isoformat() if user.created_time else None
                )
            if field_list is None or "updated_time" in field_list:
                item.updated_time = (
                    user.updated_time.isoformat() if user.updated_time else None
                )
            if field_list is None or "suspension_status" in field_list:
                item.suspension_status = (
                    user.suspension_status.value if user.suspension_status else None
                )
            if field_list is None or "created_via" in field_list:
                item.created_via = user.created_via.value if user.created_via else None
            if field_list is None or "roles" in field_list:
                item.roles = get_active_roles_for_user(user, organization_id)
            if field_list is None or "avatar_url" in field_list:
                item.avatar_url = get_avatar_url_for_user(user)

            # User types (if needed and available)
            if needs_user_types and hasattr(user, "user_user_types"):
                item.user_types = get_user_types_for_user(user, organization_id)

            # Storage (from batch query)
            if needs_storage:
                item.total_storage_bytes = storage_map.get(str(user.id))

            # Last login (from batch query)
            if needs_last_login:
                last_login = last_login_map.get(str(user.id))
                item.last_login = last_login.isoformat() if last_login else None

            user_responses.append(item)

        return UserCursorListResponse(
            items=user_responses,
            total=total,
            limit=limit,
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error listing users with cursor: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{user_id}", response_model=UserDetailResponse)
async def get_user_endpoint(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a user by ID (requires users:read permission)"""
    try:
        organization_id = current_user.organization_id
        user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )

        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        return UserDetailResponse(
            id=str(user.id),
            email=user.email,
            email_verified=user.email_verified or False,
            email_deliverable=getattr(user, "email_deliverable", True) or True,
            phone=user.phone,
            phone_verified=user.phone_verified or False,
            first_name=user.first_name,
            last_name=user.last_name,
            is_admin=user.is_admin or False,
            created_time=user.created_time.isoformat() if user.created_time else "",
            updated_time=user.updated_time.isoformat() if user.updated_time else None,
            suspension_status=(
                user.suspension_status.value if user.suspension_status else None
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting user {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("", response_model=CreateUserApiResponse)
async def create_user_endpoint(
    request: AdminCreateUserRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new user in the organization (requires users:write permission)"""
    try:
        organization_id = current_user.organization_id

        # Only super admins can set is_admin flag
        is_admin_value = False
        if request.is_admin:
            if not current_user.is_admin:
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admins can grant super admin privileges",
                    detail_code="common.forbidden",
                )
            is_admin_value = True

        # Validate password complexity
        validate_password_complexity(request.password)

        user_data = {
            "email": request.email,
            "password": request.password,
            "phone": str(request.phone) if request.phone else None,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "is_admin": is_admin_value,
            "email_verified": False,
        }

        new_user = await create_user(
            session=session, request=user_data, organization_id=organization_id
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(new_user.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "email": new_user.email,
                "first_name": new_user.first_name,
                "last_name": new_user.last_name,
                "is_admin": new_user.is_admin,
            },
        )

        response = UserDetailResponse(
            id=str(new_user.id),
            email=new_user.email,
            email_verified=new_user.email_verified or False,
            email_deliverable=getattr(new_user, "email_deliverable", True) or True,
            phone=new_user.phone,
            phone_verified=new_user.phone_verified or False,
            first_name=new_user.first_name,
            last_name=new_user.last_name,
            is_admin=new_user.is_admin or False,
            created_time=(
                new_user.created_time.isoformat() if new_user.created_time else ""
            ),
            updated_time=(
                new_user.updated_time.isoformat() if new_user.updated_time else None
            ),
            suspension_status=(
                new_user.suspension_status.value if new_user.suspension_status else None
            ),
        )

        return CreateUserApiResponse(
            message="User created successfully",
            message_code=get_response_code("user.created"),
            user=response,
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
        Logger.error(f"Error creating user: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{user_id}", response_model=AdminUpdateUserResponse)
async def update_user_endpoint(
    user_id: str,
    request: AdminUpdateUserRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a user (requires users:write permission)"""
    try:
        organization_id = current_user.organization_id

        # Get current state for change tracking
        existing_user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not existing_user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )
        old_values = {
            "email": existing_user.email,
            "phone": existing_user.phone,
            "first_name": existing_user.first_name,
            "last_name": existing_user.last_name,
            "is_admin": existing_user.is_admin,
        }

        # Validate password complexity if password is being updated
        if request.password:
            validate_password_complexity(request.password)

        update_data: dict[str, Any] = {"id": user_id}
        if request.email is not None:
            update_data["email"] = request.email
        if request.password is not None:
            update_data["password"] = request.password
        if request.phone is not None:
            update_data["phone"] = str(request.phone)
        if request.first_name is not None:
            update_data["first_name"] = request.first_name
        if request.last_name is not None:
            update_data["last_name"] = request.last_name
        if request.is_admin is not None:
            # Only super admins can modify is_admin flag
            if not current_user.is_admin:
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only super admins can modify super admin privileges",
                    detail_code="common.forbidden",
                )
            # Prevent removing the last super admin
            if request.is_admin is False and existing_user.is_admin:
                other_admins = await count_super_admins(
                    session, organization_id, exclude_user_id=user_id
                )
                if other_admins == 0:
                    raise create_http_exception(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cannot remove the last super admin. Promote another user first.",
                        detail_code="user.last_super_admin",
                    )
            update_data["is_admin"] = request.is_admin

        updated_user = await update_user(
            session=session, request=update_data, organization_id=organization_id
        )

        # Invalidate cached JWT claims if is_admin or security-critical fields changed
        if request.is_admin is not None and request.is_admin != existing_user.is_admin:
            await cache_service.invalidate_jwt_for_user(str(user_id))
            await cache_service.invalidate_user_roles(organization_id, str(user_id))

        # Log audit event
        new_values = {
            "email": updated_user.email,
            "phone": updated_user.phone,
            "first_name": updated_user.first_name,
            "last_name": updated_user.last_name,
            "is_admin": updated_user.is_admin,
        }
        # Add password change indicator if password was updated
        if request.password is not None:
            old_values["password"] = "[PREVIOUS]"
            new_values["password"] = "[CHANGED]"

        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(updated_user.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        response = UserDetailResponse(
            id=str(updated_user.id),
            email=updated_user.email,
            email_verified=updated_user.email_verified or False,
            email_deliverable=getattr(updated_user, "email_deliverable", True) or True,
            phone=updated_user.phone,
            phone_verified=updated_user.phone_verified or False,
            first_name=updated_user.first_name,
            last_name=updated_user.last_name,
            is_admin=updated_user.is_admin or False,
            created_time=(
                updated_user.created_time.isoformat()
                if updated_user.created_time
                else ""
            ),
            updated_time=(
                updated_user.updated_time.isoformat()
                if updated_user.updated_time
                else None
            ),
            suspension_status=(
                updated_user.suspension_status.value
                if updated_user.suspension_status
                else None
            ),
        )

        return AdminUpdateUserResponse(
            message="User updated successfully",
            message_code=get_response_code("user.updated"),
            user=response,
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
        Logger.error(f"Error updating user {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{user_id}", response_model=DeleteUserApiResponse)
async def delete_user_endpoint(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:delete"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete a user (soft delete, requires users:delete permission)"""
    try:
        organization_id = current_user.organization_id

        # Prevent users from deleting themselves
        if user_id == current_user.id:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete yourself",
                detail_code="common.bad_request",
            )

        # Prevent deleting organization owners - they can only be removed when the organization is deleted
        is_owner = await user_has_role(session, user_id, "owner", organization_id)
        if is_owner:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete organization owner. The owner can only be removed by deleting the organization.",
                detail_code="common.forbidden",
            )

        # Get user data before deletion for audit log
        existing_user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not existing_user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )
        user_data = {
            "email": existing_user.email,
            "first_name": existing_user.first_name,
            "last_name": existing_user.last_name,
        }

        deleted_user = await delete_user(
            session=session, user_id=user_id, organization_id=organization_id
        )

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(deleted_user.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=user_data,
        )

        return DeleteUserApiResponse(
            message="User deleted successfully",
            message_code=get_response_code("user.deleted"),
            user_id=str(deleted_user.id),
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
        Logger.error(f"Error deleting user {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("/{user_id}/suspend", response_model=SuspendUserResponse)
async def suspend_user_endpoint(
    user_id: str,
    request: SuspendUserRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:suspend"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Suspend a user (requires users:suspend permission)"""
    try:
        organization_id = current_user.organization_id

        # Prevent users from suspending themselves
        if user_id == current_user.id:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot suspend yourself",
                detail_code="user.cannot_suspend_self",
            )

        # Prevent suspending organization owners
        is_owner = await user_has_role(session, user_id, "owner", organization_id)
        if is_owner:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot suspend organization owner",
                detail_code="user.cannot_suspend_owner",
            )

        # Get user data before suspension for audit log
        existing_user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not existing_user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        old_values = {
            "suspension_status": existing_user.suspension_status.value,
            "suspended_time": (
                existing_user.suspended_time.isoformat()
                if existing_user.suspended_time
                else None
            ),
            "suspended_by": (
                str(existing_user.suspended_by) if existing_user.suspended_by else None
            ),
            "suspension_reason": existing_user.suspension_reason,
        }

        suspended_user = await suspend_user(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            suspended_by=current_user.id,
            reason=request.reason,
        )

        # Invalidate suspended user's cached JWT claims
        await cache_service.invalidate_jwt_for_user(str(user_id))

        # Send notification if requested
        if request.send_notification:
            from src.services.notifications.dispatcher import notification_dispatcher

            # Prepare notification content
            suspension_message = "Your account has been suspended."
            if request.reason:
                suspension_message += f" Reason: {request.reason}"

            try:
                await notification_dispatcher.send_to_user(
                    session=session,
                    user_id=user_id,
                    organization_id=organization_id,
                    channel="email",
                    content=suspension_message,
                    subject="Account Suspended",
                    category_code="account",
                    is_urgent=True,
                )
            except Exception as e:
                Logger.error(f"Failed to send suspension notification: {str(e)}")
                # Continue even if notification fails

        new_values = {
            "suspension_status": suspended_user.suspension_status.value,
            "suspended_time": (
                suspended_user.suspended_time.isoformat()
                if suspended_user.suspended_time
                else None
            ),
            "suspended_by": (
                str(suspended_user.suspended_by)
                if suspended_user.suspended_by
                else None
            ),
            "suspension_reason": suspended_user.suspension_reason,
        }

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(suspended_user.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return SuspendUserResponse(
            message="User suspended successfully",
            message_code=get_response_code("user.suspended"),
            user_id=str(suspended_user.id),
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
        Logger.error(f"Error suspending user {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("/{user_id}/unsuspend", response_model=UnsuspendUserResponse)
async def unsuspend_user_endpoint(
    user_id: str,
    http_request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("users:unsuspend"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Unsuspend a user (requires users:unsuspend permission)"""
    try:
        organization_id = current_user.organization_id

        # Get user data before unsuspension for audit log
        existing_user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not existing_user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        old_values = {
            "suspension_status": existing_user.suspension_status.value,
            "suspended_time": (
                existing_user.suspended_time.isoformat()
                if existing_user.suspended_time
                else None
            ),
            "suspended_by": (
                str(existing_user.suspended_by) if existing_user.suspended_by else None
            ),
            "suspension_reason": existing_user.suspension_reason,
        }

        unsuspended_user = await unsuspend_user(
            session=session, user_id=user_id, organization_id=organization_id
        )

        new_values = {
            "suspension_status": unsuspended_user.suspension_status.value,
            "suspended_time": None,
            "suspended_by": None,
            "suspension_reason": None,
        }

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="User",
            resource_id=str(unsuspended_user.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UnsuspendUserResponse(
            message="User unsuspended successfully",
            message_code=get_response_code("user.unsuspended"),
            user_id=str(unsuspended_user.id),
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
        Logger.error(f"Error unsuspending user {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# Enhanced user management endpoints


def get_user_types_for_user(user, organization_id: str) -> list[UserTypeOnboardingInfo]:
    """Extract user types with onboarding status for a user."""
    from uuid import UUID

    org_uuid = UUID(organization_id)
    user_types = []
    for uut in user.user_user_types:
        if uut.deleted_time is None and uut.organization_id == org_uuid:
            user_types.append(
                UserTypeOnboardingInfo(
                    id=str(uut.user_type_id),
                    name=uut.user_type.name if uut.user_type else "Unknown",
                    code=uut.user_type.code if uut.user_type else "unknown",
                    onboarding_status=uut.onboarding_status.value,
                    onboarded_at=(
                        uut.onboarded_at.isoformat() if uut.onboarded_at else None
                    ),
                )
            )
    return user_types


@router.get("/{user_id}/detail", response_model=UserFullDetailResponse)
async def get_user_detail_endpoint(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get complete user details including all related data.

    Returns comprehensive user information including sessions, security settings,
    file usage, activity history, etc.

    Requires users:read permission.
    """
    try:
        organization_id = current_user.organization_id

        # Get the current session ID from the request (for marking current session)
        current_session_id = getattr(http_request.state, "session_id", None)

        data = await get_user_full_detail(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            current_session_id=current_session_id,
        )

        if not data:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        user = data["user"]

        # Build sessions list
        sessions_list = []
        for sess in data["sessions"]:
            sessions_list.append(
                UserSessionInfo(
                    id=str(sess.id),
                    created_time=(
                        sess.created_time.isoformat() if sess.created_time else ""
                    ),
                    updated_time=(
                        sess.updated_time.isoformat() if sess.updated_time else None
                    ),
                    expires_at=sess.expires_at.isoformat() if sess.expires_at else "",
                    auth_provider=sess.auth_provider,
                    ip_address=sess.ip_address,
                    user_agent=sess.user_agent,
                    city=sess.city,
                    country=sess.country,
                    country_code=sess.country_code,
                    is_current=str(sess.id) == data["current_session_id"],
                )
            )

        # Build two-factor status
        two_factor = data["two_factor"]
        backup_codes_remaining = 0
        if two_factor and two_factor.backup_codes:
            backup_codes_remaining = sum(
                1
                for code in two_factor.backup_codes
                if code.deleted_time is None and not code.used_at
            )

        two_factor_info = TwoFactorStatusInfo(
            is_enabled=two_factor.is_enabled if two_factor else False,
            verified_at=(
                two_factor.verified_at.isoformat()
                if two_factor and two_factor.verified_at
                else None
            ),
            backup_codes_remaining=backup_codes_remaining,
        )

        # Build file usage
        file_usage = data["file_usage"]
        file_usage_info = None
        if file_usage:
            file_usage_info = FileUsageInfo(
                total_files=file_usage.total_files,
                total_size_bytes=file_usage.total_size_bytes,
                image_count=file_usage.image_count,
                image_size_bytes=file_usage.image_size_bytes,
                video_count=file_usage.video_count,
                video_size_bytes=file_usage.video_size_bytes,
                document_count=file_usage.document_count,
                document_size_bytes=file_usage.document_size_bytes,
                audio_count=file_usage.audio_count,
                audio_size_bytes=file_usage.audio_size_bytes,
                other_count=file_usage.other_count,
                other_size_bytes=file_usage.other_size_bytes,
            )

        # Build feedback summary
        feedback_list = []
        for fb in data["feedback"]:
            feedback_list.append(
                FeedbackSummaryInfo(
                    id=str(fb.id),
                    type=fb.type,
                    subject=fb.subject,
                    status=fb.status,
                    created_time=fb.created_time.isoformat() if fb.created_time else "",
                )
            )

        # Build identity providers
        identity_list = []
        for identity in data["identities"]:
            identity_list.append(
                IdentityProviderInfo(
                    id=str(identity.id),
                    provider=identity.provider,
                    provider_email=identity.provider_email,
                    created_time=(
                        identity.created_time.isoformat()
                        if identity.created_time
                        else ""
                    ),
                )
            )

        # Build data exports
        exports_list = []
        for export in data["data_exports"]:
            exports_list.append(
                DataExportInfo(
                    id=str(export.id),
                    status=export.status.value if export.status else "unknown",
                    created_time=(
                        export.created_time.isoformat() if export.created_time else ""
                    ),
                    completed_at=(
                        export.completed_at.isoformat() if export.completed_at else None
                    ),
                    file_size_bytes=export.file_size_bytes,
                    download_count=export.download_count,
                    expires_at=(
                        export.expires_at.isoformat() if export.expires_at else None
                    ),
                )
            )

        # Build impersonation history
        impersonation_list = []
        for imp in data["impersonation_history"]:
            impersonator_name = None
            if imp.impersonator:
                impersonator_name = (
                    " ".join(
                        filter(
                            None,
                            [imp.impersonator.first_name, imp.impersonator.last_name],
                        )
                    )
                    or imp.impersonator.email
                )
            impersonation_list.append(
                ImpersonationHistoryInfo(
                    id=str(imp.id),
                    impersonator_id=str(imp.impersonator_id),
                    impersonator_name=impersonator_name,
                    created_time=(
                        imp.created_time.isoformat() if imp.created_time else ""
                    ),
                    ended_time=imp.ended_time.isoformat() if imp.ended_time else None,
                )
            )

        # Build notification preferences
        notif_prefs = data["notification_preferences"]
        notif_prefs_info = None
        if notif_prefs:
            notif_prefs_info = NotificationPreferencesInfo(
                email_enabled=(
                    notif_prefs.email_enabled
                    if hasattr(notif_prefs, "email_enabled")
                    else True
                ),
                sms_enabled=(
                    notif_prefs.sms_enabled
                    if hasattr(notif_prefs, "sms_enabled")
                    else False
                ),
                push_enabled=(
                    notif_prefs.push_enabled
                    if hasattr(notif_prefs, "push_enabled")
                    else False
                ),
                in_app_enabled=(
                    notif_prefs.in_app_enabled
                    if hasattr(notif_prefs, "in_app_enabled")
                    else True
                ),
            )

        # Build suspension info
        suspension_info = None
        if user.suspension_status and user.suspension_status.value == "suspended":
            suspended_by_name = None
            if user.suspended_by_user:
                suspended_by_name = (
                    " ".join(
                        filter(
                            None,
                            [
                                user.suspended_by_user.first_name,
                                user.suspended_by_user.last_name,
                            ],
                        )
                    )
                    or user.suspended_by_user.email
                )
            suspension_info = SuspensionInfo(
                suspended_time=(
                    user.suspended_time.isoformat() if user.suspended_time else None
                ),
                suspended_by=str(user.suspended_by) if user.suspended_by else None,
                suspended_by_name=suspended_by_name,
                suspension_reason=user.suspension_reason,
            )

        return UserFullDetailResponse(
            id=str(user.id),
            email=user.email,
            email_verified=user.email_verified or False,
            email_deliverable=getattr(user, "email_deliverable", True) or True,
            phone=user.phone,
            phone_verified=user.phone_verified or False,
            first_name=user.first_name,
            last_name=user.last_name,
            is_admin=user.is_admin or False,
            created_time=user.created_time.isoformat() if user.created_time else "",
            updated_time=user.updated_time.isoformat() if user.updated_time else None,
            created_via=user.created_via.value if user.created_via else "email",
            avatar_url=get_avatar_url_for_user(user),
            suspension_status=(
                user.suspension_status.value if user.suspension_status else "active"
            ),
            suspension_info=suspension_info,
            roles=get_active_roles_for_user(user, organization_id),
            user_types=get_user_types_for_user(user, organization_id),
            sessions=sessions_list,
            two_factor=two_factor_info,
            identity_providers=identity_list,
            file_usage=file_usage_info,
            feedback=feedback_list,
            data_exports=exports_list,
            impersonation_history=impersonation_list,
            notification_preferences=notif_prefs_info,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting user detail {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete(
    "/{user_id}/sessions/{session_id}", response_model=InvalidateSessionResponse
)
async def invalidate_user_session_endpoint(
    user_id: str,
    session_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Invalidate a specific user session.

    This allows admins to forcibly log out a user from a specific device/session.

    Requires users:write permission.
    """
    try:
        organization_id = current_user.organization_id

        # Verify the user exists
        user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Invalidate the session
        success = await invalidate_user_session(
            session=session,
            session_id=session_id,
            user_id=user_id,
            organization_id=organization_id,
        )

        if not success:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
                detail_code="session.not_found",
            )

        # Log audit event
        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="UserSession",
            resource_id=session_id,
            old_values={"status": "active"},
            new_values={"status": "invalidated"},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return InvalidateSessionResponse(
            message="Session invalidated successfully",
            message_code=get_response_code("session.invalidated"),
            session_id=session_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error invalidating session {session_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Login History Endpoint
# =============================================================================


@router.get("/{user_id}/login-history", response_model=LoginHistoryResponse)
async def get_user_login_history(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    Get login history for a user from audit logs and sessions.

    Returns a paginated list of login attempts for the user,
    including successful logins and failed attempts.

    Requires users:read permission.
    """
    try:
        organization_id = current_user.organization_id

        # Verify user exists
        user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Query audit logs for login-related events
        # We filter for Session CREATE events where the resource_id relates to sessions
        filters = [
            FilterSpec(field="resource_type", operator="eq", value="Session"),
            FilterSpec(field="action", operator="eq", value="CREATE"),
            FilterSpec(field="actor_id", operator="eq", value=user_id),
        ]

        audit_logs, total = await audit_log_crud.get_audit_logs(
            session=session,
            organization_id=organization_id,
            filters=filters,
            limit=limit,
            offset=offset,
        )

        # Build login history from audit logs
        login_entries = []
        for log in audit_logs:
            context = log.resource_context or {}
            entry = LoginHistoryEntry(
                id=str(log.id),
                created_time=log.created_time.isoformat() if log.created_time else "",
                success=True,  # CREATE Session = successful login
                auth_method=context.get("auth_provider"),
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                city=context.get("city"),
                country=context.get("country"),
                country_code=context.get("country_code"),
                failure_reason=None,
            )
            login_entries.append(entry)

        return LoginHistoryResponse(
            items=login_entries,
            total=total,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting login history for {user_id}: {str(e)}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Admin Notification Preferences Endpoints
# =============================================================================


@router.get(
    "/{user_id}/notification-preferences",
    response_model=AdminNotificationPreferencesResponse,
)
async def get_user_notification_preferences(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a user's notification preferences.

    Returns the user's actual notification preferences including all channels.

    Requires users:read permission.
    """
    try:
        organization_id = current_user.organization_id

        # Verify user exists
        user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Get or create notification preferences
        prefs = await notif_pref_crud.get_or_create_user_preference(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
        )

        prefs_info = NotificationPreferencesFullInfo(
            email_enabled=prefs.email_enabled,
            sms_enabled=prefs.sms_enabled,
            whatsapp_enabled=prefs.whatsapp_enabled,
            in_app_enabled=prefs.in_app_enabled,
            quiet_hours_enabled=prefs.quiet_hours_enabled,
            quiet_hours_start=(
                prefs.quiet_hours_start.isoformat() if prefs.quiet_hours_start else None
            ),
            quiet_hours_end=(
                prefs.quiet_hours_end.isoformat() if prefs.quiet_hours_end else None
            ),
            quiet_hours_timezone=prefs.quiet_hours_timezone,
        )

        return AdminNotificationPreferencesResponse(
            message="Notification preferences retrieved successfully",
            message_code="notification_preferences.retrieved",
            user_id=user_id,
            preferences=prefs_info,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error getting notification preferences for {user_id}: {str(e)}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put(
    "/{user_id}/notification-preferences",
    response_model=AdminNotificationPreferencesResponse,
)
async def update_user_notification_preferences(
    user_id: str,
    request: AdminUpdateNotificationPreferencesRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a user's notification preferences (super admin only).

    Allows admins to update a user's notification preferences on their behalf.

    Requires super admin access.
    """
    try:
        organization_id = str(current_user.organization_id)

        # Verify user exists
        user = await get_user_by_id(
            session=session, user_id=user_id, organization_id=organization_id
        )
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Get current preferences for audit
        old_prefs = await notif_pref_crud.get_user_preference(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
        )

        old_values = {}
        if old_prefs:
            old_values = {
                "email_enabled": old_prefs.email_enabled,
                "sms_enabled": old_prefs.sms_enabled,
                "whatsapp_enabled": old_prefs.whatsapp_enabled,
                "in_app_enabled": old_prefs.in_app_enabled,
            }

        # Update preferences
        update_data = request.model_dump(exclude_unset=True)
        prefs = await notif_pref_crud.update_user_preference(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            preference_data=update_data,
        )

        # Log audit event
        new_values = {
            "email_enabled": prefs.email_enabled,
            "sms_enabled": prefs.sms_enabled,
            "whatsapp_enabled": prefs.whatsapp_enabled,
            "in_app_enabled": prefs.in_app_enabled,
        }

        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserNotificationPreference",
            resource_id=str(prefs.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            # `log_update` takes no `resource_name`; passing one raised
            # TypeError and turned every preference update into a 500.
            resource_context={"resource_name": f"Notification preferences for {user.email}"},
        )

        prefs_info = NotificationPreferencesFullInfo(
            email_enabled=prefs.email_enabled,
            sms_enabled=prefs.sms_enabled,
            whatsapp_enabled=prefs.whatsapp_enabled,
            in_app_enabled=prefs.in_app_enabled,
            quiet_hours_enabled=prefs.quiet_hours_enabled,
            quiet_hours_start=(
                prefs.quiet_hours_start.isoformat() if prefs.quiet_hours_start else None
            ),
            quiet_hours_end=(
                prefs.quiet_hours_end.isoformat() if prefs.quiet_hours_end else None
            ),
            quiet_hours_timezone=prefs.quiet_hours_timezone,
        )

        return AdminNotificationPreferencesResponse(
            message="Notification preferences updated successfully",
            message_code="notification_preferences.updated",
            user_id=user_id,
            preferences=prefs_info,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error updating notification preferences for {user_id}: {str(e)}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Admin Password Reset
# =============================================================================


@router.post("/{user_id}/password-reset", response_model=AdminPasswordResetResponse)
async def admin_send_password_reset(
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Send a password reset email to a user (admin only).

    This allows admins to trigger a password reset for users who need
    to reset their password but may not have access to the reset flow.
    Only available for users with email/password login.
    """
    from src.core.config import settings
    from src.crud.organization import get_organization_by_id
    from src.crud.user_otp import create_password_reset_token
    from src.services.tasks import task_queue

    organization_id = str(current_user.organization_id)

    try:
        # Get target user
        user = await get_user_by_id(session, user_id, organization_id)
        if not user:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                detail_code="user.not_found",
            )

        # Check if user has email/password login (created via email)
        if user.created_via and user.created_via.lower() != "email":
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User does not have email/password login. They should use their identity provider to sign in.",
                detail_code="user.no_password_login",
            )

        # Generate password reset token
        reset_token = await create_password_reset_token(
            session=session,
            user_id=user.id,
            organization_id=organization_id,
        )

        # Build reset URL.
        # SPA route (app/frontend/src/router.tsx), so the FRONTEND origin.
        #
        # The org slug is read from the database: CurrentUser carries only
        # organization_id and org_name, so the previous `current_user.organization.slug`
        # raised AttributeError and turned every call to this endpoint into a 500.
        organization = await get_organization_by_id(session, organization_id)
        org_slug = organization.slug if organization else ""
        reset_url = (
            f"{settings.PUBLIC_URL_FRONTEND}/reset-password"
            f"?token={reset_token}&org={org_slug}"
        )

        # Queue password reset email
        await task_queue.enqueue_password_reset_email(
            to=user.email,
            reset_token=reset_token,
            reset_url=reset_url,
            organization_id=organization_id,
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="PasswordResetRequest",
            resource_id=str(user.id),
            # log_create takes resource_data, not values/resource_name; the old
            # kwargs raised TypeError and made this endpoint 500 unconditionally.
            resource_data={
                "triggered_by_admin": True,
                "user_email": user.email,
            },
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        Logger.info(f"Admin {current_user.email} sent password reset to {user.email}")

        return AdminPasswordResetResponse(
            message="Password reset email has been sent to the user",
            message_code="user.password_reset_sent",
            user_id=user_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error sending password reset for {user_id}: {str(e)}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
