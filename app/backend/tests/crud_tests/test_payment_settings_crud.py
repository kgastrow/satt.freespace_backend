"""
CRUD tests for OrganizationPaymentSettings model.

Tests verify:
- Basic CRUD operations
- Two-tier permission system (payments_allowed + provider_enabled)
- Organization-based tenant isolation
- Provider enablement logic
"""

import pytest

from src.crud.organization_payment_settings import (
    create_payment_settings,
    get_enabled_providers,
    get_or_create_payment_settings,
    get_payment_settings,
    is_provider_enabled,
    set_payments_allowed,
    update_payment_settings,
)


# ─────────────────────────────────────────────────────────────
# Basic CRUD Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_payment_settings(async_session, test_organization):
    """Test creating organization payment settings."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "default_provider": "stripe",
            "default_currency": "USD",
            "supported_currencies": ["USD", "EUR"],
            "stripe_enabled": True,
        },
    )

    assert settings is not None
    assert settings.organization_id == test_organization.id
    assert settings.payments_allowed is True
    assert settings.default_provider == "stripe"
    assert settings.default_currency == "USD"
    assert settings.stripe_enabled is True


@pytest.mark.asyncio
async def test_create_payment_settings_defaults(async_session, test_organization):
    """Test creating payment settings with default values."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
    )

    assert settings is not None
    assert settings.payments_allowed is False
    assert settings.default_currency == "USD"
    assert settings.stripe_enabled is False
    assert settings.payfast_enabled is False
    assert settings.paypal_enabled is False


@pytest.mark.asyncio
async def test_create_payment_settings_already_exists(async_session, test_organization):
    """Test that creating duplicate settings raises error."""
    # Create first settings
    await create_payment_settings(async_session, str(test_organization.id))

    # Try to create again
    with pytest.raises(ValueError, match="Payment settings already exist"):
        await create_payment_settings(async_session, str(test_organization.id))


@pytest.mark.asyncio
async def test_get_payment_settings(async_session, payment_settings):
    """Test retrieving payment settings."""
    retrieved = await get_payment_settings(
        async_session,
        str(payment_settings.organization_id),
    )

    assert retrieved is not None
    assert retrieved.id == payment_settings.id
    assert retrieved.payments_allowed == payment_settings.payments_allowed


@pytest.mark.asyncio
async def test_get_payment_settings_not_found(async_session, test_organization):
    """Test retrieving non-existent settings returns None."""
    # No settings created
    retrieved = await get_payment_settings(
        async_session,
        str(test_organization.id),
    )

    assert retrieved is None


@pytest.mark.asyncio
async def test_update_payment_settings(async_session, payment_settings):
    """Test updating payment settings."""
    updated = await update_payment_settings(
        async_session,
        str(payment_settings.organization_id),
        {
            "default_provider": "payfast",
            "default_currency": "ZAR",
            "payfast_enabled": True,
        },
    )

    assert updated.default_provider == "payfast"
    assert updated.default_currency == "ZAR"
    assert updated.payfast_enabled is True


@pytest.mark.asyncio
async def test_update_payment_settings_not_found(async_session, test_organization):
    """Test updating non-existent settings raises error."""
    with pytest.raises(ValueError, match="Payment settings not found"):
        await update_payment_settings(
            async_session,
            str(test_organization.id),
            {"payments_allowed": True},
        )


@pytest.mark.asyncio
async def test_get_or_create_payment_settings_get(async_session, payment_settings):
    """Test get_or_create returns existing settings."""
    retrieved = await get_or_create_payment_settings(
        async_session,
        str(payment_settings.organization_id),
    )

    assert retrieved.id == payment_settings.id


@pytest.mark.asyncio
async def test_get_or_create_payment_settings_create(async_session, test_organization):
    """Test get_or_create creates new settings if not found."""
    settings = await get_or_create_payment_settings(
        async_session,
        str(test_organization.id),
    )

    assert settings is not None
    assert settings.organization_id == test_organization.id


# ─────────────────────────────────────────────────────────────
# Provider Enablement Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_enabled_providers_stripe_only(async_session, test_organization):
    """Test getting enabled providers when only Stripe is enabled."""
    # Create settings with Stripe enabled
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_123",
        },
    )

    providers = await get_enabled_providers(
        async_session,
        str(test_organization.id),
    )

    assert "stripe" in providers
    assert "payfast" not in providers
    assert "paypal" not in providers


@pytest.mark.asyncio
async def test_get_enabled_providers_multiple(async_session, test_organization):
    """Test getting enabled providers when multiple are enabled."""
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_123",
            "payfast_enabled": True,
            "payfast_merchant_id": "12345",
        },
    )

    providers = await get_enabled_providers(
        async_session,
        str(test_organization.id),
    )

    assert "stripe" in providers
    assert "payfast" in providers


@pytest.mark.asyncio
async def test_get_enabled_providers_payments_not_allowed(
    async_session, test_organization
):
    """Test that no providers are enabled if payments_allowed is False."""
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": False,  # Super admin hasn't allowed
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_123",
        },
    )

    providers = await get_enabled_providers(
        async_session,
        str(test_organization.id),
    )

    assert len(providers) == 0


@pytest.mark.asyncio
async def test_get_enabled_providers_no_settings(async_session, test_organization):
    """Test getting providers when no settings exist."""
    providers = await get_enabled_providers(
        async_session,
        str(test_organization.id),
    )

    assert len(providers) == 0


@pytest.mark.asyncio
async def test_is_provider_enabled_true(async_session, test_organization):
    """Test is_provider_enabled returns True for enabled provider."""
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_123",
        },
    )

    enabled = await is_provider_enabled(
        async_session,
        str(test_organization.id),
        "stripe",
    )

    assert enabled is True


@pytest.mark.asyncio
async def test_is_provider_enabled_false(async_session, test_organization):
    """Test is_provider_enabled returns False for disabled provider."""
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_secret_key": "sk_test_123",
            "payfast_enabled": False,
        },
    )

    enabled = await is_provider_enabled(
        async_session,
        str(test_organization.id),
        "payfast",
    )

    assert enabled is False


# ─────────────────────────────────────────────────────────────
# Super Admin Controls Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_payments_allowed_create(async_session, test_organization):
    """Test set_payments_allowed creates settings if not exist."""
    settings = await set_payments_allowed(
        async_session,
        str(test_organization.id),
        True,
    )

    assert settings is not None
    assert settings.payments_allowed is True


@pytest.mark.asyncio
async def test_set_payments_allowed_update(async_session, test_organization):
    """Test set_payments_allowed updates existing settings."""
    # Create settings first
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": False},
    )

    # Update via set_payments_allowed
    settings = await set_payments_allowed(
        async_session,
        str(test_organization.id),
        True,
    )

    assert settings.payments_allowed is True


@pytest.mark.asyncio
async def test_set_payments_allowed_disable(async_session, test_organization):
    """Test disabling payments for an organization."""
    # Create settings with payments enabled
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": True, "stripe_enabled": True},
    )

    # Disable payments
    settings = await set_payments_allowed(
        async_session,
        str(test_organization.id),
        False,
    )

    assert settings.payments_allowed is False

    # Verify no providers are available now
    providers = await get_enabled_providers(
        async_session,
        str(test_organization.id),
    )

    assert len(providers) == 0


# ─────────────────────────────────────────────────────────────
# Organization Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_settings_organization_isolation(
    async_session, test_organization, second_organization
):
    """Test that payment settings are isolated by organization."""
    # Create settings for first org
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": True, "default_provider": "stripe"},
    )

    # Create settings for second org
    await create_payment_settings(
        async_session,
        str(second_organization.id),
        {"payments_allowed": True, "default_provider": "payfast"},
    )

    # Retrieve and verify isolation
    retrieved1 = await get_payment_settings(
        async_session,
        str(test_organization.id),
    )
    retrieved2 = await get_payment_settings(
        async_session,
        str(second_organization.id),
    )

    assert retrieved1.default_provider == "stripe"
    assert retrieved2.default_provider == "payfast"


@pytest.mark.asyncio
async def test_update_does_not_affect_other_org(
    async_session, test_organization, second_organization
):
    """Test that updating one org's settings doesn't affect another."""
    # Create settings for both orgs
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": True, "default_currency": "USD"},
    )
    await create_payment_settings(
        async_session,
        str(second_organization.id),
        {"payments_allowed": True, "default_currency": "EUR"},
    )

    # Update first org
    await update_payment_settings(
        async_session,
        str(test_organization.id),
        {"default_currency": "GBP"},
    )

    # Verify second org unchanged
    settings2 = await get_payment_settings(
        async_session,
        str(second_organization.id),
    )

    assert settings2.default_currency == "EUR"


# ─────────────────────────────────────────────────────────────
# Provider Configuration Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stripe_configuration(async_session, test_organization):
    """Test Stripe-specific configuration fields."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_publishable_key": "pk_test_xxx",
            "stripe_secret_key": "sk_test_xxx",
            "stripe_webhook_secret": "whsec_xxx",
            "stripe_connect_account_id": "acct_xxx",
        },
    )

    assert settings.stripe_publishable_key == "pk_test_xxx"
    assert settings.stripe_secret_key == "sk_test_xxx"
    assert settings.stripe_webhook_secret == "whsec_xxx"
    assert settings.stripe_connect_account_id == "acct_xxx"


@pytest.mark.asyncio
async def test_payfast_configuration(async_session, test_organization):
    """Test PayFast-specific configuration fields."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "payfast_enabled": True,
            "payfast_merchant_id": "12345678",
            "payfast_merchant_key": "abcdefgh",
            "payfast_passphrase": "secret123",
            "payfast_sandbox": True,
        },
    )

    assert settings.payfast_merchant_id == "12345678"
    assert settings.payfast_merchant_key == "abcdefgh"
    assert settings.payfast_passphrase == "secret123"
    assert settings.payfast_sandbox is True


@pytest.mark.asyncio
async def test_paypal_configuration(async_session, test_organization):
    """Test PayPal-specific configuration fields."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "paypal_enabled": True,
            "paypal_client_id": "client_xxx",
            "paypal_client_secret": "secret_xxx",
            "paypal_sandbox": False,
        },
    )

    assert settings.paypal_client_id == "client_xxx"
    assert settings.paypal_client_secret == "secret_xxx"
    assert settings.paypal_sandbox is False


@pytest.mark.asyncio
async def test_supported_currencies(async_session, test_organization):
    """Test supported currencies configuration."""
    settings = await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "default_currency": "USD",
            "supported_currencies": ["USD", "EUR", "GBP", "ZAR"],
        },
    )

    assert settings.supported_currencies == ["USD", "EUR", "GBP", "ZAR"]


@pytest.mark.asyncio
async def test_update_provider_credentials(async_session, test_organization):
    """Test updating provider credentials."""
    # Create with initial credentials
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": True,
            "stripe_enabled": True,
            "stripe_secret_key": "sk_old_key",
        },
    )

    # Update credentials
    updated = await update_payment_settings(
        async_session,
        str(test_organization.id),
        {"stripe_secret_key": "sk_new_key"},
    )

    assert updated.stripe_secret_key == "sk_new_key"
