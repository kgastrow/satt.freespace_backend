"""
Organization Two-Factor Authentication Settings API endpoints.
Provides endpoints for managing organization-level 2FA settings and permissions.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.crud import organization_two_factor_settings as org_2fa_crud
from src.crud.organization import get_organization_by_id
from src.serialisers.two_factor import (
    GetOrganizationTwoFactorSettingsResponse,
    UpdateOrganizationTwoFactorAllowedRequest,
    UpdateOrganizationTwoFactorSettingsRequest,
)


router = APIRouter(
    prefix="/organization-two-factor-settings",
    tags=["organization-two-factor-settings"],
)


@router.get(
    "/",
    response_model=GetOrganizationTwoFactorSettingsResponse,
)
async def get_organization_two_factor_settings(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("two_factor:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get 2FA settings for the organization (requires two_factor:read permission)."""
    try:
        settings = await org_2fa_crud.get_by_organization_id(
            session, current_user.organization_id
        )
        # Auto-create default settings if they don't exist
        if not settings:
            settings = await org_2fa_crud.create_settings(
                session,
                {
                    "two_factor_allowed": False,
                    "two_factor_policy": "disabled",
                    "grace_period_days": 7,
                },
                current_user.organization_id,
            )
        return GetOrganizationTwoFactorSettingsResponse.model_validate(settings)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.put(
    "/",
    response_model=GetOrganizationTwoFactorSettingsResponse,
)
async def update_organization_two_factor_settings(
    request: UpdateOrganizationTwoFactorSettingsRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("two_factor:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update 2FA settings for the organization (requires two_factor:write permission)."""
    try:
        existing = await org_2fa_crud.get_by_organization_id(
            session, current_user.organization_id
        )
        if not existing:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="2FA settings not found. Contact super admin to enable 2FA.",
                detail_code="two_factor.settings_not_found",
            )

        if not existing.two_factor_allowed:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="2FA is not allowed for this organization. Contact super admin.",
                detail_code="two_factor.not_allowed",
            )

        settings = await org_2fa_crud.update_settings(
            session, request.model_dump(exclude_none=True), current_user.organization_id
        )
        return GetOrganizationTwoFactorSettingsResponse.model_validate(settings)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.put("/organization/{organization_id}/allow")
async def update_organization_two_factor_allowed(
    organization_id: str,
    request: UpdateOrganizationTwoFactorAllowedRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Super admin endpoint to allow/disallow 2FA for an organization."""
    # Validate UUID format
    try:
        UUID(organization_id)
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format",
            detail_code="organization.invalid_id",
        )

    # Verify organization exists before creating/updating settings
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    try:
        settings = await org_2fa_crud.update_allowed_by_super_admin(
            session, organization_id, request.two_factor_allowed
        )
        return GetOrganizationTwoFactorSettingsResponse.model_validate(settings)
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="two_factor.invalid_request",
        )


@router.get(
    "/organization/{organization_id}",
    response_model=GetOrganizationTwoFactorSettingsResponse,
)
async def get_organization_two_factor_settings_by_id(
    organization_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get 2FA settings for a specific organization.

    Super admin only. Used for viewing 2FA status of any organization.

    Args:
        organization_id: The organization UUID

    Returns:
        GetOrganizationTwoFactorSettingsResponse or 404 if not configured
    """
    # Validate UUID format
    try:
        UUID(organization_id)
    except ValueError:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid organization ID format",
            detail_code="organization.invalid_id",
        )

    # Verify organization exists
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    settings = await org_2fa_crud.get_by_organization_id(session, organization_id)

    if not settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="2FA settings not found for this organization",
            detail_code="two_factor.settings_not_found",
        )

    return GetOrganizationTwoFactorSettingsResponse.model_validate(settings)
