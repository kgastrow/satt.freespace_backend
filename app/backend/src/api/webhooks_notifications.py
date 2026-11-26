"""
Notification provider webhook endpoints.

Handles incoming webhook events from notification providers (Twilio, etc.)
for delivery status updates.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from src.api.deps import get_session
from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.crud import notification as notification_crud
from src.logger.logger import Logger
from src.services.notifications.sms.twilio_sms import TwilioSMSProvider


router = APIRouter(prefix="/webhooks/notifications", tags=["webhooks"])

# Twilio SDK availability check
try:
    from twilio.request_validator import RequestValidator

    TWILIO_VALIDATOR_AVAILABLE = True
except ImportError:
    TWILIO_VALIDATOR_AVAILABLE = False
    Logger.warning("Twilio SDK not available, webhook signature validation disabled")


def verify_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """
    Verify Twilio webhook signature using the official Twilio SDK.

    Uses Twilio's RequestValidator as recommended in their security docs:
    https://www.twilio.com/docs/usage/webhooks/webhooks-security

    Args:
        request_url: The full URL Twilio sent the request to
        params: POST parameters from the request
        signature: The X-Twilio-Signature header value

    Returns:
        True if signature is valid, False otherwise
    """
    if not settings.TWILIO_AUTH_TOKEN:
        Logger.warning(
            "TWILIO_AUTH_TOKEN not configured, skipping signature verification"
        )
        return True  # Allow in development without token

    if not TWILIO_VALIDATOR_AVAILABLE:
        Logger.warning("Twilio SDK not available, skipping signature verification")
        return True

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    return validator.validate(request_url, params, signature)


@router.post("/twilio/sms-status")
async def twilio_sms_status_callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Handle Twilio SMS status callback webhook.

    Twilio sends POST requests to this endpoint when SMS status changes.
    Status progression: queued -> sending -> sent -> delivered (or failed/undelivered)

    Twilio POST parameters include:
    - MessageSid: Unique message identifier
    - MessageStatus: Current status (queued, sending, sent, delivered, failed)
    - To: Recipient phone number
    - From: Sender phone number
    - ErrorCode: Error code if failed (optional)
    - ErrorMessage: Error message if failed (optional)

    See: https://www.twilio.com/docs/messaging/guides/outbound-message-status-in-status-callbacks
    """
    # Get form data
    form_data = await request.form()
    params = {key: form_data[key] for key in form_data}

    # Verify Twilio signature
    signature = request.headers.get("X-Twilio-Signature", "")
    request_url = str(request.url)

    # Twilio uses the URL you configured, which may differ from the actual request URL
    # due to proxies. Rebuild it from PUBLIC_URL_BACKEND: the signature is an
    # HMAC over the exact URL STRING Twilio called, which is an API route on the
    # backend origin, never the SPA origin.
    if settings.PUBLIC_URL_BACKEND:
        webhook_path = "/api/v1/webhooks/notifications/twilio/sms-status"
        expected_url = f"{settings.PUBLIC_URL_BACKEND.rstrip('/')}{webhook_path}"
        request_url = expected_url

    if not verify_twilio_signature(request_url, params, signature):
        Logger.warning("Invalid Twilio signature for SMS status callback")
        raise create_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid signature",
            detail_code="common.forbidden",
        )

    # Extract relevant fields
    message_sid = params.get("MessageSid", "")
    message_status = params.get("MessageStatus", "")
    error_code = params.get("ErrorCode")
    error_message = params.get("ErrorMessage")

    if not message_sid or not message_status:
        Logger.warning(
            f"Missing required fields in Twilio callback: "
            f"sid={message_sid}, status={message_status}"
        )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields",
            detail_code="common.bad_request",
        )

    Logger.info(
        f"Twilio SMS status callback: sid={message_sid}, status={message_status}"
    )

    # Map Twilio status to our status
    provider = TwilioSMSProvider()
    internal_status = provider._map_twilio_status(message_status)

    # Build error message if applicable
    error = None
    if error_code or error_message:
        error = f"{error_code}: {error_message}" if error_code else error_message

    # Update notification status
    notification = await notification_crud.update_notification_status_by_provider_id(
        session=session,
        provider_message_id=message_sid,
        status=internal_status,
        error=error,
    )

    if notification:
        Logger.info(
            f"Updated notification {notification.id} status to {internal_status} "
            f"(Twilio status: {message_status})"
        )
    else:
        # This can happen if notification was deleted or this is a duplicate callback
        Logger.warning(f"No notification found for Twilio message SID: {message_sid}")

    # Always return 200 to acknowledge receipt
    # Twilio will retry if we return non-2xx
    return {"received": True}
