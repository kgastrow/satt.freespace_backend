"""
API tests for notification webhook endpoints.

Tests verify:
- Twilio SMS status webhooks
- Signature validation
- Status updates for notifications
"""

from unittest.mock import AsyncMock, MagicMock, patch
import urllib.parse

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def twilio_sms_status_payload():
    """Sample Twilio SMS status callback payload."""
    return {
        "MessageSid": "SM1234567890abcdef",
        "MessageStatus": "delivered",
        "To": "+15551234567",
        "From": "+15557654321",
        "ErrorCode": "",
        "ErrorMessage": "",
    }


@pytest.fixture
def twilio_signature_headers():
    """Generate Twilio signature headers."""
    return {
        "X-Twilio-Signature": "test_twilio_signature_123",
    }


# ─────────────────────────────────────────────────────────────
# Twilio SMS Status Webhook Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twilio_sms_status_webhook_delivered(
    client: AsyncClient,
    twilio_sms_status_payload,
):
    """Test Twilio SMS status webhook for delivered status."""
    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ):
        # Form-encode the payload as Twilio sends
        form_data = urllib.parse.urlencode(twilio_sms_status_payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    # Should acknowledge receipt with 200
    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True


@pytest.mark.asyncio
async def test_twilio_sms_status_webhook_failed(
    client: AsyncClient,
):
    """Test Twilio SMS status webhook for failed status."""
    payload = {
        "MessageSid": "SM1234567890abcdef",
        "MessageStatus": "failed",
        "To": "+15551234567",
        "From": "+15557654321",
        "ErrorCode": "30003",
        "ErrorMessage": "Unreachable destination handset",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ):
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True


@pytest.mark.asyncio
async def test_twilio_sms_status_invalid_signature_rejected(
    client: AsyncClient,
    twilio_sms_status_payload,
):
    """Test Twilio webhook with invalid signature is rejected."""
    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=False,
    ):
        form_data = urllib.parse.urlencode(twilio_sms_status_payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "invalid_signature",
            },
        )

    # Should reject with 403
    assert response.status_code == 403
    data = response.json()
    assert data["detail"] == "Invalid signature"


@pytest.mark.asyncio
async def test_twilio_sms_status_missing_required_fields(
    client: AsyncClient,
):
    """Test Twilio webhook with missing required fields is rejected."""
    # Missing MessageSid
    payload = {
        "MessageStatus": "delivered",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ):
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    # Should reject with 400
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Missing required fields"


@pytest.mark.asyncio
async def test_twilio_sms_status_missing_status_field(
    client: AsyncClient,
):
    """Test Twilio webhook with missing MessageStatus is rejected."""
    # Missing MessageStatus
    payload = {
        "MessageSid": "SM1234567890abcdef",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ):
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    # Should reject with 400
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Missing required fields"


@pytest.mark.asyncio
async def test_twilio_status_unknown_message_id_handled(
    client: AsyncClient,
):
    """Test that unknown message IDs are handled gracefully."""
    payload = {
        "MessageSid": "SM_unknown_12345",
        "MessageStatus": "delivered",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=None,  # Notification not found
    ):
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    # Should still acknowledge (don't retry for unknown messages)
    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True


# ─────────────────────────────────────────────────────────────
# Status Mapping Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twilio_status_queued(client: AsyncClient):
    """Test handling of 'queued' status."""
    payload = {
        "MessageSid": "SM_test_queued",
        "MessageStatus": "queued",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    # Verify that update was called with mapped 'queued' status
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["provider_message_id"] == "SM_test_queued"
    assert call_kwargs["status"] == "queued"


@pytest.mark.asyncio
async def test_twilio_status_sent(client: AsyncClient):
    """Test handling of 'sent' status."""
    payload = {
        "MessageSid": "SM_test_sent",
        "MessageStatus": "sent",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["status"] == "sent"


@pytest.mark.asyncio
async def test_twilio_status_undelivered(client: AsyncClient):
    """Test handling of 'undelivered' status."""
    payload = {
        "MessageSid": "SM_test_undelivered",
        "MessageStatus": "undelivered",
        "To": "+15551234567",
        "From": "+15557654321",
        "ErrorCode": "30006",
        "ErrorMessage": "Landline or unreachable carrier",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    # 'undelivered' maps to 'failed'
    assert call_kwargs["status"] == "failed"
    assert call_kwargs["error"] == "30006: Landline or unreachable carrier"


@pytest.mark.asyncio
async def test_twilio_status_sending(client: AsyncClient):
    """Test handling of 'sending' status."""
    payload = {
        "MessageSid": "SM_test_sending",
        "MessageStatus": "sending",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    # 'sending' maps to 'queued'
    assert call_kwargs["status"] == "queued"


@pytest.mark.asyncio
async def test_twilio_status_accepted(client: AsyncClient):
    """Test handling of 'accepted' status."""
    payload = {
        "MessageSid": "SM_test_accepted",
        "MessageStatus": "accepted",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    # 'accepted' maps to 'queued'
    assert call_kwargs["status"] == "queued"


# ─────────────────────────────────────────────────────────────
# WhatsApp Status Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twilio_whatsapp_status_webhook(client: AsyncClient):
    """Test Twilio WhatsApp status callback."""
    payload = {
        "MessageSid": "WA1234567890abcdef",
        "MessageStatus": "read",
        "To": "whatsapp:+15551234567",
        "From": "whatsapp:+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ):
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["received"] is True


# ─────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_twilio_sms_status_error_code_only(client: AsyncClient):
    """Test handling of error code without error message."""
    payload = {
        "MessageSid": "SM_test_error",
        "MessageStatus": "failed",
        "To": "+15551234567",
        "From": "+15557654321",
        "ErrorCode": "30003",
        "ErrorMessage": "",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["error"] == "30003: "


@pytest.mark.asyncio
async def test_twilio_sms_status_error_message_only(client: AsyncClient):
    """Test handling of error message without error code."""
    payload = {
        "MessageSid": "SM_test_error_msg",
        "MessageStatus": "failed",
        "To": "+15551234567",
        "From": "+15557654321",
        "ErrorCode": "",
        "ErrorMessage": "Unknown error occurred",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["error"] == "Unknown error occurred"


@pytest.mark.asyncio
async def test_twilio_sms_status_no_errors(client: AsyncClient):
    """Test handling of successful status with no error fields."""
    payload = {
        "MessageSid": "SM_test_success",
        "MessageStatus": "delivered",
        "To": "+15551234567",
        "From": "+15557654321",
    }

    mock_notification = MagicMock()
    mock_notification.id = "test-notification-id"

    with patch(
        "src.api.webhooks_notifications.verify_twilio_signature",
        return_value=True,
    ), patch(
        "src.crud.notification.update_notification_status_by_provider_id",
        new_callable=AsyncMock,
        return_value=mock_notification,
    ) as mock_update:
        form_data = urllib.parse.urlencode(payload)

        response = await client.post(
            "/api/v1/webhooks/notifications/twilio/sms-status",
            content=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Twilio-Signature": "valid_signature",
            },
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["error"] is None


# ─────────────────────────────────────────────────────────────
# Signature Verification Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_twilio_signature_no_auth_token():
    """Test that signature verification passes when no auth token is configured."""
    from src.api.webhooks_notifications import verify_twilio_signature

    with patch("src.api.webhooks_notifications.settings") as mock_settings:
        mock_settings.TWILIO_AUTH_TOKEN = None

        result = verify_twilio_signature(
            request_url="https://example.com/webhook",
            params={"MessageSid": "SM123", "MessageStatus": "delivered"},
            signature="any_signature",
        )

    # Should return True when no auth token configured (development mode)
    assert result is True


@pytest.mark.asyncio
async def test_verify_twilio_signature_sdk_not_available():
    """Test signature verification when Twilio SDK is not available."""
    from src.api.webhooks_notifications import verify_twilio_signature

    with patch("src.api.webhooks_notifications.settings") as mock_settings, patch(
        "src.api.webhooks_notifications.TWILIO_VALIDATOR_AVAILABLE", False
    ):
        mock_settings.TWILIO_AUTH_TOKEN = "test_token"

        result = verify_twilio_signature(
            request_url="https://example.com/webhook",
            params={"MessageSid": "SM123", "MessageStatus": "delivered"},
            signature="any_signature",
        )

    # Should return True when SDK not available
    assert result is True
