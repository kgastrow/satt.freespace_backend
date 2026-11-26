"""
Service tests for PaymentService.

Tests verify:
- Checkout session creation
- Payment retrieval and listing
- Refund processing
- Webhook event processing
- Payment method management

Uses mocked payment providers to test service logic without external calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.crud.payment import create_payment, get_payment
from src.services.payments.base import (
    CheckoutSession,
    NormalizedEventType,
    PaymentStatus,
    ProviderCapabilities,
    RefundResult,
    WebhookEvent,
)
from src.services.payments.service import PaymentService


# ─────────────────────────────────────────────────────────────
# Fixtures for Mocked Providers
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_provider():
    """Create a mock payment provider."""
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


@pytest.fixture
def mock_checkout_session():
    """Create a mock checkout session result."""
    return CheckoutSession(
        session_id="cs_test_123",
        checkout_url="https://checkout.stripe.com/pay/cs_test_123",
        expires_at="2024-12-31T23:59:59Z",
    )


@pytest.fixture
def mock_refund_result():
    """Create a mock refund result."""
    return RefundResult(
        success=True,
        refund_reference="re_test_123",
        amount_cents=5000,
        status="succeeded",
    )


# ─────────────────────────────────────────────────────────────
# Checkout Session Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkout_success(
    async_session,
    test_organization,
    test_user,
    payment_settings,
    mock_provider,
    mock_checkout_session,
):
    """Test successful checkout session creation."""
    mock_provider.create_checkout_session = AsyncMock(
        return_value=mock_checkout_session
    )

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        result = await PaymentService.create_checkout(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            amount_cents=10000,
            currency="USD",
            description="Test checkout",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
        )

    assert result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_123"
    assert result["payment_id"] is not None
    assert "existing" not in result


@pytest.mark.asyncio
async def test_create_checkout_with_metadata(
    async_session,
    test_organization,
    test_user,
    payment_settings,
    mock_provider,
    mock_checkout_session,
):
    """Test checkout creation with custom metadata."""
    mock_provider.create_checkout_session = AsyncMock(
        return_value=mock_checkout_session
    )

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        await PaymentService.create_checkout(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            amount_cents=10000,
            currency="USD",
            description="Test checkout with metadata",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            metadata={"order_id": "order_123", "product": "premium"},
        )

    # Verify metadata was passed to provider
    call_args = mock_provider.create_checkout_session.call_args
    assert "order_id" in call_args.kwargs["metadata"]
    assert call_args.kwargs["metadata"]["order_id"] == "order_123"


@pytest.mark.asyncio
async def test_create_checkout_idempotency(
    async_session,
    test_organization,
    test_user,
    payment_settings,
    mock_provider,
    mock_checkout_session,
):
    """Test that idempotency key returns existing payment."""
    idempotency_key = f"idem_{uuid4()}"
    mock_provider.create_checkout_session = AsyncMock(
        return_value=mock_checkout_session
    )

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider_for_org",
        new_callable=AsyncMock,
        return_value=mock_provider,
    ):
        # First checkout
        result1 = await PaymentService.create_checkout(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            amount_cents=10000,
            currency="USD",
            description="Test checkout",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            idempotency_key=idempotency_key,
        )

        # Second checkout with same key
        result2 = await PaymentService.create_checkout(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            amount_cents=10000,
            currency="USD",
            description="Test checkout",
            success_url="https://example.com/success",
            cancel_url="https://example.com/cancel",
            idempotency_key=idempotency_key,
        )

    assert result2["payment_id"] == result1["payment_id"]
    assert result2.get("existing") is True


# ─────────────────────────────────────────────────────────────
# Payment Retrieval Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_payment(async_session, test_organization, test_payment):
    """Test retrieving payment details."""
    result = await PaymentService.get_payment(
        async_session,
        str(test_organization.id),
        str(test_payment.id),
    )

    assert result is not None
    assert result["id"] == str(test_payment.id)
    assert result["provider"] == "stripe"
    assert result["amount_cents"] == 10000
    assert result["currency"] == "USD"
    assert result["status"] == "succeeded"


@pytest.mark.asyncio
async def test_get_payment_not_found(async_session, test_organization):
    """Test retrieving non-existent payment returns None."""
    result = await PaymentService.get_payment(
        async_session,
        str(test_organization.id),
        str(uuid4()),
    )

    assert result is None


@pytest.mark.asyncio
async def test_list_payments(async_session, test_organization, test_payment):
    """Test listing payments."""
    result = await PaymentService.list_payments(
        async_session,
        str(test_organization.id),
    )

    assert result["total"] >= 1
    assert len(result["items"]) >= 1
    assert result["limit"] == 20
    assert result["offset"] == 0


@pytest.mark.asyncio
async def test_list_payments_with_status_filter(
    async_session, test_organization, test_user, payment_customer
):
    """Test listing payments with status filter."""
    # Create payments with different statuses
    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_list_pending",
            "amount_cents": 1000,
            "currency": "USD",
            "status": "pending",
        },
    )

    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_list_succeeded",
            "amount_cents": 2000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    result = await PaymentService.list_payments(
        async_session,
        str(test_organization.id),
        status="pending",
    )

    assert all(item["status"] == "pending" for item in result["items"])


# ─────────────────────────────────────────────────────────────
# Refund Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refund_payment_full(
    async_session,
    test_organization,
    test_user,
    payment_settings,
    payment_customer,
    mock_provider,
    mock_refund_result,
):
    """Test full refund of a payment."""
    # Create a succeeded payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_refund_full",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # Mock full refund
    full_refund = RefundResult(
        success=True,
        refund_reference="re_full_123",
        amount_cents=5000,
        status="succeeded",
    )
    mock_provider.refund_payment = AsyncMock(return_value=full_refund)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        result = await PaymentService.refund_payment(
            async_session,
            str(test_organization.id),
            str(payment.id),
            actor_id=str(test_user.id),
        )

    assert result["success"] is True
    assert result["amount_cents"] == 5000
    assert result["new_status"] == "refunded"


@pytest.mark.asyncio
async def test_refund_payment_partial(
    async_session, test_organization, test_user, payment_settings, mock_provider
):
    """Test partial refund of a payment."""
    # Create a succeeded payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_refund_partial",
            "amount_cents": 10000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    # Mock partial refund
    partial_refund = RefundResult(
        success=True,
        refund_reference="re_partial_123",
        amount_cents=3000,
        status="succeeded",
    )
    mock_provider.refund_payment = AsyncMock(return_value=partial_refund)

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        result = await PaymentService.refund_payment(
            async_session,
            str(test_organization.id),
            str(payment.id),
            amount_cents=3000,
            actor_id=str(test_user.id),
        )

    assert result["success"] is True
    assert result["amount_cents"] == 3000
    assert result["new_status"] == "partially_refunded"


@pytest.mark.asyncio
async def test_refund_payment_not_found(async_session, test_organization):
    """Test refunding non-existent payment raises error."""
    with pytest.raises(ValueError, match="Payment not found"):
        await PaymentService.refund_payment(
            async_session,
            str(test_organization.id),
            str(uuid4()),
        )


@pytest.mark.asyncio
async def test_refund_payment_wrong_status(async_session, test_organization, test_user):
    """Test refunding payment with invalid status raises error."""
    # Create a pending payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_refund_pending",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",  # Cannot refund pending
        },
    )

    with pytest.raises(ValueError, match="Cannot refund payment with status"):
        await PaymentService.refund_payment(
            async_session,
            str(test_organization.id),
            str(payment.id),
        )


@pytest.mark.asyncio
async def test_refund_exceeds_available(
    async_session, test_organization, test_user, payment_settings
):
    """Test refund amount exceeding available raises error."""
    # Create a partially refunded payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_refund_exceed",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "succeeded",
        },
    )

    with pytest.raises(ValueError, match="Refund amount.*exceeds available"):
        await PaymentService.refund_payment(
            async_session,
            str(test_organization.id),
            str(payment.id),
            amount_cents=10000,  # More than payment amount
        )


# ─────────────────────────────────────────────────────────────
# Webhook Processing Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_webhook_event_succeeded(
    async_session, test_organization, test_user
):
    """Test processing payment succeeded webhook."""
    # Create a pending payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_webhook_succeed",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
        },
    )

    # Create webhook event
    event = WebhookEvent(
        event_id="evt_test_succeed",
        event_type="payment_intent.succeeded",
        normalized_type=NormalizedEventType.PAYMENT_SUCCEEDED,
        payment_reference="pi_webhook_succeed",
        data={"status": "succeeded"},
        created_at="2024-01-01T00:00:00Z",
    )

    result = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    assert result is True

    # Verify payment status updated
    updated = await get_payment(
        async_session,
        str(test_organization.id),
        str(payment.id),
    )
    assert updated.status == "succeeded"


@pytest.mark.asyncio
async def test_process_webhook_event_failed(
    async_session, test_organization, test_user
):
    """Test processing payment failed webhook."""
    # Create a pending payment
    payment = await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_webhook_fail",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
        },
    )

    # Create webhook event
    event = WebhookEvent(
        event_id="evt_test_fail",
        event_type="payment_intent.payment_failed",
        normalized_type=NormalizedEventType.PAYMENT_FAILED,
        payment_reference="pi_webhook_fail",
        data={
            "status": "failed",
            "failure_code": "card_declined",
            "failure_message": "Your card was declined",
        },
        created_at="2024-01-01T00:00:00Z",
    )

    result = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    assert result is True

    # Verify payment status updated
    updated = await get_payment(
        async_session,
        str(test_organization.id),
        str(payment.id),
    )
    assert updated.status == "failed"


@pytest.mark.asyncio
async def test_process_webhook_event_duplicate(
    async_session, test_organization, test_user
):
    """Test duplicate webhook events are handled idempotently."""
    # Create a pending payment
    await create_payment(
        async_session,
        str(test_organization.id),
        {
            "user_id": str(test_user.id),
            "provider": "stripe",
            "provider_reference": "pi_webhook_dup",
            "amount_cents": 5000,
            "currency": "USD",
            "status": "pending",
        },
    )

    # Create webhook event
    event = WebhookEvent(
        event_id="evt_duplicate_123",
        event_type="payment_intent.succeeded",
        normalized_type=NormalizedEventType.PAYMENT_SUCCEEDED,
        payment_reference="pi_webhook_dup",
        data={"status": "succeeded"},
        created_at="2024-01-01T00:00:00Z",
    )

    # Process first time
    result1 = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    # Process second time (same event_id)
    result2 = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    assert result1 is True
    assert result2 is True  # Should return True (already processed)


@pytest.mark.asyncio
async def test_process_webhook_event_no_payment_reference(async_session):
    """Test webhook event without payment reference."""
    event = WebhookEvent(
        event_id="evt_no_ref",
        event_type="account.updated",
        normalized_type=NormalizedEventType.UNKNOWN,
        payment_reference=None,  # No payment reference
        data={},
        created_at="2024-01-01T00:00:00Z",
    )

    result = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    assert result is False


@pytest.mark.asyncio
async def test_process_webhook_event_payment_not_found(async_session):
    """Test webhook event for non-existent payment."""
    event = WebhookEvent(
        event_id="evt_not_found",
        event_type="payment_intent.succeeded",
        normalized_type=NormalizedEventType.PAYMENT_SUCCEEDED,
        payment_reference="pi_does_not_exist",
        data={},
        created_at="2024-01-01T00:00:00Z",
    )

    result = await PaymentService.process_webhook_event(
        async_session,
        "stripe",
        event,
    )

    assert result is False


# ─────────────────────────────────────────────────────────────
# Payment Method Management Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_payment_methods(
    async_session, test_organization, test_user, saved_payment_method
):
    """Test retrieving user's saved payment methods."""
    result = await PaymentService.get_user_payment_methods(
        async_session,
        str(test_organization.id),
        str(test_user.id),
    )

    assert len(result) >= 1
    method = result[0]
    assert method["type"] == "card"
    assert method["last_four"] == "4242"
    assert method["brand"] == "visa"


@pytest.mark.asyncio
async def test_get_user_payment_methods_empty(
    async_session, test_organization, second_org_user
):
    """Test retrieving payment methods for user with none."""
    result = await PaymentService.get_user_payment_methods(
        async_session,
        str(test_organization.id),
        str(second_org_user.id),  # User in different org, no methods
    )

    assert result == []


@pytest.mark.asyncio
async def test_delete_payment_method(
    async_session,
    test_organization,
    test_user,
    payment_customer,
    payment_settings,
    mock_provider,
):
    """Test deleting a saved payment method."""
    from src.crud.payment import create_saved_payment_method

    # Create a payment method to delete
    method = await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_to_delete",
            "type": "card",
            "last_four": "9999",
        },
    )

    mock_provider.detach_payment_method = AsyncMock()

    with patch(
        "src.services.payments.service.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        result = await PaymentService.delete_payment_method(
            async_session,
            str(test_organization.id),
            str(test_user.id),
            str(method.id),
        )

    assert result is True


@pytest.mark.asyncio
async def test_delete_payment_method_not_found(
    async_session, test_organization, test_user
):
    """Test deleting non-existent payment method returns False."""
    result = await PaymentService.delete_payment_method(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        str(uuid4()),
    )

    assert result is False


@pytest.mark.asyncio
async def test_set_default_payment_method(
    async_session, test_organization, test_user, payment_customer
):
    """Test setting a payment method as default."""
    from src.crud.payment import create_saved_payment_method

    # Create two payment methods
    await create_saved_payment_method(
        async_session,
        str(test_organization.id),
        {
            "customer_id": str(payment_customer.id),
            "provider": "stripe",
            "provider_payment_method_id": "pm_default_1",
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
            "provider_payment_method_id": "pm_default_2",
            "type": "card",
            "is_default": False,
        },
    )

    # Set method2 as default
    result = await PaymentService.set_default_payment_method(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        str(method2.id),
    )

    assert result is True


@pytest.mark.asyncio
async def test_set_default_payment_method_not_found(
    async_session, test_organization, test_user
):
    """Test setting default for non-existent method returns False."""
    result = await PaymentService.set_default_payment_method(
        async_session,
        str(test_organization.id),
        str(test_user.id),
        str(uuid4()),
    )

    assert result is False


# ─────────────────────────────────────────────────────────────
# Event to Status Mapping Tests
# ─────────────────────────────────────────────────────────────


def test_map_event_to_status_succeeded():
    """Test mapping succeeded event to status."""
    status = PaymentService._map_event_to_status(NormalizedEventType.PAYMENT_SUCCEEDED)
    assert status == PaymentStatus.SUCCEEDED.value


def test_map_event_to_status_failed():
    """Test mapping failed event to status."""
    status = PaymentService._map_event_to_status(NormalizedEventType.PAYMENT_FAILED)
    assert status == PaymentStatus.FAILED.value


def test_map_event_to_status_refunded():
    """Test mapping refund event to status."""
    status = PaymentService._map_event_to_status(NormalizedEventType.REFUND_SUCCEEDED)
    assert status == PaymentStatus.REFUNDED.value


def test_map_event_to_status_unknown():
    """Test mapping unknown event returns None."""
    status = PaymentService._map_event_to_status(NormalizedEventType.UNKNOWN)
    assert status is None
