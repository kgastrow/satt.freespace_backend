"""
CRUD operations for OrganizationPaymentSettings model.

Each organization has exactly one payment settings record.

CRITICAL: All functions filter by organization_id to ensure tenant isolation.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings as app_settings
from src.models.organization_payment_settings import OrganizationPaymentSettings


async def get_payment_settings(
    session: AsyncSession,
    organization_id: str,
) -> Optional[OrganizationPaymentSettings]:
    """
    Get organization payment settings.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationPaymentSettings or None if not found
    """
    org_uuid = UUID(organization_id)

    result = await session.execute(
        select(OrganizationPaymentSettings).where(
            OrganizationPaymentSettings.organization_id == org_uuid,
            OrganizationPaymentSettings.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_payment_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: Optional[dict[str, Any]] = None,
) -> OrganizationPaymentSettings:
    """
    Create organization payment settings.

    CRITICAL: Always associates with organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Payment settings data (optional)

    Returns:
        The created OrganizationPaymentSettings

    Raises:
        ValueError: If settings already exist for this organization
    """
    org_uuid = UUID(organization_id)
    settings_data = settings_data or {}

    # Check if settings already exist
    existing = await get_payment_settings(session, organization_id)
    if existing:
        raise ValueError(
            f"Payment settings already exist for organization {organization_id}"
        )

    # Create new settings
    payment_settings = OrganizationPaymentSettings(
        organization_id=org_uuid,
        payments_allowed=settings_data.get("payments_allowed", False),
        default_provider=settings_data.get("default_provider"),
        default_currency=settings_data.get("default_currency", "USD"),
        supported_currencies=settings_data.get("supported_currencies"),
        # Stripe
        stripe_enabled=settings_data.get("stripe_enabled", False),
        stripe_connect_account_id=settings_data.get("stripe_connect_account_id"),
        stripe_publishable_key=settings_data.get("stripe_publishable_key"),
        stripe_secret_key=settings_data.get("stripe_secret_key"),
        stripe_webhook_secret=settings_data.get("stripe_webhook_secret"),
        # PayFast
        payfast_enabled=settings_data.get("payfast_enabled", False),
        payfast_merchant_id=settings_data.get("payfast_merchant_id"),
        payfast_merchant_key=settings_data.get("payfast_merchant_key"),
        payfast_passphrase=settings_data.get("payfast_passphrase"),
        payfast_sandbox=settings_data.get("payfast_sandbox", True),
        # PayPal
        paypal_enabled=settings_data.get("paypal_enabled", False),
        paypal_client_id=settings_data.get("paypal_client_id"),
        paypal_client_secret=settings_data.get("paypal_client_secret"),
        paypal_sandbox=settings_data.get("paypal_sandbox", True),
    )

    session.add(payment_settings)
    try:
        await session.commit()
        await session.refresh(payment_settings)
    except Exception as e:
        await session.rollback()
        raise e

    return payment_settings


async def update_payment_settings(
    session: AsyncSession,
    organization_id: str,
    settings_data: dict[str, Any],
) -> OrganizationPaymentSettings:
    """
    Update organization payment settings.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        settings_data: Fields to update (all optional)

    Returns:
        The updated OrganizationPaymentSettings

    Raises:
        ValueError: If settings don't exist for this organization
    """
    # Get existing settings
    payment_settings = await get_payment_settings(session, organization_id)

    if not payment_settings:
        raise ValueError(
            f"Payment settings not found for organization {organization_id}"
        )

    # Update allowed fields
    updatable_fields = [
        "payments_allowed",
        "default_provider",
        "default_currency",
        "supported_currencies",
        # Stripe
        "stripe_enabled",
        "stripe_connect_account_id",
        "stripe_publishable_key",
        "stripe_secret_key",
        "stripe_webhook_secret",
        # PayFast
        "payfast_enabled",
        "payfast_merchant_id",
        "payfast_merchant_key",
        "payfast_passphrase",
        "payfast_sandbox",
        # PayPal
        "paypal_enabled",
        "paypal_client_id",
        "paypal_client_secret",
        "paypal_sandbox",
    ]

    for field in updatable_fields:
        if field in settings_data:
            setattr(payment_settings, field, settings_data[field])

    try:
        await session.commit()
        await session.refresh(payment_settings)
    except Exception as e:
        await session.rollback()
        raise e

    return payment_settings


async def get_or_create_payment_settings(
    session: AsyncSession,
    organization_id: str,
) -> OrganizationPaymentSettings:
    """
    Get existing payment settings or create default ones.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        The OrganizationPaymentSettings (existing or newly created)
    """
    payment_settings = await get_payment_settings(session, organization_id)

    if not payment_settings:
        payment_settings = await create_payment_settings(session, organization_id)

    return payment_settings


async def get_enabled_providers(
    session: AsyncSession,
    organization_id: str,
) -> list[str]:
    """
    Get list of enabled payment providers for an organization.

    Only returns providers if:
    1. payments_allowed is True (super admin)
    2. The specific provider is enabled (org admin)
    3. The provider is configured at system level

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string

    Returns:
        List of enabled provider names (e.g., ['stripe', 'payfast'])
    """
    payment_settings = await get_payment_settings(session, organization_id)

    if not payment_settings:
        return []

    # Payments must be allowed by super admin
    if not payment_settings.payments_allowed:
        return []

    enabled_providers = []

    # Check each provider (system config + org settings)
    if payment_settings.stripe_enabled and (
        app_settings.STRIPE_ENABLED or payment_settings.stripe_secret_key
    ):
        enabled_providers.append("stripe")

    if payment_settings.payfast_enabled and (
        app_settings.PAYFAST_ENABLED or payment_settings.payfast_merchant_id
    ):
        enabled_providers.append("payfast")

    if payment_settings.paypal_enabled and (
        app_settings.PAYPAL_ENABLED or payment_settings.paypal_client_id
    ):
        enabled_providers.append("paypal")

    return enabled_providers


async def is_provider_enabled(
    session: AsyncSession,
    organization_id: str,
    provider: str,
) -> bool:
    """
    Check if a specific provider is enabled for an organization.

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        provider: Provider name (e.g., 'stripe', 'payfast')

    Returns:
        True if provider is enabled, False otherwise
    """
    enabled_providers = await get_enabled_providers(session, organization_id)
    return provider in enabled_providers


async def set_payments_allowed(
    session: AsyncSession,
    organization_id: str,
    allowed: bool,
) -> OrganizationPaymentSettings:
    """
    Set the payments_allowed flag for an organization (super admin only).

    CRITICAL: Always filters by organization_id for tenant isolation.

    Args:
        session: Database session
        organization_id: Organization UUID string
        allowed: Whether payments should be allowed

    Returns:
        The updated OrganizationPaymentSettings
    """
    payment_settings = await get_payment_settings(session, organization_id)

    if not payment_settings:
        # Create settings if they don't exist
        payment_settings = await create_payment_settings(
            session, organization_id, {"payments_allowed": allowed}
        )
    else:
        payment_settings.payments_allowed = allowed
        try:
            await session.commit()
            await session.refresh(payment_settings)
        except Exception as e:
            await session.rollback()
            raise e

    return payment_settings
