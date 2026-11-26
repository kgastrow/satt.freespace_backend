"""
API tests for payment settings endpoints.

Tests verify:
- Payment settings retrieval and update
- Enabled providers retrieval
- Super admin controls (payments_allowed)
- Authorization requirements
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Get Payment Settings Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_payment_settings(
    client: AsyncClient,
    test_jwt_token,
    payment_settings,
):
    """Test GET /api/v1/payment-settings returns settings."""
    # Mock permission check to grant organization:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["organization:read"])

        response = await client.get(
            "/api/v1/payment-settings",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["payments_allowed"] is True
    assert data["default_provider"] == "stripe"
    assert data["default_currency"] == "USD"
    assert data["stripe_enabled"] is True


@pytest.mark.asyncio
async def test_get_payment_settings_no_settings(
    client: AsyncClient,
    test_jwt_token,
):
    """Test getting settings when none exist returns defaults."""
    # Mock permission check to grant organization:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["organization:read"])

        response = await client.get(
            "/api/v1/payment-settings",
            headers={"Authorization": test_jwt_token},
        )

    # Should create default settings or return empty/default response
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_get_payment_settings_unauthenticated(client: AsyncClient):
    """Test getting settings requires authentication."""
    response = await client.get("/api/v1/payment-settings")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Update Payment Settings Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_payment_settings(
    client: AsyncClient,
    admin_token,
    admin_with_org_permission,
    test_organization,
    payment_settings,
    async_session,
):
    """Test PUT /api/v1/payment-settings updates settings."""
    response = await client.put(
        "/api/v1/payment-settings",
        json={
            "default_currency": "EUR",
            "stripe_enabled": True,
            "payfast_enabled": True,
        },
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["default_currency"] == "EUR"
    assert data["payfast_enabled"] is True


@pytest.mark.asyncio
async def test_update_payment_settings_provider_config(
    client: AsyncClient,
    admin_token,
    admin_with_org_permission,
    payment_settings,
):
    """Test updating provider enable flags."""
    response = await client.put(
        "/api/v1/payment-settings",
        json={
            "stripe_enabled": True,
            "payfast_enabled": True,
            "paypal_enabled": False,
            "default_provider": "stripe",
        },
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stripe_enabled"] is True
    assert data["payfast_enabled"] is True
    assert data["paypal_enabled"] is False
    assert data["default_provider"] == "stripe"


@pytest.mark.asyncio
async def test_update_payment_settings_unauthenticated(client: AsyncClient):
    """Test updating settings requires authentication."""
    response = await client.put(
        "/api/v1/payment-settings",
        json={"default_currency": "EUR"},
    )

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Get Enabled Providers Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_enabled_providers(
    client: AsyncClient,
    test_jwt_token,
    payment_settings,
):
    """Test GET /api/v1/payment-settings/enabled-providers returns list."""
    response = await client.get(
        "/api/v1/payment-settings/enabled-providers",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "providers" in data
    assert "stripe" in data["providers"]


@pytest.mark.asyncio
async def test_get_enabled_providers_none_enabled(
    client: AsyncClient,
    test_jwt_token,
    async_session,
    test_organization,
):
    """Test getting providers when none enabled returns empty list."""
    from src.crud.organization_payment_settings import create_payment_settings

    # Create settings with no providers enabled
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {
            "payments_allowed": False,
            "stripe_enabled": False,
            "payfast_enabled": False,
            "paypal_enabled": False,
        },
    )

    response = await client.get(
        "/api/v1/payment-settings/enabled-providers",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["providers"] == []


@pytest.mark.asyncio
async def test_get_enabled_providers_unauthenticated(client: AsyncClient):
    """Test getting providers requires authentication."""
    response = await client.get("/api/v1/payment-settings/enabled-providers")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Super Admin Controls Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_payments_allowed_super_admin(
    client: AsyncClient,
    test_super_admin_token,
    test_organization,
    async_session,
):
    """Test super admin can set payments_allowed flag."""
    from src.crud.organization_payment_settings import create_payment_settings

    # Create settings first
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": False},
    )

    response = await client.put(
        f"/api/v1/payment-settings/organization/{test_organization.id}/payments-allowed",
        json={"allowed": True},
        headers={"Authorization": test_super_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["payments_allowed"] is True


@pytest.mark.asyncio
async def test_set_payments_allowed_non_super_admin(
    client: AsyncClient,
    admin_token,
    test_organization,
    payment_settings,
):
    """Test non-super-admin cannot set payments_allowed flag."""
    response = await client.put(
        f"/api/v1/payment-settings/organization/{test_organization.id}/payments-allowed",
        json={"allowed": False},
        headers={"Authorization": admin_token},
    )

    # Should be forbidden for non-super-admin
    assert response.status_code in [403, 401]


@pytest.mark.asyncio
async def test_set_payments_allowed_unauthenticated(
    client: AsyncClient,
    test_organization,
):
    """Test setting payments_allowed requires authentication."""
    response = await client.put(
        f"/api/v1/payment-settings/organization/{test_organization.id}/payments-allowed",
        json={"allowed": True},
    )

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Organization Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_settings_isolation(
    client: AsyncClient,
    test_jwt_token,
    test_organization,
    second_organization,
    async_session,
):
    """Test that payment settings are isolated by organization."""
    from src.crud.organization_payment_settings import create_payment_settings

    # Create settings for test_organization
    await create_payment_settings(
        async_session,
        str(test_organization.id),
        {"payments_allowed": True, "default_provider": "stripe"},
    )

    # Create different settings for second_organization
    await create_payment_settings(
        async_session,
        str(second_organization.id),
        {"payments_allowed": True, "default_provider": "payfast"},
    )

    # Mock permission check to grant organization:read
    with patch("src.crud.role_permission.cache_service") as mock_cache:
        mock_cache.get_user_permissions = AsyncMock(return_value=["organization:read"])

        # Get settings with first org token
        response = await client.get(
            "/api/v1/payment-settings",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["default_provider"] == "stripe"  # Should be test_org's settings


# ─────────────────────────────────────────────────────────────
# Validation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_settings_invalid_currency(
    client: AsyncClient,
    admin_token,
    admin_with_org_permission,
    payment_settings,
):
    """Test updating with invalid currency format."""
    response = await client.put(
        "/api/v1/payment-settings",
        json={"default_currency": "INVALID"},  # Too long
        headers={"Authorization": admin_token},
    )

    # Should be rejected (either 400 or 422)
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_update_settings_supported_currencies(
    client: AsyncClient,
    admin_token,
    admin_with_org_permission,
    payment_settings,
):
    """Test updating supported currencies list."""
    response = await client.put(
        "/api/v1/payment-settings",
        json={"supported_currencies": ["USD", "EUR", "GBP", "ZAR"]},
        headers={"Authorization": admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert set(data["supported_currencies"]) == {"USD", "EUR", "GBP", "ZAR"}
