"""
API tests for payment endpoints.

Tests verify:
- Checkout session creation
- Payment retrieval and listing
- Refund processing
- Authentication requirements
- Organization isolation
"""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
import pytest

from src.services.payments.base import (
    CheckoutSession,
    ProviderCapabilities,
    RefundResult,
)


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_provider():
    """Create a mock payment provider for API tests."""
    from unittest.mock import MagicMock

    provider = MagicMock()
    provider.provider_name = "stripe"
    provider.capabilities = ProviderCapabilities(
        supports_checkout=True,
        supports_subscriptions=True,
        supports_refund=True,
        supports_partial_refund=True,
        supports_webhooks=True,
        supported_currencies=["USD", "EUR", "GBP"],
        supported_payment_methods=["card"],
    )
    return provider


# ─────────────────────────────────────────────────────────────
# Checkout Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkout_session(
    client: AsyncClient,
    test_jwt_token,
    async_session,
    payment_settings,
    mock_provider,
):
    """Test POST /api/v1/payments/checkout creates checkout session."""
    mock_checkout = CheckoutSession(
        session_id="cs_api_test_123",
        checkout_url="https://checkout.stripe.com/pay/cs_api_test_123",
        expires_at="2024-12-31T23:59:59Z",
    )
    mock_provider.create_checkout_session = AsyncMock(return_value=mock_checkout)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        response = await client.post(
            "/api/v1/payments/checkout",
            json={
                "amount_cents": 10000,
                "currency": "USD",
                "description": "Test API checkout",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
            },
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["checkout_url"] == "https://checkout.stripe.com/pay/cs_api_test_123"
    assert data["payment_id"] is not None


@pytest.mark.asyncio
async def test_create_checkout_session_with_metadata(
    client: AsyncClient,
    test_jwt_token,
    payment_settings,
    mock_provider,
):
    """Test checkout session with custom metadata."""
    mock_checkout = CheckoutSession(
        session_id="cs_meta_test",
        checkout_url="https://checkout.stripe.com/pay/cs_meta_test",
        expires_at="2024-12-31T23:59:59Z",
    )
    mock_provider.create_checkout_session = AsyncMock(return_value=mock_checkout)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        response = await client.post(
            "/api/v1/payments/checkout",
            json={
                "amount_cents": 5000,
                "currency": "USD",
                "description": "Test with metadata",
                "success_url": "https://example.com/success",
                "cancel_url": "https://example.com/cancel",
                "metadata": {"order_id": "order_123", "item": "premium_plan"},
            },
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_checkout_session_unauthenticated(client: AsyncClient):
    """Test checkout requires authentication."""
    response = await client.post(
        "/api/v1/payments/checkout",
        json={
            "amount_cents": 10000,
            "currency": "USD",
            "description": "Test",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_checkout_session_invalid_data(
    client: AsyncClient,
    test_jwt_token,
):
    """Test checkout with invalid data returns 422."""
    response = await client.post(
        "/api/v1/payments/checkout",
        json={
            "amount_cents": -100,  # Invalid negative amount
            "currency": "USD",
            "description": "Test",
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        },
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────
# List Payments Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_payments(
    client: AsyncClient,
    test_jwt_token,
    test_payment,
):
    """Test GET /api/v1/payments returns payment list."""
    response = await client.get(
        "/api/v1/payments",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_list_payments_with_status_filter(
    client: AsyncClient,
    test_jwt_token,
    test_payment,
):
    """Test listing payments with status filter."""
    response = await client.get(
        "/api/v1/payments?status_filter=succeeded",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    for item in data["items"]:
        assert item["status"] == "succeeded"


@pytest.mark.asyncio
async def test_list_payments_pagination(
    client: AsyncClient,
    test_jwt_token,
    test_payment,
):
    """Test payment list pagination."""
    response = await client.get(
        "/api/v1/payments?limit=10&offset=0",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_list_payments_unauthenticated(client: AsyncClient):
    """Test listing payments requires authentication."""
    response = await client.get("/api/v1/payments")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Get Payment Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_payment(
    client: AsyncClient,
    test_jwt_token,
    test_payment,
):
    """Test GET /api/v1/payments/{id} returns payment details."""
    response = await client.get(
        f"/api/v1/payments/{test_payment.id}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_payment.id)
    assert data["provider"] == "stripe"
    assert data["amount_cents"] == 10000
    assert data["currency"] == "USD"


@pytest.mark.asyncio
async def test_get_payment_not_found(
    client: AsyncClient,
    test_jwt_token,
):
    """Test getting non-existent payment returns 404."""
    from uuid import uuid4

    response = await client.get(
        f"/api/v1/payments/{uuid4()}",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_payment_unauthenticated(client: AsyncClient, test_payment):
    """Test getting payment requires authentication."""
    response = await client.get(f"/api/v1/payments/{test_payment.id}")

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Refund Endpoint Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_payment_full(
    client: AsyncClient,
    test_admin_token,
    test_organization,
    test_user,
    payment_settings,
    payment_customer,
    mock_provider,
    async_session,
):
    """Test POST /api/v1/payments/{id}/refund for full refund."""
    from src.crud.payment import create_payment

    # Create a succeeded payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_api_refund_full",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    mock_refund = RefundResult(
        success=True,
        refund_reference="re_api_123",
        amount_cents=5000,
        status="succeeded",
    )
    mock_provider.refund_payment = AsyncMock(return_value=mock_refund)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = await client.post(
            f"/api/v1/payments/{payment.id}/refund",
            json={"reason": "Customer requested refund"},
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["amount_cents"] == 5000


@pytest.mark.asyncio
async def test_refund_payment_partial(
    client: AsyncClient,
    test_admin_token,
    test_organization,
    test_user,
    payment_settings,
    mock_provider,
    async_session,
):
    """Test partial refund."""
    from src.crud.payment import create_payment

    # Create a succeeded payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_api_refund_partial",
            "amount_cents": 10000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    mock_refund = RefundResult(
        success=True,
        refund_reference="re_api_partial",
        amount_cents=3000,
        status="succeeded",
    )
    mock_provider.refund_payment = AsyncMock(return_value=mock_refund)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = await client.post(
            f"/api/v1/payments/{payment.id}/refund",
            json={"amount_cents": 3000, "reason": "Partial refund"},
            headers={"Authorization": test_admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["amount_cents"] == 3000
    assert data["new_status"] == "partially_refunded"


@pytest.mark.asyncio
async def test_refund_payment_not_found(
    client: AsyncClient,
    test_admin_token,
):
    """Test refunding non-existent payment returns 400."""
    from uuid import uuid4

    response = await client.post(
        f"/api/v1/payments/{uuid4()}/refund",
        json={},
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_refund_payment_unauthenticated(client: AsyncClient, test_payment):
    """Test refunding requires authentication."""
    response = await client.post(
        f"/api/v1/payments/{test_payment.id}/refund",
        json={},
    )

    assert response.status_code == 401


# ─────────────────────────────────────────────────────────────
# Organization Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_get_payment_from_other_org(
    client: AsyncClient,
    test_jwt_token,
    second_organization,
    second_org_user,
    async_session,
):
    """Test user cannot access payments from other organization."""
    from src.crud.payment import create_payment
    from src.models.payment_customer import PaymentCustomer

    # Create customer in second org
    customer = PaymentCustomer(
        organization_id=second_organization.id,
        user_id=second_org_user.id,
        provider="stripe",
        provider_customer_id="cus_other_org",
        email=second_org_user.email,
    )
    async_session.add(customer)
    await async_session.commit()

    # Create payment in second org
    payment = await create_payment(
        async_session,
        str(second_organization.id),
        {
            "user_id": str(second_org_user.id),
            "provider": "stripe",
            "provider_reference": "pi_other_org",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # Try to get with first org token
    response = await client.get(
        f"/api/v1/payments/{payment.id}",
        headers={"Authorization": test_jwt_token},  # Token for test_organization
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_payments_only_shows_org_payments(
    client: AsyncClient,
    test_jwt_token,
    test_organization,
    test_user,
    second_organization,
    second_org_user,
    async_session,
):
    """Test listing payments only returns payments from user's organization."""
    from src.crud.payment import create_payment
    from src.models.payment_customer import PaymentCustomer

    # Create customer and payment in test_organization
    customer1 = PaymentCustomer(
        organization_id=test_organization.id,
        user_id=test_user.id,
        provider="stripe",
        provider_customer_id="cus_org1_iso",
        email=test_user.email,
    )
    async_session.add(customer1)
    await async_session.commit()

    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_org1_iso",
            "amount_cents": 1000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # Create customer and payment in second_organization
    customer2 = PaymentCustomer(
        organization_id=second_organization.id,
        user_id=second_org_user.id,
        provider="stripe",
        provider_customer_id="cus_org2_iso",
        email=second_org_user.email,
    )
    async_session.add(customer2)
    await async_session.commit()

    await create_payment(
        async_session,
        str(second_organization.id),
        {
            "user_id": str(second_org_user.id),
            "provider": "stripe",
            "provider_reference": "pi_org2_iso",
            "amount_cents": 2000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # List payments with first org token
    response = await client.get(
        "/api/v1/payments",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()

    # All payments should belong to test_organization
    for item in data["items"]:
        # Verify we can get each payment (implies same org)
        get_response = await client.get(
            f"/api/v1/payments/{item['id']}",
            headers={"Authorization": test_jwt_token},
        )
        assert get_response.status_code == 200
