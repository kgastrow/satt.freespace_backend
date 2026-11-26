"""
API tests for payment methods endpoints.

Tests verify:
- Listing saved payment methods
- Deleting payment methods
- Setting default payment method
- Authorization requirements
- Organization isolation
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# List Payment Methods Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_payment_methods(
    client: AsyncClient,
    test_jwt_token,
    saved_payment_method,
):
    """Test GET /api/v1/payment-methods returns user's payment methods."""
    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert len(data["items"]) >= 1

    method = data["items"][0]
    assert method["type"] == "card"
    assert method["last_four"] == "4242"
    assert method["brand"] == "visa"


@pytest.mark.asyncio
async def test_list_payment_methods_empty(
    client: AsyncClient,
    test_jwt_token,
):
    """Test listing payment methods when user has none."""
    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    # May be empty or have fixtures


@pytest.mark.asyncio
async def test_list_payment_methods_shows_default(
    client: AsyncClient,
    test_jwt_token,
    payment_customer,
    async_session,
    test_organization,
):
    """Test that default payment method is indicated."""
    from src.crud.payment import create_saved_payment_method

    # Create a non-default method
    await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_list_default_test",
            "type": "card",
            "last_four": "1111",
            "brand": "mastercard",
            "is_default": False,
        },
    )

    # Create a default method
    await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_list_default_actual",
            "type": "card",
            "last_four": "2222",
            "brand": "visa",
            "is_default": True,
        },
    )

    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()

    default_methods = [m for m in data["items"] if m.get("is_default")]
    assert len(default_methods) >= 1


@pytest.mark.asyncio
async def test_list_payment_methods_unauthenticated(client: AsyncClient):
    """Test listing payment methods requires authentication."""
    response = await client.get("/api/v1/payment-methods")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Delete Payment Method Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_payment_method(
    client: AsyncClient,
    test_jwt_token,
    payment_customer,
    payment_settings,
    async_session,
    test_organization,
):
    """Test DELETE /api/v1/payment-methods/{id} removes payment method."""
    from src.crud.payment import create_saved_payment_method

    # Create a payment method to delete
    method = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_to_delete_api",
            "type": "card",
            "last_four": "9999",
        },
    )

    # Mock provider detachment
    mock_provider = MagicMock()
    mock_provider.detach_payment_method = AsyncMock()

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = await client.delete(
            f"/api/v1/payment-methods/{method.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_payment_method_not_found(
    client: AsyncClient,
    test_jwt_token,
):
    """Test deleting non-existent payment method returns 404."""
    response = await client.delete(
        f"/api/v1/payment-methods/{uuid4()}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_payment_method_other_user(
    client: AsyncClient,
    test_jwt_token,
    second_organization,
    second_org_user,
    async_session,
):
    """Test user cannot delete another user's payment method."""
    from src.models.payment_customer import PaymentCustomer, SavedPaymentMethod

    # Create customer and method for second user
    customer = PaymentCustomer(
        organization_id=second_organization.id,
        user_id=second_org_user.id,
        provider="stripe",
        provider_customer_id="cus_other_user",
        email=second_org_user.email,
    )
    async_session.add(customer)
    await async_session.commit()
    await async_session.refresh(customer)

    method = SavedPaymentMethod(
        organization_id=second_organization.id,
        customer_id=customer.id,
        provider="stripe",
        provider_payment_method_id="pm_other_user",
        type="card",
    )
    async_session.add(method)
    await async_session.commit()
    await async_session.refresh(method)

    # Try to delete with test_user's token
    response = await client.delete(
        f"/api/v1/payment-methods/{method.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_payment_method_unauthenticated(client: AsyncClient):
    """Test deleting payment method requires authentication."""
    response = await client.delete(f"/api/v1/payment-methods/{uuid4()}")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Set Default Payment Method Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_set_default_payment_method(
    client: AsyncClient,
    test_jwt_token,
    payment_customer,
    async_session,
    test_organization,
):
    """Test POST /api/v1/payment-methods/{id}/default sets as default."""
    from src.crud.payment import create_saved_payment_method

    # Create two payment methods
    await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_set_default_1",
            "type": "card",
            "is_default": True,
        },
    )

    method2 = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_set_default_2",
            "type": "card",
            "is_default": False,
        },
    )

    # Set method2 as default
    response = await client.post(
        f"/api/v1/payment-methods/{method2.id}/default",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_set_default_payment_method_not_found(
    client: AsyncClient,
    test_jwt_token,
):
    """Test setting default for non-existent method returns 404."""
    response = await client.post(
        f"/api/v1/payment-methods/{uuid4()}/default",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_default_payment_method_unauthenticated(client: AsyncClient):
    """Test setting default requires authentication."""
    response = await client.post(f"/api/v1/payment-methods/{uuid4()}/default")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Organization Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_methods_organization_isolation(
    client: AsyncClient,
    test_jwt_token,
    test_organization,
    test_user,
    second_organization,
    second_org_user,
    async_session,
):
    """Test that payment methods are isolated by organization."""
    from src.models.payment_customer import PaymentCustomer, SavedPaymentMethod

    # Create customer and method in test_organization
    customer1 = PaymentCustomer(
        organization_id=test_organization.id,
        user_id=test_user.id,
        provider="stripe",
        provider_customer_id="cus_org1_iso_pm",
        email=test_user.email,
    )
    async_session.add(customer1)
    await async_session.commit()
    await async_session.refresh(customer1)

    method1 = SavedPaymentMethod(
        organization_id=test_organization.id,
        customer_id=customer1.id,
        provider="stripe",
        provider_payment_method_id="pm_org1_iso",
        type="card",
        last_four="1111",
    )
    async_session.add(method1)
    await async_session.commit()

    # Create customer and method in second_organization
    customer2 = PaymentCustomer(
        organization_id=second_organization.id,
        user_id=second_org_user.id,
        provider="stripe",
        provider_customer_id="cus_org2_iso_pm",
        email=second_org_user.email,
    )
    async_session.add(customer2)
    await async_session.commit()
    await async_session.refresh(customer2)

    method2 = SavedPaymentMethod(
        organization_id=second_organization.id,
        customer_id=customer2.id,
        provider="stripe",
        provider_payment_method_id="pm_org2_iso",
        type="card",
        last_four="2222",
    )
    async_session.add(method2)
    await async_session.commit()

    # List methods with first org token
    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()

    # Should only see org1 methods
    for item in data["items"]:
        if item.get("last_four"):
            assert item["last_four"] != "2222"  # org2 method


# ─────────────────────────────────────────────────────────────
# Card Details Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payment_method_card_details(
    client: AsyncClient,
    test_jwt_token,
    saved_payment_method,
):
    """Test that card details are returned correctly."""
    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()

    # Find the saved_payment_method fixture
    methods = data["items"]
    assert len(methods) >= 1

    card = methods[0]
    assert card["type"] == "card"
    assert card["last_four"] == "4242"
    assert card["brand"] == "visa"
    assert card["exp_month"] == 12
    assert card["exp_year"] == 2030
    assert card["is_expired"] is False


@pytest.mark.asyncio
async def test_payment_method_expired_flag(
    client: AsyncClient,
    test_jwt_token,
    payment_customer,
    async_session,
    test_organization,
):
    """Test that expired payment methods are flagged."""
    from src.crud.payment import create_saved_payment_method

    # Create an expired card
    await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_expired",
            "type": "card",
            "last_four": "0000",
            "exp_month": 1,
            "exp_year": 2020,
            "is_expired": True,
        },
    )

    response = await client.get(
        "/api/v1/payment-methods",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()

    expired_methods = [m for m in data["items"] if m.get("is_expired")]
    assert len(expired_methods) >= 1
