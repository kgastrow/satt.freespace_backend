"""
Pydantic serializers for OrganizationPaymentSettings.
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentSettingsResponse(BaseModel):
    """Response model for organization payment settings."""

    id: UUID
    organization_id: UUID
    payments_allowed: bool  # Master switch - controlled by super admin
    default_provider: Optional[str]
    default_currency: str
    supported_currencies: Optional[list[str]]

    # Provider enabled flags (credentials are never exposed)
    stripe_enabled: bool
    stripe_connect_configured: bool = False  # Has Connect account
    payfast_enabled: bool
    paypal_enabled: bool

    created_time: Optional[str]
    updated_time: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class UpdatePaymentSettingsRequest(BaseModel):
    """Request model for updating payment settings (org admin)."""

    default_provider: Optional[str] = Field(None, max_length=50)
    default_currency: Optional[str] = Field(None, min_length=3, max_length=3)
    supported_currencies: Optional[list[str]] = None

    # Provider toggles (credentials updated separately)
    stripe_enabled: Optional[bool] = None
    payfast_enabled: Optional[bool] = None
    paypal_enabled: Optional[bool] = None

    # Super admin only (silently ignored for org admins)
    payments_allowed: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")


class EnabledProvidersResponse(BaseModel):
    """Response model for list of enabled payment providers."""

    providers: list[str]
    default_provider: Optional[str]


class ProviderCapabilitiesResponse(BaseModel):
    """Response model for provider capabilities."""

    provider: str
    capabilities: dict  # ProviderCapabilities as dict


class SetPaymentsAllowedRequest(BaseModel):
    """Request model for super admin to set payments_allowed."""

    allowed: bool = Field(..., description="Allow payments for this organization")

    model_config = ConfigDict(extra="forbid")


class ProviderCredentialsRequest(BaseModel):
    """
    Request model for updating provider credentials.

    This is a sensitive operation - should require re-authentication
    or additional verification in production.
    """

    provider: str = Field(..., max_length=50)

    # Stripe credentials
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_connect_account_id: Optional[str] = None

    # PayFast credentials
    payfast_merchant_id: Optional[str] = None
    payfast_merchant_key: Optional[str] = None
    payfast_passphrase: Optional[str] = None
    payfast_sandbox: Optional[bool] = None

    # PayPal credentials
    paypal_client_id: Optional[str] = None
    paypal_client_secret: Optional[str] = None
    paypal_sandbox: Optional[bool] = None

    model_config = ConfigDict(extra="forbid")
