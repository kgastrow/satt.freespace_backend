"""
Organization SSO settings API endpoints.

Super admins can allow/disallow SSO per organization.
Organization admins can enable/configure SSO providers (if SSO is allowed).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.crud.organization import get_organization_by_id, get_organization_by_slug
from src.crud.organization_sso_settings import (
    create_organization_sso_settings,
    get_enabled_providers,
    get_organization_sso_settings,
    update_organization_sso_settings,
)
from src.models.audit_log import AuditAction
from src.serialisers.organization_sso_settings import (
    CreateOrganizationSSOSettingsRequest,
    EnabledProvidersResponse,
    OrganizationSSOSettingsResponse,
    SetSSOAllowedRequest,
    UpdateOrganizationSSOSettingsRequest,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(
    prefix="/organization-sso-settings", tags=["organization-sso-settings"]
)


def _build_response(settings) -> OrganizationSSOSettingsResponse:
    """Build response from settings model."""
    return OrganizationSSOSettingsResponse(
        id=settings.id,
        organization_id=settings.organization_id,
        sso_allowed=settings.sso_allowed,
        google_enabled=settings.google_enabled,
        google_client_id=settings.google_client_id,
        created_time=(
            settings.created_time.isoformat() if settings.created_time else None
        ),
        updated_time=(
            settings.updated_time.isoformat() if settings.updated_time else None
        ),
    )


@router.get("", response_model=OrganizationSSOSettingsResponse)
async def get_organization_sso_settings_endpoint(
    current_user: Annotated[CurrentUser, Depends(require_permission("sso:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get SSO settings for the current user's organization.

    Requires sso:read permission. Users with this permission can view SSO
    configuration to understand their login options.
    (client_secret is not included in response for security)

    Returns:
        OrganizationSSOSettingsResponse with SSO configuration
    """
    organization_id = current_user.organization_id

    settings = await get_organization_sso_settings(session, organization_id)

    if not settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO settings not found for this organization",
            detail_code="sso.settings_not_found",
        )

    return _build_response(settings)


@router.get("/enabled-providers", response_model=EnabledProvidersResponse)
async def get_enabled_providers_endpoint(
    org_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get list of enabled SSO providers for an organization.

    This endpoint is public and used by the login page to dynamically display SSO login buttons.
    Only returns providers if SSO is allowed AND the provider is enabled.

    For security, returns an empty list for non-existent organizations
    to prevent organization enumeration attacks.

    Args:
        org_slug: Organization slug to look up

    Returns:
        EnabledProvidersResponse with list of provider names (empty if org not found)
    """
    organization = await get_organization_by_slug(session, org_slug)

    # Return empty list for non-existent orgs to prevent enumeration
    if not organization:
        return EnabledProvidersResponse(providers=[])

    providers = await get_enabled_providers(session, str(organization.id))

    return EnabledProvidersResponse(providers=providers)


@router.post(
    "",
    response_model=OrganizationSSOSettingsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_organization_sso_settings_endpoint(
    request: CreateOrganizationSSOSettingsRequest,
    current_user: Annotated[CurrentUser, Depends(require_permission("sso:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Create SSO settings for an organization.

    Requires sso:write permission.
    Note: SSO will still need to be allowed by super admin before it can be used.

    Args:
        request: SSO settings data

    Returns:
        Created SSO settings
    """
    organization_id = current_user.organization_id

    try:
        settings = await create_organization_sso_settings(
            session, organization_id, request.model_dump()
        )

        # Audit log for SSO settings creation
        await audit_service.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.CREATE,
            resource_type="organization_sso_settings",
            resource_id=str(settings.id),
            actor_id=current_user.id,
            changes={
                "google_enabled": {"old": None, "new": settings.google_enabled},
                "google_client_id": {"old": None, "new": settings.google_client_id},
            },
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            impersonated_by=(
                current_user.impersonator_id if current_user.is_impersonating else None
            ),
        )

        return _build_response(settings)

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )


@router.put("", response_model=OrganizationSSOSettingsResponse)
async def update_organization_sso_settings_endpoint(
    request: UpdateOrganizationSSOSettingsRequest,
    current_user: Annotated[CurrentUser, Depends(require_permission("sso:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Update SSO settings for an organization.

    Requires sso:write permission.
    SSO must be allowed by super admin before configuration changes take effect.

    Args:
        request: SSO settings data to update

    Returns:
        Updated SSO settings
    """
    organization_id = current_user.organization_id

    # Get current settings to check if SSO is allowed
    settings = await get_organization_sso_settings(session, organization_id)

    if not settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO settings not found for this organization",
            detail_code="sso.settings_not_found",
        )

    # Store old values for audit logging
    old_values = {
        "google_enabled": settings.google_enabled,
        "google_client_id": settings.google_client_id,
    }

    # Super admins (is_admin=True) can always update settings.
    # Organization admins can only update when SSO is allowed for their organization.
    if not settings.sso_allowed and not current_user.is_admin:
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SSO is not allowed for this organization. Contact a super admin to enable SSO.",
            detail_code="common.forbidden",
        )

    try:
        settings = await update_organization_sso_settings(
            session, organization_id, request.model_dump(exclude_unset=True)
        )

        # Audit log for SSO settings update
        new_values = {
            "google_enabled": settings.google_enabled,
            "google_client_id": settings.google_client_id,
        }
        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="organization_sso_settings",
            resource_id=str(settings.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            impersonated_by=(
                current_user.impersonator_id if current_user.is_impersonating else None
            ),
        )

        return _build_response(settings)

    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )


# =============================================================================
# Super Admin Endpoints
# =============================================================================


@router.put(
    "/organization/{organization_id}/allow",
    response_model=OrganizationSSOSettingsResponse,
)
async def set_sso_allowed_endpoint(
    organization_id: str,
    request: SetSSOAllowedRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Set whether SSO is allowed for an organization.

    Super admin only. This is the master switch that controls whether
    organization admins can configure and use SSO.

    Args:
        organization_id: The organization UUID
        request: Contains sso_allowed boolean

    Returns:
        Updated SSO settings
    """
    # Verify organization exists
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    # Get or create SSO settings for the organization
    settings = await get_organization_sso_settings(session, organization_id)
    old_sso_allowed = settings.sso_allowed if settings else None

    if not settings:
        # Create settings with sso_allowed
        settings = await create_organization_sso_settings(
            session, organization_id, {"sso_allowed": request.sso_allowed}
        )

        # Audit log for SSO settings creation (super admin)
        await audit_service.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.CREATE,
            resource_type="organization_sso_settings",
            resource_id=str(settings.id),
            actor_id=current_user.id,
            changes={"sso_allowed": {"old": None, "new": request.sso_allowed}},
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )
    else:
        # Update sso_allowed
        settings = await update_organization_sso_settings(
            session, organization_id, {"sso_allowed": request.sso_allowed}
        )

        # Audit log for SSO allowed status change (super admin)
        await audit_service.log_update(
            session=session,
            organization_id=organization_id,
            resource_type="organization_sso_settings",
            resource_id=str(settings.id),
            old_values={"sso_allowed": old_sso_allowed},
            new_values={"sso_allowed": request.sso_allowed},
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

    return _build_response(settings)


@router.get(
    "/organization/{organization_id}", response_model=OrganizationSSOSettingsResponse
)
async def get_organization_sso_settings_by_id_endpoint(
    organization_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get SSO settings for a specific organization.

    Super admin only. Used for viewing SSO status of any organization.

    Args:
        organization_id: The organization UUID

    Returns:
        OrganizationSSOSettingsResponse or 404 if not configured
    """
    # Verify organization exists
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    settings = await get_organization_sso_settings(session, organization_id)

    if not settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SSO settings not found for this organization",
            detail_code="sso.settings_not_found",
        )

    return _build_response(settings)
