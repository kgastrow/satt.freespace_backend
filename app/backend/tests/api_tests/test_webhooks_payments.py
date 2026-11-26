"""
API tests for payment webhook endpoints.

Tests verify:
- Signature verification for all providers
- Timestamp validation (replay attack prevention)
- Event processing and job enqueueing
- Provider routing
- Error handling
"""

from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_stripe_provider():
    """Create a mock Stripe payment provider."""
    provider = MagicMock()
    provider.provider_name = "stripe"
    provider.capabilities = MagicMock()
    provider.capabilities.supports_webhook_signatures = True
    provider.verify_webhook_signature = MagicMock(return_value=True)

    # Mock parsed event
    mock_event = MagicMock()
    mock_event.event_id = "evt_test_123"
    mock_event.event_type = "checkout.session.completed"
    mock_event.normalized_type = MagicMock(value="checkout_completed")
    mock_event.payment_reference = "pi_test_123"
    mock_event.customer_reference = "cus_test_123"
    mock_event.data = {"test": "data"}
    mock_event.created_at = datetime.now(timezone.utc)
    provider.parse_webhook_event = MagicMock(return_value=mock_event)

    return provider


@pytest.fixture
def stripe_webhook_payload():
    """Sample Stripe webhook payload."""
    return json.dumps(
        {
            "id": "evt_test_123",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_123",
                    "payment_intent": "pi_test_123",
                    "customer": "cus_test_123",
                    "amount_total": 10000,
                    "currency": "usd",
                }
            },
            "created": int(datetime.now(timezone.utc).timestamp()),
        }
    )


@pytest.fixture
def stripe_signature():
    """Generate a sample Stripe signature header."""
    timestamp = int(datetime.now(timezone.utc).timestamp())
    return f"t={timestamp},v1=test_signature_123"


@pytest.fixture
def mock_enqueue_job():
    """Mock TaskQueue.enqueue_job to prevent Redis connection."""
    with patch(
        "src.api.webhooks_payments.task_queue.enqueue_job",
        new_callable=AsyncMock,
        return_value="job_test_123",
    ) as mock:
        yield mock


# ─────────────────────────────────────────────────────────────
# Stripe Webhook Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stripe_webhook_valid_signature(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
    stripe_signature,
    mock_enqueue_job,
):
    """Test Stripe webhook with valid signature is accepted."""
    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    assert response.status_code == 200
    assert response.json()["received"] is True


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature_rejected(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
    stripe_signature,
):
    """Test Stripe webhook with invalid signature is rejected."""
    mock_stripe_provider.verify_webhook_signature = MagicMock(return_value=False)

    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    assert response.status_code == 400
    assert "Invalid signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stripe_webhook_missing_signature_rejected(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
):
    """Test Stripe webhook without signature is rejected."""
    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 400
    assert "Missing signature" in response.json()["detail"]


@pytest.mark.asyncio
async def test_stripe_webhook_replay_attack_prevented(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
):
    """Test that old timestamps are rejected to prevent replay attacks."""
    # Use timestamp from 10 minutes ago (beyond tolerance)
    old_timestamp = int(
        (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
    )
    old_signature = f"t={old_timestamp},v1=test_signature"

    # Mock validate_webhook_timestamp to return False for old timestamps
    with (
        patch(
            "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
            return_value=mock_stripe_provider,
        ),
        patch(
            "src.api.webhooks_payments.validate_webhook_timestamp",
            return_value=False,
        ),
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": old_signature,
            },
        )

    assert response.status_code == 400
    assert "timestamp" in response.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────
# Event Processing Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_enqueues_background_job(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
    stripe_signature,
    mock_enqueue_job,
):
    """Test that webhook enqueues a background job for processing."""
    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    assert response.status_code == 200
    mock_enqueue_job.assert_called_once()
    call_args = mock_enqueue_job.call_args
    assert call_args[0][0] == "process_payment_webhook_task"


@pytest.mark.asyncio
async def test_webhook_returns_200_even_on_enqueue_failure(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_webhook_payload,
    stripe_signature,
):
    """Test webhook returns 200 even if enqueueing fails (prevents retries)."""
    with (
        patch(
            "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
            return_value=mock_stripe_provider,
        ),
        patch(
            "src.api.webhooks_payments.task_queue.enqueue_job",
            new_callable=AsyncMock,
            side_effect=Exception("Redis error"),
        ),
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content=stripe_webhook_payload,
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    # Should still return 200 to acknowledge receipt
    assert response.status_code == 200
    assert response.json()["received"] is True


# ─────────────────────────────────────────────────────────────
# Provider Routing Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_provider_returns_404(client: AsyncClient):
    """Test that unknown provider returns 404."""
    response = await client.post(
        "/api/v1/webhooks/payments/unknown_provider",
        content="{}",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 404
    assert "Unknown provider" in response.json()["detail"]


@pytest.mark.asyncio
async def test_payfast_webhook_routing(
    client: AsyncClient,
    mock_enqueue_job,
):
    """Test PayFast webhook endpoint exists and routes correctly."""
    mock_provider = MagicMock()
    mock_provider.capabilities.supports_webhook_signatures = True
    mock_provider.verify_webhook_signature = MagicMock(return_value=True)

    mock_event = MagicMock()
    mock_event.event_id = "pf_evt_123"
    mock_event.event_type = "payment.complete"
    mock_event.normalized_type = MagicMock(value="payment_succeeded")
    mock_event.payment_reference = "pf_123"
    mock_event.customer_reference = None
    mock_event.data = {}
    mock_event.created_at = datetime.now(timezone.utc)
    mock_provider.parse_webhook_event = MagicMock(return_value=mock_event)

    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        response = await client.post(
            "/api/v1/webhooks/payments/payfast",
            content='{"signature": "test"}',
            headers={
                "Content-Type": "application/json",
                "pf-request-signature": "test_sig",
                "pf-request-timestamp": timestamp,
            },
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_paypal_webhook_routing(
    client: AsyncClient,
    mock_enqueue_job,
):
    """Test PayPal webhook endpoint exists and routes correctly."""
    mock_provider = MagicMock()
    mock_provider.capabilities.supports_webhook_signatures = True
    mock_provider.verify_webhook_signature = MagicMock(return_value=True)

    mock_event = MagicMock()
    mock_event.event_id = "pp_evt_123"
    mock_event.event_type = "PAYMENT.CAPTURE.COMPLETED"
    mock_event.normalized_type = MagicMock(value="payment_succeeded")
    mock_event.payment_reference = "pp_123"
    mock_event.customer_reference = None
    mock_event.data = {}
    mock_event.created_at = datetime.now(timezone.utc)
    mock_provider.parse_webhook_event = MagicMock(return_value=mock_event)

    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/paypal",
            content="{}",
            headers={
                "Content-Type": "application/json",
                "paypal-transmission-sig": "test_sig",
                "paypal-transmission-time": datetime.now(timezone.utc).isoformat()
                + "Z",
            },
        )

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────
# Invalid Payload Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_webhook_invalid_payload_rejected(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_signature,
):
    """Test webhook with invalid payload is rejected."""
    mock_stripe_provider.parse_webhook_event = MagicMock(
        side_effect=ValueError("Invalid JSON")
    )

    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content="not valid json {",
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    assert response.status_code == 400
    assert "Invalid payload" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_empty_payload(
    client: AsyncClient,
    mock_stripe_provider,
    stripe_signature,
):
    """Test webhook with empty payload."""
    mock_stripe_provider.parse_webhook_event = MagicMock(
        side_effect=ValueError("Empty payload")
    )

    with patch(
        "src.api.webhooks_payments.PaymentProviderFactory.get_provider",
        return_value=mock_stripe_provider,
    ):
        response = await client.post(
            "/api/v1/webhooks/payments/stripe",
            content="",
            headers={
                "Content-Type": "application/json",
                "stripe-signature": stripe_signature,
            },
        )

    assert response.status_code == 400
