"""
Admin API endpoints for system configuration.
Super admin only endpoints for managing system config, notification providers,
system templates, system categories, file settings, and permissions.
"""

import traceback
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.exceptions import create_http_exception
from src.core.rate_limit import limiter
from src.core.response_codes import get_response_code
from src.crud.file_settings import (
    get_all_file_settings as get_all_organization_file_settings,
)
from src.crud.maintenance import (
    get_maintenance_config,
    update_maintenance_config,
)
from src.crud.notification_category import (
    create_system_category,
    get_system_categories,
)
from src.crud.notification_provider import (
    create_notification_provider,
    deactivate_notification_provider,
    get_notification_providers,
    update_notification_provider,
)
from src.crud.notification_template import (
    create_system_template,
    delete_system_template,
    get_system_templates,
    update_system_template,
)

# Permission CRUD imports
from src.crud.permission import (
    create_permission,
    delete_permission,
    get_all_permissions,
    update_permission,
)
from src.crud.role_permission import (
    get_permission_matrix,
    grant_permission_to_role,
    revoke_permission_from_role,
)

# CRUD imports - these will be created as part of the notifications/files implementation
from src.crud.system_config import (
    get_s3_config,
    get_system_config_by_key,
    update_system_config,
)
from src.crud.user_type_permission import (
    get_extended_permission_matrix,
    grant_permission_to_user_type,
    revoke_permission_from_user_type,
)
from src.logger.logger import Logger
from src.models.audit_log import AuditAction
from src.serialisers.admin import (
    CreateNotificationProviderRequest,
    CreateNotificationProviderResponse,
    CreateSystemCategoryRequest,
    CreateSystemCategoryResponse,
    CreateSystemTemplateRequest,
    CreateSystemTemplateResponse,
    DeleteNotificationProviderResponse,
    DeleteSystemTemplateResponse,
    ListNotificationProvidersResponse,
    ListOrganizationFileSettingsResponse,
    ListSystemCategoriesResponse,
    ListSystemTemplatesResponse,
    NotificationProviderResponse,
    OrganizationFileSettingsResponse,
    S3ConfigResponse,
    SystemCategoryResponse,
    SystemTemplateResponse,
    TriggerHardDeleteRequest,
    TriggerHardDeleteResponse,
    UpdateNotificationProviderRequest,
    UpdateNotificationProviderResponse,
    UpdateS3ConfigRequest,
    UpdateS3ConfigResponse,
    UpdateSystemTemplateRequest,
    UpdateSystemTemplateResponse,
)
from src.serialisers.maintenance import (
    MaintenanceConfigResponse,
    MaintenanceHistoryListResponse,
    MaintenanceHistoryResponse,
    UpdateMaintenanceRequest,
    UpdateMaintenanceResponse,
    UserSummary,
)
from src.serialisers.permission import (
    AssignRolePermissionRequest,
    AssignUserTypePermissionRequest,
    CreatePermissionRequest,
    ExtendedPermissionMatrixResponse,
    ListPermissionsResponse,
    PermissionMatrixResponse,
    PermissionResponse,
    RevokeRolePermissionRequest,
    RevokeUserTypePermissionRequest,
    RoleWithPermissionsResponse,
    UpdatePermissionRequest,
    UserTypeWithPermissionsResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.files.file_manager import file_manager


router = APIRouter(prefix="/admin", tags=["admin"])

# Rate limit for destructive operations (hard delete)
RATE_LIMIT_HARD_DELETE = "2/minute"


# =============================================================================
# Notification Provider Endpoints
# =============================================================================


@router.get(
    "/notifications/providers", response_model=ListNotificationProvidersResponse
)
async def list_notification_providers(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    channel: Optional[str] = Query(
        None, description="Filter by channel (sms, whatsapp, email)"
    ),
    include_inactive: bool = Query(False, description="Include inactive providers"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """
    List all notification providers.

    Requires super admin access (is_admin=True).
    """
    providers, total = await get_notification_providers(
        session=session,
        channel=channel,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )

    provider_responses = [
        NotificationProviderResponse(
            id=str(provider.id),
            name=provider.name,
            channel=provider.channel,
            is_active=provider.is_active if provider.is_active is not None else False,
            is_default=(
                provider.is_default if provider.is_default is not None else False
            ),
            config=_mask_sensitive_config(provider.config),
            created_time=(
                provider.created_time.isoformat() if provider.created_time else ""
            ),
            updated_time=(
                provider.updated_time.isoformat() if provider.updated_time else None
            ),
        )
        for provider in providers
    ]

    return ListNotificationProvidersResponse(
        items=provider_responses, total=total, limit=limit, offset=offset
    )


@router.post(
    "/notifications/providers",
    response_model=CreateNotificationProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_provider_endpoint(
    request: CreateNotificationProviderRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new notification provider.

    Requires super admin access (is_admin=True).
    """
    try:
        provider = await create_notification_provider(
            session=session, provider_data=request.model_dump()
        )

        # Audit log the creation
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="NotificationProvider",
            resource_id=str(provider.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"name": provider.name, "channel": provider.channel},
        )

        return CreateNotificationProviderResponse(
            message="Notification provider created successfully",
            message_code=get_response_code("common.success"),
            provider=NotificationProviderResponse(
                id=str(provider.id),
                name=provider.name,
                channel=provider.channel,
                is_active=(
                    provider.is_active if provider.is_active is not None else False
                ),
                is_default=(
                    provider.is_default if provider.is_default is not None else False
                ),
                config=_mask_sensitive_config(provider.config),
                created_time=(
                    provider.created_time.isoformat() if provider.created_time else ""
                ),
                updated_time=(
                    provider.updated_time.isoformat() if provider.updated_time else None
                ),
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in create_notification_provider_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put(
    "/notifications/providers/{provider_id}",
    response_model=UpdateNotificationProviderResponse,
)
async def update_notification_provider_endpoint(
    provider_id: UUID,
    request: UpdateNotificationProviderRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a notification provider.

    Requires super admin access (is_admin=True).
    """
    try:
        provider = await update_notification_provider(
            session=session,
            provider_id=str(provider_id),
            provider_data=request.model_dump(exclude_unset=True),
        )

        if not provider:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification provider not found",
                detail_code="notification.template_not_found",
            )

        # Audit log the update
        await audit_service.log_action(
            session=session,
            organization_id=current_user.organization_id,
            action=AuditAction.UPDATE,
            resource_type="NotificationProvider",
            resource_id=str(provider_id),
            actor_id=current_user.id,
            changes=request.model_dump(exclude_unset=True),
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UpdateNotificationProviderResponse(
            message="Notification provider updated successfully",
            message_code=get_response_code("common.success"),
            provider=NotificationProviderResponse(
                id=str(provider.id),
                name=provider.name,
                channel=provider.channel,
                is_active=(
                    provider.is_active if provider.is_active is not None else False
                ),
                is_default=(
                    provider.is_default if provider.is_default is not None else False
                ),
                config=_mask_sensitive_config(provider.config),
                created_time=(
                    provider.created_time.isoformat() if provider.created_time else ""
                ),
                updated_time=(
                    provider.updated_time.isoformat() if provider.updated_time else None
                ),
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in update_notification_provider_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete(
    "/notifications/providers/{provider_id}",
    response_model=DeleteNotificationProviderResponse,
)
async def delete_notification_provider_endpoint(
    provider_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Deactivate a notification provider (soft delete).

    Requires super admin access (is_admin=True).
    """
    try:
        provider = await deactivate_notification_provider(
            session=session, provider_id=str(provider_id)
        )

        if not provider:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification provider not found",
                detail_code="notification.template_not_found",
            )

        # Audit log the deletion
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="NotificationProvider",
            resource_id=str(provider_id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"name": provider.name, "channel": provider.channel},
        )

        return DeleteNotificationProviderResponse(
            message="Notification provider deactivated successfully",
            message_code=get_response_code("notification.template_deleted"),
            provider_id=str(provider.id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in delete_notification_provider_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# System Template Endpoints
# =============================================================================


@router.get("/notifications/templates", response_model=ListSystemTemplatesResponse)
async def list_system_templates(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    channel: Optional[str] = Query(
        None, description="Filter by channel (sms, whatsapp, email)"
    ),
    include_inactive: bool = Query(False, description="Include inactive templates"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all system notification templates (organization_id is NULL).

    Requires super admin access (is_admin=True).
    """
    templates, total = await get_system_templates(
        session=session,
        channel=channel,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )

    template_responses = [
        SystemTemplateResponse(
            id=str(template.id),
            code=template.code,
            name=template.name,
            description=template.description,
            channel=template.channel,
            subject=template.subject,
            body_text=template.body_text,
            body_html=template.body_html,
            variables=template.variables,
            is_active=template.is_active if template.is_active is not None else False,
            created_time=(
                template.created_time.isoformat() if template.created_time else ""
            ),
            updated_time=(
                template.updated_time.isoformat() if template.updated_time else None
            ),
        )
        for template in templates
    ]

    return ListSystemTemplatesResponse(
        items=template_responses, total=total, limit=limit, offset=offset
    )


@router.post(
    "/notifications/templates",
    response_model=CreateSystemTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_system_template_endpoint(
    request: CreateSystemTemplateRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new system notification template.

    System templates have organization_id=NULL and are available to all organizations.

    Requires super admin access (is_admin=True).
    """
    try:
        template = await create_system_template(
            session=session, template_data=request.model_dump()
        )

        # Audit log the creation
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemTemplate",
            resource_id=str(template.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "code": template.code,
                "name": template.name,
                "channel": template.channel,
            },
        )

        return CreateSystemTemplateResponse(
            message="System template created successfully",
            message_code=get_response_code("notification.template_created"),
            template=SystemTemplateResponse(
                id=str(template.id),
                code=template.code,
                name=template.name,
                description=template.description,
                channel=template.channel,
                subject=template.subject,
                body_text=template.body_text,
                body_html=template.body_html,
                variables=template.variables,
                is_active=(
                    template.is_active if template.is_active is not None else False
                ),
                created_time=(
                    template.created_time.isoformat() if template.created_time else ""
                ),
                updated_time=(
                    template.updated_time.isoformat() if template.updated_time else None
                ),
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in create_system_template_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put(
    "/notifications/templates/{template_id}",
    response_model=UpdateSystemTemplateResponse,
)
async def update_system_template_endpoint(
    template_id: UUID,
    request: UpdateSystemTemplateRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a system notification template.

    Requires super admin access (is_admin=True).
    """
    try:
        template = await update_system_template(
            session=session,
            template_id=str(template_id),
            template_data=request.model_dump(exclude_unset=True),
        )

        if not template:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System template not found",
                detail_code="notification.template_not_found",
            )

        # Audit log the update
        await audit_service.log_action(
            session=session,
            organization_id=current_user.organization_id,
            action=AuditAction.UPDATE,
            resource_type="SystemTemplate",
            resource_id=str(template_id),
            actor_id=current_user.id,
            changes=request.model_dump(exclude_unset=True),
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UpdateSystemTemplateResponse(
            message="System template updated successfully",
            message_code=get_response_code("notification.template_updated"),
            template=SystemTemplateResponse(
                id=str(template.id),
                code=template.code,
                name=template.name,
                description=template.description,
                channel=template.channel,
                subject=template.subject,
                body_text=template.body_text,
                body_html=template.body_html,
                variables=template.variables,
                is_active=(
                    template.is_active if template.is_active is not None else False
                ),
                created_time=(
                    template.created_time.isoformat() if template.created_time else ""
                ),
                updated_time=(
                    template.updated_time.isoformat() if template.updated_time else None
                ),
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in update_system_template_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete(
    "/notifications/templates/{template_id}",
    response_model=DeleteSystemTemplateResponse,
)
async def delete_system_template_endpoint(
    template_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a system notification template (soft delete).

    Requires super admin access (is_admin=True).
    """
    try:
        template = await delete_system_template(
            session=session, template_id=str(template_id)
        )

        if not template:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System template not found",
                detail_code="notification.template_not_found",
            )

        # Audit log the deletion
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemTemplate",
            resource_id=str(template_id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"code": template.code, "name": template.name},
        )

        return DeleteSystemTemplateResponse(
            message="System template deleted successfully",
            message_code=get_response_code("notification.template_deleted"),
            template_id=str(template.id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in delete_system_template_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# System Category Endpoints
# =============================================================================


@router.get("/notifications/categories", response_model=ListSystemCategoriesResponse)
async def list_system_categories(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List all system notification categories (organization_id is NULL).

    Requires super admin access (is_admin=True).
    """
    categories, total = await get_system_categories(
        session=session, limit=limit, offset=offset
    )

    category_responses = [
        SystemCategoryResponse(
            id=str(category.id),
            code=category.code,
            name=category.name,
            description=category.description,
            default_enabled=(
                category.default_enabled
                if category.default_enabled is not None
                else False
            ),
            user_configurable=(
                category.user_configurable
                if category.user_configurable is not None
                else False
            ),
            display_order=(
                category.display_order if category.display_order is not None else 0
            ),
            created_time=(
                category.created_time.isoformat() if category.created_time else ""
            ),
            updated_time=(
                category.updated_time.isoformat() if category.updated_time else None
            ),
        )
        for category in categories
    ]

    return ListSystemCategoriesResponse(
        items=category_responses, total=total, limit=limit, offset=offset
    )


@router.post(
    "/notifications/categories",
    response_model=CreateSystemCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_system_category_endpoint(
    request: CreateSystemCategoryRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new system notification category.

    System categories have organization_id=NULL and are available to all organizations.

    Requires super admin access (is_admin=True).
    """
    try:
        category = await create_system_category(
            session=session, category_data=request.model_dump()
        )

        # Audit log the creation
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemCategory",
            resource_id=str(category.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"code": category.code, "name": category.name},
        )

        return CreateSystemCategoryResponse(
            message="System category created successfully",
            message_code=get_response_code("common.success"),
            category=SystemCategoryResponse(
                id=str(category.id),
                code=category.code,
                name=category.name,
                description=category.description,
                default_enabled=(
                    category.default_enabled
                    if category.default_enabled is not None
                    else False
                ),
                user_configurable=(
                    category.user_configurable
                    if category.user_configurable is not None
                    else False
                ),
                display_order=(
                    category.display_order if category.display_order is not None else 0
                ),
                created_time=(
                    category.created_time.isoformat() if category.created_time else ""
                ),
                updated_time=(
                    category.updated_time.isoformat() if category.updated_time else None
                ),
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in create_system_category_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# File Admin Endpoints
# =============================================================================


@router.get("/files/settings", response_model=ListOrganizationFileSettingsResponse)
async def list_all_organization_file_settings(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List file settings for all organizations.

    Requires super admin access (is_admin=True).
    """
    settings, total = await get_all_organization_file_settings(
        session=session, limit=limit, offset=offset
    )

    settings_responses = [
        OrganizationFileSettingsResponse(
            id=str(setting.id),
            organization_id=str(setting.organization_id),
            organization_name=(
                setting.organization.name
                if hasattr(setting, "organization") and setting.organization
                else None
            ),
            max_file_size_bytes=(
                setting.max_file_size_bytes
                if setting.max_file_size_bytes is not None
                else 0
            ),
            max_video_size_bytes=(
                setting.max_video_size_bytes
                if setting.max_video_size_bytes is not None
                else 0
            ),
            allowed_extensions=setting.allowed_extensions or [],
            user_storage_quota_bytes=setting.user_storage_quota_bytes,
            org_storage_quota_bytes=setting.org_storage_quota_bytes,
            signed_url_expiry_seconds=(
                setting.signed_url_expiry_seconds
                if setting.signed_url_expiry_seconds is not None
                else 0
            ),
            deleted_file_retention_days=(
                setting.deleted_file_retention_days
                if setting.deleted_file_retention_days is not None
                else 0
            ),
            created_time=(
                setting.created_time.isoformat() if setting.created_time else ""
            ),
            updated_time=(
                setting.updated_time.isoformat() if setting.updated_time else None
            ),
        )
        for setting in settings
    ]

    return ListOrganizationFileSettingsResponse(
        items=settings_responses, total=total, limit=limit, offset=offset
    )


@router.post("/files/hard-delete", response_model=TriggerHardDeleteResponse)
@limiter.limit(RATE_LIMIT_HARD_DELETE)
async def trigger_hard_delete_old_files(
    body: TriggerHardDeleteRequest,
    request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Trigger hard deletion of files that have been soft-deleted past their retention period.

    Requires super admin access (is_admin=True).

    Use dry_run=True (default) to preview what would be deleted without actually deleting.

    This endpoint is rate-limited to 2 requests per minute to prevent abuse.
    """
    try:
        if file_manager is None:
            raise create_http_exception(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="File manager service is not available",
                detail_code="file.service_unavailable",
            )

        result = await file_manager.hard_delete_expired_files(  # type: ignore[attr-defined]
            session=session,
            organization_id=body.organization_id,
            dry_run=body.dry_run,
        )

        # Audit log the hard delete operation
        await audit_service.log_action(
            session=session,
            organization_id=current_user.organization_id,
            action=AuditAction.DELETE,
            resource_type="FileHardDelete",
            resource_id=body.organization_id or "all",
            actor_id=current_user.id,
            changes={
                "files_deleted": result["files_deleted"],
                "total_bytes_freed": result["total_bytes_freed"],
                "dry_run": body.dry_run,
            },
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        action = "would be deleted" if body.dry_run else "deleted"
        return TriggerHardDeleteResponse(
            message=f"{result['files_deleted']} files {action}, freeing {result['total_bytes_freed']} bytes",
            message_code=get_response_code("admin.organization_deactivated"),
            files_deleted=result["files_deleted"],
            total_bytes_freed=result["total_bytes_freed"],
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in trigger_hard_delete_old_files: {e}\n{error_tb}"
        )
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Permission Endpoints
# =============================================================================


@router.get("/permissions", response_model=ListPermissionsResponse)
async def list_permissions(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    resource: Optional[str] = Query(
        None, description="Filter by resource (e.g., 'users', 'roles')"
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    List all permissions with optional resource filtering.

    Requires super admin access (is_admin=True).
    """
    permissions, total = await get_all_permissions(
        session=session, resource=resource, limit=limit, offset=offset
    )

    permission_responses = [
        PermissionResponse(
            id=perm.id,
            code=perm.code,
            name=perm.name,
            description=perm.description,
            resource=perm.resource,
            action=perm.action,
            display_order=perm.display_order if perm.display_order is not None else 0,
            created_time=perm.created_time.isoformat() if perm.created_time else "",
        )
        for perm in permissions
    ]

    return ListPermissionsResponse(
        items=permission_responses, total=total, limit=limit, offset=offset
    )


@router.post(
    "/permissions",
    response_model=PermissionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_permission_endpoint(
    request: CreatePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new permission.

    Permission codes must be in format 'resource:action' (e.g., 'users:read', 'roles:write').

    Requires super admin access (is_admin=True).
    """
    try:
        permission = await create_permission(
            session=session,
            code=request.code,
            name=request.name,
            description=request.description,
            display_order=request.display_order,
        )

        # Audit log the creation
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Permission",
            resource_id=str(permission.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"code": permission.code, "name": permission.name},
        )

        return PermissionResponse(
            id=permission.id,
            code=permission.code,
            name=permission.name,
            description=permission.description,
            resource=permission.resource,
            action=permission.action,
            display_order=(
                permission.display_order if permission.display_order is not None else 0
            ),
            created_time=(
                permission.created_time.isoformat() if permission.created_time else ""
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in create_permission_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission_endpoint(
    permission_id: UUID,
    request: UpdatePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a permission's name, description, or display order.

    Note: The permission code cannot be changed after creation.

    Requires super admin access (is_admin=True).
    """
    try:
        permission = await update_permission(
            session=session,
            permission_id=str(permission_id),
            name=request.name,
            description=request.description,
            display_order=request.display_order,
        )

        # Audit log the update
        await audit_service.log_action(
            session=session,
            organization_id=current_user.organization_id,
            action=AuditAction.UPDATE,
            resource_type="Permission",
            resource_id=str(permission_id),
            actor_id=current_user.id,
            changes={
                "name": request.name,
                "description": request.description,
                "display_order": request.display_order,
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return PermissionResponse(
            id=permission.id,
            code=permission.code,
            name=permission.name,
            description=permission.description,
            resource=permission.resource,
            action=permission.action,
            display_order=(
                permission.display_order if permission.display_order is not None else 0
            ),
            created_time=(
                permission.created_time.isoformat() if permission.created_time else ""
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="permission.not_found",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in update_permission_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/permissions/{permission_id}")
async def delete_permission_endpoint(
    permission_id: UUID,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Soft delete a permission.

    Requires super admin access (is_admin=True).
    """
    try:
        permission = await delete_permission(
            session=session, permission_id=str(permission_id)
        )

        # Audit log the deletion
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Permission",
            resource_id=str(permission_id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"code": permission.code, "name": permission.name},
        )

        return {
            "message": "Permission deleted successfully",
            "message_code": get_response_code("common.success"),
            "permission_id": str(permission.id),
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="permission.not_found",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in delete_permission_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/permissions/matrix", response_model=PermissionMatrixResponse)
async def get_permissions_matrix(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the global permission matrix.

    Returns all permissions and all global roles with their assigned permission IDs.
    This is useful for building a permission matrix UI.

    Requires super admin access (is_admin=True).
    """
    try:
        matrix = await get_permission_matrix(session=session)

        # Convert to response models
        permission_responses = [
            PermissionResponse(
                id=UUID(p["id"]),
                code=p["code"],
                name=p["name"],
                description=p["description"],
                resource=p["resource"],
                action=p["action"],
                display_order=p["display_order"],
                created_time="",  # Not included in matrix data
            )
            for p in matrix["permissions"]
        ]

        role_responses = [
            RoleWithPermissionsResponse(
                id=UUID(r["id"]),
                name=r["name"],
                description=r["description"],
                permission_ids=[UUID(pid) for pid in r["permission_ids"]],
            )
            for r in matrix["roles"]
        ]

        return PermissionMatrixResponse(
            permissions=permission_responses, roles=role_responses
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in get_permissions_matrix: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Role Permission Endpoints
# =============================================================================


@router.post("/role-permissions/assign")
async def assign_role_permission(
    request: AssignRolePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Assign a permission to a global role.

    Requires super admin access (is_admin=True).
    """
    try:
        role_permission = await grant_permission_to_role(
            session=session,
            role_id=str(request.role_id),
            permission_id=str(request.permission_id),
            granted_by_user_id=current_user.id,
        )

        # Audit log the assignment
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="RolePermission",
            resource_id=str(role_permission.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "role_id": str(request.role_id),
                "permission_id": str(request.permission_id),
            },
        )

        return {
            "message": "Permission assigned to role successfully",
            "message_code": get_response_code("common.success"),
            "role_permission": {
                "id": str(role_permission.id),
                "role_id": str(role_permission.role_id),
                "permission_id": str(role_permission.permission_id),
                "granted_by": (
                    str(role_permission.granted_by)
                    if role_permission.granted_by
                    else None
                ),
                "granted_time": (
                    role_permission.granted_time.isoformat()
                    if role_permission.granted_time
                    else None
                ),
            },
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in assign_role_permission: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("/role-permissions/revoke")
async def revoke_role_permission(
    request: RevokeRolePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Revoke a permission from a global role.

    Requires super admin access (is_admin=True).
    """
    try:
        role_permission = await revoke_permission_from_role(
            session=session,
            role_id=str(request.role_id),
            permission_id=str(request.permission_id),
        )

        # Audit log the revocation
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="RolePermission",
            resource_id=str(role_permission.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "role_id": str(request.role_id),
                "permission_id": str(request.permission_id),
            },
        )

        return {
            "message": "Permission revoked from role successfully",
            "message_code": get_response_code("common.success"),
            "role_permission_id": str(role_permission.id),
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in revoke_role_permission: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# User Type Permission Endpoints
# =============================================================================


@router.post("/user-type-permissions/assign")
async def assign_user_type_permission(
    request: AssignUserTypePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Assign a permission to a global user type.

    When a permission is granted to a user type, all users with that user type
    will have access to the permission (in addition to any permissions from roles).

    Requires super admin access (is_admin=True).
    """
    try:
        user_type_permission = await grant_permission_to_user_type(
            session=session,
            user_type_id=str(request.user_type_id),
            permission_id=str(request.permission_id),
            granted_by_user_id=current_user.id,
        )

        # Audit log the assignment
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserTypePermission",
            resource_id=str(user_type_permission.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_type_id": str(request.user_type_id),
                "permission_id": str(request.permission_id),
            },
        )

        return {
            "message": "Permission assigned to user type successfully",
            "message_code": get_response_code("common.success"),
            "user_type_permission": {
                "id": str(user_type_permission.id),
                "user_type_id": str(user_type_permission.user_type_id),
                "permission_id": str(user_type_permission.permission_id),
                "granted_by": (
                    str(user_type_permission.granted_by)
                    if user_type_permission.granted_by
                    else None
                ),
                "granted_time": (
                    user_type_permission.granted_time.isoformat()
                    if user_type_permission.granted_time
                    else None
                ),
            },
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in assign_user_type_permission: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.post("/user-type-permissions/revoke")
async def revoke_user_type_permission(
    request: RevokeUserTypePermissionRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Revoke a permission from a global user type.

    Requires super admin access (is_admin=True).
    """
    try:
        user_type_permission = await revoke_permission_from_user_type(
            session=session,
            user_type_id=str(request.user_type_id),
            permission_id=str(request.permission_id),
        )

        # Audit log the revocation
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="UserTypePermission",
            resource_id=str(user_type_permission.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "user_type_id": str(request.user_type_id),
                "permission_id": str(request.permission_id),
            },
        )

        return {
            "message": "Permission revoked from user type successfully",
            "message_code": get_response_code("common.success"),
            "user_type_permission_id": str(user_type_permission.id),
        }
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in revoke_user_type_permission: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get(
    "/permissions/matrix/extended", response_model=ExtendedPermissionMatrixResponse
)
async def get_extended_permissions_matrix(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the extended permission matrix including user types.

    Returns all permissions, all global roles with their assigned permission IDs,
    and all user types with their assigned permission IDs.
    This is useful for building a comprehensive permission matrix UI.

    Requires super admin access (is_admin=True).
    """
    try:
        matrix = await get_extended_permission_matrix(session=session)

        # Convert to response models
        permission_responses = [
            PermissionResponse(
                id=UUID(p["id"]),
                code=p["code"],
                name=p["name"],
                description=p["description"],
                resource=p["resource"],
                action=p["action"],
                display_order=p["display_order"],
                created_time="",  # Not included in matrix data
            )
            for p in matrix["permissions"]
        ]

        role_responses = [
            RoleWithPermissionsResponse(
                id=UUID(r["id"]),
                name=r["name"],
                description=r["description"],
                permission_ids=[UUID(pid) for pid in r["permission_ids"]],
            )
            for r in matrix["roles"]
        ]

        user_type_responses = [
            UserTypeWithPermissionsResponse(
                id=UUID(ut["id"]),
                name=ut["name"],
                code=ut["code"],
                description=ut["description"],
                permission_ids=[UUID(pid) for pid in ut["permission_ids"]],
            )
            for ut in matrix["user_types"]
        ]

        return ExtendedPermissionMatrixResponse(
            permissions=permission_responses,
            roles=role_responses,
            user_types=user_type_responses,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in get_extended_permissions_matrix: {e}\n{error_tb}"
        )
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# S3 Storage Config Endpoints
# =============================================================================


@router.get("/storage/s3", response_model=S3ConfigResponse)
async def get_s3_storage_config(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get S3 storage configuration.

    Requires super admin access (is_admin=True).
    """
    config = await get_s3_config(session=session)

    if not config:
        return S3ConfigResponse(
            enabled=False, bucket=None, region=None, endpoint_url=None
        )

    return S3ConfigResponse(
        enabled=config.get("enabled", False),
        bucket=config.get("bucket"),
        region=config.get("region"),
        endpoint_url=config.get("endpoint_url"),
    )


@router.put("/storage/s3", response_model=UpdateS3ConfigResponse)
async def update_s3_storage_config(
    request: UpdateS3ConfigRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update S3 storage configuration.

    Requires super admin access (is_admin=True).
    """
    try:
        # Get old config for audit logging
        old_config = await get_s3_config(session=session) or {}

        await update_system_config(
            session=session,
            key="storage.s3.enabled",
            value=request.enabled,
            description="Enable or disable S3 storage",
            updated_by_user_id=current_user.id,
        )

        if request.bucket is not None:
            await update_system_config(
                session=session,
                key="storage.s3.bucket",
                value=request.bucket,
                description="S3 bucket name",
                updated_by_user_id=current_user.id,
            )

        if request.region is not None:
            await update_system_config(
                session=session,
                key="storage.s3.region",
                value=request.region,
                description="AWS region",
                updated_by_user_id=current_user.id,
            )

        if request.endpoint_url is not None:
            await update_system_config(
                session=session,
                key="storage.s3.endpoint_url",
                value=request.endpoint_url,
                description="Custom S3-compatible endpoint URL",
                updated_by_user_id=current_user.id,
            )

        config = await get_s3_config(session=session)

        # Audit log the S3 config update
        await audit_service.log_action(
            session=session,
            organization_id=current_user.organization_id,
            action=AuditAction.UPDATE,
            resource_type="S3Config",
            resource_id="storage.s3",
            actor_id=current_user.id,
            changes={
                "enabled": {"old": old_config.get("enabled"), "new": request.enabled},
                "bucket": {"old": old_config.get("bucket"), "new": request.bucket},
                "region": {"old": old_config.get("region"), "new": request.region},
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        return UpdateS3ConfigResponse(
            message="S3 configuration updated successfully",
            message_code=get_response_code("common.success"),
            config=S3ConfigResponse(
                enabled=config.get("enabled", False) if config else False,
                bucket=config.get("bucket") if config else None,
                region=config.get("region") if config else None,
                endpoint_url=config.get("endpoint_url") if config else None,
            ),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.bad_request",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in update_s3_storage_config: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# =============================================================================
# Maintenance Mode Endpoints
# =============================================================================


@router.get("/maintenance", response_model=MaintenanceConfigResponse)
async def get_maintenance_config_admin(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get full maintenance configuration with history (super admin only).

    Returns:
        MaintenanceConfigResponse with full configuration and metadata
    """
    from datetime import datetime

    config = await get_maintenance_config(session)

    # Parse datetime strings back to datetime objects if present
    scheduled_start = None
    scheduled_end = None

    if config.get("scheduled_start"):
        scheduled_start = datetime.fromisoformat(config["scheduled_start"])

    if config.get("scheduled_end"):
        scheduled_end = datetime.fromisoformat(config["scheduled_end"])

    # Get the SystemConfig entry to retrieve metadata
    system_config = await get_system_config_by_key(session, "maintenance.mode")

    return MaintenanceConfigResponse(
        enabled=config.get("enabled", False),
        message=config.get("message"),
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        allow_super_admin=config.get("allow_super_admin", True),
        updated_time=(
            system_config.updated_time.isoformat()
            if system_config and system_config.updated_time
            else None
        ),
        updated_by_user_id=(
            str(system_config.updated_by_user_id)
            if system_config and system_config.updated_by_user_id
            else None
        ),
    )


@router.put("/maintenance", response_model=UpdateMaintenanceResponse)
async def update_maintenance_config_endpoint(
    request: UpdateMaintenanceRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update maintenance mode configuration (super admin only).

    Allows super admins to enable/disable maintenance mode, set custom messages,
    schedule maintenance windows, and control super admin access during maintenance.

    Args:
        request: UpdateMaintenanceRequest with new configuration
        current_user: Current authenticated super admin user
        session: Database session

    Returns:
        UpdateMaintenanceResponse with updated configuration
    """
    from datetime import datetime

    from src.crud.maintenance import (
        cancel_scheduled_maintenance,
        end_maintenance,
        get_active_maintenance_history,
        get_maintenance_history,
        start_maintenance,
    )
    from src.models.maintenance_history import MaintenanceStatus

    # Get current state before making changes
    current_config = await get_maintenance_config(session)
    was_enabled = current_config.get("enabled", False)

    # Track maintenance history changes
    if request.enabled and not was_enabled:
        # Maintenance is being enabled - create new history record
        await start_maintenance(
            session=session,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            message=request.message,
            started_by_user_id=str(current_user.id),
            is_immediate=True,  # Manual enable is immediate
        )
    elif not request.enabled and was_enabled:
        # Maintenance is being disabled - end the active maintenance
        active_history = await get_active_maintenance_history(session)
        if active_history:
            await end_maintenance(
                session=session,
                history_id=active_history.id,
                ended_by_user_id=str(current_user.id),
            )
    elif not request.enabled and request.scheduled_start and request.scheduled_end:
        # Scheduling maintenance for the future (not enabled yet)
        # Check if there's already a scheduled maintenance and cancel it
        histories, _ = await get_maintenance_history(
            session=session,
            limit=1,
            status_filter=MaintenanceStatus.SCHEDULED,
        )
        if histories:
            # Cancel existing scheduled maintenance
            await cancel_scheduled_maintenance(
                session=session,
                history_id=histories[0].id,
                ended_by_user_id=str(current_user.id),
            )
        # Create new scheduled maintenance
        await start_maintenance(
            session=session,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            message=request.message,
            started_by_user_id=str(current_user.id),
            is_immediate=False,  # Scheduled for the future
        )

    # Update the maintenance configuration
    updated_config = await update_maintenance_config(
        session=session,
        enabled=request.enabled,
        message=request.message,
        scheduled_start=request.scheduled_start,
        scheduled_end=request.scheduled_end,
        allow_super_admin=request.allow_super_admin,
        updated_by_user_id=str(current_user.id),
    )

    # Audit log the maintenance config update
    await audit_service.log_action(
        session=session,
        organization_id=current_user.organization_id,
        action=AuditAction.UPDATE,
        resource_type="MaintenanceConfig",
        resource_id="maintenance.mode",
        actor_id=current_user.id,
        changes={
            "enabled": {"old": was_enabled, "new": request.enabled},
            "message": {"old": current_config.get("message"), "new": request.message},
        },
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    # Broadcast maintenance mode change to all connected WebSocket clients
    from src.services.websocket import redis_pubsub

    await redis_pubsub.broadcast_maintenance_mode(
        enabled=request.enabled,
        message=request.message,
    )

    # Parse datetime strings back to datetime objects for response
    scheduled_start = None
    scheduled_end = None

    if updated_config.get("scheduled_start"):
        scheduled_start = datetime.fromisoformat(updated_config["scheduled_start"])

    if updated_config.get("scheduled_end"):
        scheduled_end = datetime.fromisoformat(updated_config["scheduled_end"])

    # Get the SystemConfig entry to retrieve metadata
    system_config = await get_system_config_by_key(session, "maintenance.mode")

    return UpdateMaintenanceResponse(
        message="Maintenance configuration updated successfully",
        message_code=get_response_code("maintenance.updated"),
        config=MaintenanceConfigResponse(
            enabled=updated_config.get("enabled", False),
            message=updated_config.get("message"),
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
            allow_super_admin=updated_config.get("allow_super_admin", True),
            updated_time=(
                system_config.updated_time.isoformat()
                if system_config and system_config.updated_time
                else None
            ),
            updated_by_user_id=(
                str(system_config.updated_by_user_id)
                if system_config and system_config.updated_by_user_id
                else None
            ),
        ),
    )


@router.get("/maintenance/history", response_model=MaintenanceHistoryListResponse)
async def get_maintenance_history_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(
        default=20, ge=1, le=100, description="Number of records to return"
    ),
    offset: int = Query(default=0, ge=0, description="Number of records to skip"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
):
    """
    Get maintenance history (super admin only).

    Returns a paginated list of maintenance history records showing
    both scheduled and actual maintenance periods.

    Args:
        current_user: Current authenticated super admin user
        session: Database session
        limit: Number of records to return
        offset: Number of records to skip
        status: Optional status filter (scheduled, active, completed, cancelled)

    Returns:
        MaintenanceHistoryListResponse with paginated history records
    """
    from src.crud.maintenance import get_maintenance_history
    from src.models.maintenance_history import MaintenanceStatus

    # Parse status filter if provided
    status_filter = None
    if status:
        try:
            status_filter = MaintenanceStatus(status)
        except ValueError:
            pass  # Invalid status, ignore filter

    histories, total = await get_maintenance_history(
        session=session,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
    )

    # Convert to response format
    items = []
    for history in histories:
        started_by_data = None
        if history.started_by:
            started_by_data = UserSummary(
                id=str(history.started_by.id),
                first_name=history.started_by.first_name,
                last_name=history.started_by.last_name,
                email=history.started_by.email,
            )

        ended_by_data = None
        if history.ended_by:
            ended_by_data = UserSummary(
                id=str(history.ended_by.id),
                first_name=history.ended_by.first_name,
                last_name=history.ended_by.last_name,
                email=history.ended_by.email,
            )

        items.append(
            MaintenanceHistoryResponse(
                id=str(history.id),
                status=history.status,
                scheduled_start=history.scheduled_start,
                scheduled_end=history.scheduled_end,
                actual_start=history.actual_start,
                actual_end=history.actual_end,
                message=history.message,
                started_by=started_by_data,
                ended_by=ended_by_data,
                created_time=history.created_time,
            )
        )

    return MaintenanceHistoryListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _mask_sensitive_config(config: dict) -> dict:
    """Mask sensitive fields in provider config for display"""
    if not config:
        return {}

    # Expanded list of sensitive key patterns (Finding 4 fix)
    sensitive_keys = [
        "secret_access_key",
        "auth_token",
        "password",
        "api_key",
        "secret",
        "private_key",
        "access_token",
        "bearer_token",
        "client_secret",
        "credential",
        "credentials",
        "refresh_token",
        "signing_key",
        "encryption_key",
        "jwt_secret",
        "oauth_secret",
        "webhook_secret",
        "passphrase",
        "pin",
        "key",
    ]

    masked = {}
    for key, value in config.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            if isinstance(value, str) and len(value) > 4:
                masked[key] = value[:4] + "****" + value[-2:]
            else:
                masked[key] = "********"
        else:
            masked[key] = value

    return masked
