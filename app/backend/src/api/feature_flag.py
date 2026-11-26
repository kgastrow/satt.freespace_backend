"""
Feature flag management API endpoints.
Super admin endpoints for CRUD operations on flags and overrides.
Organization endpoint for resolved flags with caching.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.feature_flag import (
    create_feature_flag,
    create_override,
    delete_feature_flag,
    delete_override,
    get_all_feature_flags_with_overrides,
    get_feature_flag_by_id,
    get_overrides_for_flag,
    get_resolved_flags_for_organization,
    update_feature_flag,
)
from src.logger.logger import Logger
from src.serialisers.feature_flag import (
    CreateFeatureFlagRequest,
    CreateFeatureFlagResponse,
    CreateOverrideRequest,
    CreateOverrideResponse,
    DeleteFeatureFlagResponse,
    DeleteOverrideResponse,
    FeatureFlagListResponse,
    FeatureFlagOverrideListResponse,
    FeatureFlagOverrideResponse,
    FeatureFlagOverrideSummary,
    FeatureFlagResponse,
    FeatureFlagWithOverridesResponse,
    ResolvedFeatureFlagsResponse,
    UpdateFeatureFlagRequest,
    UpdateFeatureFlagResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.feature_flag_cache import feature_flag_cache


# Super admin router
admin_router = APIRouter(prefix="/admin/feature-flags", tags=["admin", "feature-flags"])

# Organization router
org_router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


@admin_router.post(
    "", response_model=CreateFeatureFlagResponse, status_code=status.HTTP_201_CREATED
)
async def create_feature_flag_endpoint(
    request: CreateFeatureFlagRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new global feature flag (super admin only)."""
    try:
        flag = await create_feature_flag(session=session, data=request.model_dump())

        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="FeatureFlag",
            resource_id=str(flag.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "key": flag.key,
                "name": flag.name,
                "default_enabled": flag.default_enabled,
            },
        )

        response = FeatureFlagResponse(
            id=flag.id,
            key=flag.key,
            name=flag.name,
            description=flag.description,
            default_enabled=flag.default_enabled,
            created_time=flag.created_time.isoformat() if flag.created_time else "",
            updated_time=flag.updated_time.isoformat() if flag.updated_time else "",
        )
        return CreateFeatureFlagResponse(
            message="Feature flag created successfully",
            message_code=get_response_code("feature_flag.created"),
            flag=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in create_feature_flag_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.get("", response_model=FeatureFlagListResponse)
async def list_feature_flags_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all feature flags with pagination and overrides (super admin only)."""
    try:
        flags_with_overrides, total = await get_all_feature_flags_with_overrides(
            session=session, limit=limit, offset=offset
        )
        flag_responses = [
            FeatureFlagWithOverridesResponse(
                id=item["flag"].id,
                key=item["flag"].key,
                name=item["flag"].name,
                description=item["flag"].description,
                default_enabled=item["flag"].default_enabled,
                created_time=(
                    item["flag"].created_time.isoformat()
                    if item["flag"].created_time
                    else ""
                ),
                updated_time=(
                    item["flag"].updated_time.isoformat()
                    if item["flag"].updated_time
                    else ""
                ),
                overrides=[
                    FeatureFlagOverrideSummary(
                        organization_id=o["organization_id"],
                        organization_name=o["organization_name"],
                        enabled=o["enabled"],
                    )
                    for o in item["overrides"]
                ],
            )
            for item in flags_with_overrides
        ]
        return FeatureFlagListResponse(
            items=flag_responses, total=total, limit=limit, offset=offset
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in list_feature_flags_endpoint: {e}\n{error_tb}"
        )
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.get("/{flag_id}", response_model=FeatureFlagResponse)
async def get_feature_flag_endpoint(
    flag_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a feature flag by ID (super admin only)."""
    try:
        flag = await get_feature_flag_by_id(session=session, flag_id=flag_id)
        if not flag:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feature flag not found",
                detail_code="feature_flag.not_found",
            )
        return FeatureFlagResponse(
            id=flag.id,
            key=flag.key,
            name=flag.name,
            description=flag.description,
            default_enabled=flag.default_enabled,
            created_time=flag.created_time.isoformat() if flag.created_time else "",
            updated_time=flag.updated_time.isoformat() if flag.updated_time else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in get_feature_flag_endpoint: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.put("/{flag_id}", response_model=UpdateFeatureFlagResponse)
async def update_feature_flag_endpoint(
    flag_id: str,
    request: UpdateFeatureFlagRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a feature flag (super admin only)."""
    try:
        flag = await update_feature_flag(
            session=session,
            flag_id=flag_id,
            data=request.model_dump(exclude_unset=True),
        )

        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="FeatureFlag",
            resource_id=str(flag.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            old_values={},
            new_values=request.model_dump(exclude_unset=True),
        )

        response = FeatureFlagResponse(
            id=flag.id,
            key=flag.key,
            name=flag.name,
            description=flag.description,
            default_enabled=flag.default_enabled,
            created_time=flag.created_time.isoformat() if flag.created_time else "",
            updated_time=flag.updated_time.isoformat() if flag.updated_time else "",
        )
        return UpdateFeatureFlagResponse(
            message="Feature flag updated successfully",
            message_code=get_response_code("feature_flag.updated"),
            flag=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in update_feature_flag_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.delete("/{flag_id}", response_model=DeleteFeatureFlagResponse)
async def delete_feature_flag_endpoint(
    flag_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Soft delete a feature flag (super admin only)."""
    try:
        flag = await delete_feature_flag(session=session, flag_id=flag_id)

        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="FeatureFlag",
            resource_id=str(flag.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"key": flag.key, "name": flag.name},
        )

        return DeleteFeatureFlagResponse(
            message="Feature flag deleted successfully",
            message_code=get_response_code("feature_flag.deleted"),
            flag_id=str(flag.id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in delete_feature_flag_endpoint: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.post(
    "/{flag_id}/overrides",
    response_model=CreateOverrideResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_override_endpoint(
    flag_id: str,
    request: CreateOverrideRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create or update an organization override for a feature flag (super admin only)."""
    try:
        override = await create_override(
            session=session,
            flag_id=flag_id,
            organization_id=str(request.organization_id),
            enabled=request.enabled,
        )

        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="FeatureFlagOverride",
            resource_id=str(override.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "feature_flag_id": flag_id,
                "organization_id": str(request.organization_id),
                "enabled": request.enabled,
            },
        )

        response = FeatureFlagOverrideResponse(
            id=override.id,
            feature_flag_id=override.feature_flag_id,
            organization_id=override.organization_id,
            enabled=override.enabled,
            created_time=(
                override.created_time.isoformat() if override.created_time else ""
            ),
            updated_time=(
                override.updated_time.isoformat() if override.updated_time else ""
            ),
        )
        return CreateOverrideResponse(
            message="Feature flag override created successfully",
            message_code=get_response_code("feature_flag_override.created"),
            override=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in create_override_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.delete(
    "/{flag_id}/overrides/{org_id}", response_model=DeleteOverrideResponse
)
async def delete_override_endpoint(
    flag_id: str,
    org_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete an organization override for a feature flag (super admin only)."""
    try:
        override = await delete_override(
            session=session, flag_id=flag_id, organization_id=org_id
        )

        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="FeatureFlagOverride",
            resource_id=str(override.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"feature_flag_id": flag_id, "organization_id": org_id},
        )

        return DeleteOverrideResponse(
            message="Feature flag override deleted successfully",
            message_code=get_response_code("feature_flag_override.deleted"),
            flag_id=flag_id,
            organization_id=org_id,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in delete_override_endpoint: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@admin_router.get(
    "/{flag_id}/overrides", response_model=FeatureFlagOverrideListResponse
)
async def list_overrides_endpoint(
    flag_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all organization overrides for a feature flag (super admin only)."""
    try:
        overrides, total = await get_overrides_for_flag(
            session=session, flag_id=flag_id, limit=limit, offset=offset
        )
        override_responses = [
            FeatureFlagOverrideResponse(
                id=override.id,
                feature_flag_id=override.feature_flag_id,
                organization_id=override.organization_id,
                enabled=override.enabled,
                created_time=(
                    override.created_time.isoformat() if override.created_time else ""
                ),
                updated_time=(
                    override.updated_time.isoformat() if override.updated_time else ""
                ),
            )
            for override in overrides
        ]
        return FeatureFlagOverrideListResponse(
            items=override_responses, total=total, limit=limit, offset=offset
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in list_overrides_endpoint: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@org_router.get("", response_model=ResolvedFeatureFlagsResponse)
async def get_resolved_flags_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get resolved enabled flags for current organization (uses caching)."""
    try:
        organization_id = current_user.organization_id

        # Try cache first
        cached_flags = await feature_flag_cache.get_org_feature_flags(organization_id)
        if cached_flags is not None:
            return ResolvedFeatureFlagsResponse(flags=cached_flags)

        # Cache miss - fetch from database
        flags = await get_resolved_flags_for_organization(
            session=session, organization_id=organization_id
        )

        # Cache for next time
        await feature_flag_cache.set_org_feature_flags(organization_id, flags)

        return ResolvedFeatureFlagsResponse(flags=flags)
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Unexpected error in get_resolved_flags_endpoint: {e}\n{error_tb}"
        )
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# Combine routers for export
router = APIRouter()
router.include_router(admin_router)
router.include_router(org_router)
