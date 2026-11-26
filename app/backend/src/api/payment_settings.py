"""
Organization payment settings API endpoints.

Super admins can allow/disallow payments per organization.
Organization admins can enable/configure payment providers (if payments are allowed).
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.crud.organization import get_organization_by_id
from src.crud.organization_payment_settings import (
    get_enabled_providers,
    get_or_create_payment_settings,
    get_payment_settings,
    set_payments_allowed,
    update_payment_settings,
)
from src.logger.logger import Logger
from src.serialisers.payment_settings import (
    EnabledProvidersResponse,
    PaymentSettingsResponse,
    ProviderCapabilitiesResponse,
    SetPaymentsAllowedRequest,
    UpdatePaymentSettingsRequest,
)
from src.services.payments import PaymentProviderFactory


router = APIRouter(prefix="/payment-settings", tags=["payment-settings"])


def _build_response(settings) -> PaymentSettingsResponse:
    """Build response from settings model."""
    return PaymentSettingsResponse(
        id=settings.id,
        organization_id=settings.organization_id,
        payments_allowed=settings.payments_allowed,
        default_provider=settings.default_provider,
        default_currency=settings.default_currency,
        supported_currencies=settings.supported_currencies,
        stripe_enabled=settings.stripe_enabled,
        stripe_connect_configured=bool(settings.stripe_connect_account_id),
        payfast_enabled=settings.payfast_enabled,
        paypal_enabled=settings.paypal_enabled,
        created_time=(
            settings.created_time.isoformat() if settings.created_time else None
        ),
        updated_time=(
            settings.updated_time.isoformat() if settings.updated_time else None
        ),
    )


@router.get("", response_model=PaymentSettingsResponse)
async def get_payment_settings_endpoint(
    current_user: Annotated[
        CurrentUser, Depends(require_permission("organization:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get payment settings for the current user's organization.

    Requires organization:read permission.
    Returns payment configuration (credentials are never exposed).
    """
    organization_id = current_user.organization_id

    settings = await get_or_create_payment_settings(session, organization_id)

    return _build_response(settings)


@router.put("", response_model=PaymentSettingsResponse)
async def update_payment_settings_endpoint(
    settings_request: UpdatePaymentSettingsRequest,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("organization:write"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    http_request: Request,
):
    """
    Update payment settings for an organization.

    Requires organization:write permission.
    Note: payments_allowed can only be changed by super admins.
    """
    organization_id = current_user.organization_id

    # Get or create settings
    settings = await get_or_create_payment_settings(session, organization_id)

    # Org admins cannot change payments_allowed - remove from request
    update_data = settings_request.model_dump(exclude_unset=True)
    if not current_user.is_admin:
        update_data.pop("payments_allowed", None)

    try:
        settings = await update_payment_settings(session, organization_id, update_data)

        return _build_response(settings)

    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error updating payment settings: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="payments.settings_update_failed",
        )


@router.get("/enabled-providers", response_model=EnabledProvidersResponse)
async def get_enabled_providers_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get list of enabled payment providers for the organization.

    This is the primary endpoint for frontends to know what
    payment options to display.
    """
    organization_id = current_user.organization_id

    providers = await get_enabled_providers(session, organization_id)

    settings = await get_payment_settings(session, organization_id)
    default_provider = settings.default_provider if settings else None

    # If no default set, use first enabled provider
    if not default_provider and providers:
        default_provider = providers[0]

    return EnabledProvidersResponse(
        providers=providers,
        default_provider=default_provider,
    )


@router.get(
    "/providers/{provider}/capabilities", response_model=ProviderCapabilitiesResponse
)
async def get_provider_capabilities(
    provider: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    http_request: Request,
):
    """
    Get capabilities for a specific payment provider.

    Useful for frontends to know what features are available
    (e.g., whether to show "Save card" checkbox).
    """
    try:
        capabilities = PaymentProviderFactory.get_provider_capabilities(provider)
        return ProviderCapabilitiesResponse(
            provider=provider,
            capabilities=capabilities.model_dump(),
        )
    except ValueError as e:
        error_tb = traceback.format_exc()
        Logger.error(
            f"Error getting provider capabilities for {provider}: {e}\n{error_tb}"
        )
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider not found: {provider}",
            detail_code="payments.provider_not_found",
        )


# =============================================================================
# Super Admin Endpoints
# =============================================================================


@router.put(
    "/organization/{organization_id}/payments-allowed",
    response_model=PaymentSettingsResponse,
)
async def set_payments_allowed_endpoint(
    organization_id: str,
    request: SetPaymentsAllowedRequest,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Enable/disable payments for an organization (super admin only).

    This is the master switch - if False, no payments can be processed.

    Args:
        organization_id: The organization UUID
        request: Contains allowed boolean

    Returns:
        Updated payment settings
    """
    # Verify organization exists
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    settings = await set_payments_allowed(session, organization_id, request.allowed)

    return _build_response(settings)


@router.get(
    "/organization/{organization_id}",
    response_model=PaymentSettingsResponse,
)
async def get_payment_settings_by_id_endpoint(
    organization_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get payment settings for a specific organization.

    Super admin only. Used for viewing payment status of any organization.

    Args:
        organization_id: The organization UUID

    Returns:
        PaymentSettingsResponse or 404 if not configured
    """
    # Verify organization exists
    organization = await get_organization_by_id(session, organization_id)
    if not organization:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
            detail_code="organization.not_found",
        )

    settings = await get_payment_settings(session, organization_id)

    if not settings:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment settings not found for this organization",
            detail_code="payments.settings_not_found",
        )

    return _build_response(settings)
