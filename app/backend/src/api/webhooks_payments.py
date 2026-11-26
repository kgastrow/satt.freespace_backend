"""
Payment provider webhook endpoints.

Handles incoming webhook events from payment providers (Stripe, PayFast, PayPal, etc.)
Webhooks are processed asynchronously via ARQ background jobs.
"""

from datetime import datetime, timedelta, timezone
import traceback
from typing import Optional

from fastapi import APIRouter, Request
from starlette import status

from src.core.config import settings
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger
from src.services.payments import PaymentProviderFactory
from src.services.tasks import task_queue


router = APIRouter(prefix="/webhooks/payments", tags=["webhooks"])

# Valid providers - pre-validate to prevent log pollution from enumeration attacks
VALID_PROVIDERS = {"stripe", "payfast", "paypal"}

# Signature header names for each provider
SIGNATURE_HEADERS = {
    "stripe": "stripe-signature",
    "payfast": "pf-request-signature",
    "paypal": "paypal-transmission-sig",
}

# Timestamp header names for each provider
TIMESTAMP_HEADERS = {
    "stripe": None,  # Timestamp is in the signature header (t= parameter)
    "payfast": "pf-request-timestamp",
    "paypal": "paypal-transmission-time",
}



def extract_webhook_timestamp(
    provider: str, signature: str, headers: dict
) -> Optional[datetime]:
    """
    Extract timestamp from webhook request for replay attack protection.

    Different providers include timestamps in different locations:
    - Stripe: In the signature header as 't=' parameter
    - PayFast: In 'pf-request-timestamp' header
    - PayPal: In 'paypal-transmission-time' header (ISO 8601 format)

    Args:
        provider: Payment provider name
        signature: Signature header value
        headers: Request headers dict

    Returns:
        datetime in UTC timezone, or None if timestamp cannot be extracted
    """
    try:
        if provider == "stripe":
            # Stripe signature format: t=1234567890,v1=signature
            if signature:
                for part in signature.split(","):
                    if part.startswith("t="):
                        timestamp_str = part[2:]
                        return datetime.fromtimestamp(
                            int(timestamp_str), tz=timezone.utc
                        )
        elif provider == "payfast":
            timestamp_header = headers.get("pf-request-timestamp")
            if timestamp_header:
                # PayFast uses Unix timestamp
                return datetime.fromtimestamp(int(timestamp_header), tz=timezone.utc)
        elif provider == "paypal":
            timestamp_header = headers.get("paypal-transmission-time")
            if timestamp_header:
                # PayPal uses ISO 8601 format (e.g., "2024-01-15T10:30:00Z")
                # Handle both with and without Z suffix
                if timestamp_header.endswith("Z"):
                    timestamp_header = timestamp_header[:-1] + "+00:00"
                return datetime.fromisoformat(timestamp_header)
    except (ValueError, TypeError) as e:
        Logger.warning(f"Failed to parse webhook timestamp for {provider}: {e}")
    return None


def validate_webhook_timestamp(
    event_timestamp: Optional[datetime], tolerance_seconds: int
) -> bool:
    """
    Validate that webhook timestamp is within acceptable tolerance.

    Args:
        event_timestamp: Timestamp from the webhook request
        tolerance_seconds: Maximum age in seconds for the webhook to be valid

    Returns:
        True if timestamp is valid (within tolerance), False otherwise
    """
    if event_timestamp is None:
        # If we couldn't extract a timestamp, we can't validate
        # Return True to not break webhooks for providers without timestamps
        return True

    now = datetime.now(timezone.utc)
    tolerance = timedelta(seconds=tolerance_seconds)

    # Check if timestamp is within tolerance (both past and future)
    return abs(now - event_timestamp) <= tolerance


@router.post("/{provider}")
async def payment_webhook(
    provider: str,
    request: Request,
):
    """
    Handle payment provider webhooks.

    Each provider has its own endpoint for clarity in webhook configuration.
    Signature verification happens before any processing.
    Event processing is done asynchronously via ARQ for fast webhook response.

    Provider webhook URLs:
    - Stripe: POST /api/v1/webhooks/payments/stripe
    - PayFast: POST /api/v1/webhooks/payments/payfast
    - PayPal: POST /api/v1/webhooks/payments/paypal

    Args:
        provider: Provider name from URL path
        request: Raw HTTP request

    Returns:
        Acknowledgment response with job_id for tracking
    """
    # Pre-validate provider against allowlist to prevent log pollution
    # from enumeration attacks (LOW-001)
    if provider not in VALID_PROVIDERS:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown provider",
            detail_code="common.not_found",
        )

    # Validate provider with factory
    try:
        payment_provider = PaymentProviderFactory.get_provider(provider)
    except ValueError:
        Logger.warning(f"Webhook received for unknown provider: {provider}")
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown provider",
            detail_code="common.not_found",
        )

    # Get raw payload
    payload = await request.body()

    # Get signature header
    signature_header = SIGNATURE_HEADERS.get(provider, f"{provider}-signature")
    signature = request.headers.get(signature_header, "")

    if not signature and payment_provider.capabilities.supports_webhook_signatures:
        Logger.warning(f"Missing signature for {provider} webhook")
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing signature",
            detail_code="common.bad_request",
        )

    # Verify signature
    if payment_provider.capabilities.supports_webhook_signatures:
        if not payment_provider.verify_webhook_signature(payload, signature):
            Logger.warning(f"Invalid signature for {provider} webhook")
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
                detail_code="common.forbidden",
            )

    # Validate webhook timestamp to prevent replay attacks (HIGH-001)
    # Extract timestamp from provider-specific header/signature
    event_timestamp = extract_webhook_timestamp(
        provider, signature, dict(request.headers)
    )
    tolerance_seconds = settings.PAYMENTS_WEBHOOK_TOLERANCE_SECONDS
    if not validate_webhook_timestamp(event_timestamp, tolerance_seconds):
        Logger.warning(
            f"Webhook timestamp outside tolerance for {provider}: {event_timestamp}"
        )
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook timestamp expired",
            detail_code="common.bad_request",
        )

    # Parse event
    try:
        event = payment_provider.parse_webhook_event(payload)
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to parse {provider} webhook: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload",
            detail_code="common.bad_request",
        )

    Logger.info(f"Received {provider} webhook: {event.event_type} ({event.event_id})")

    # Enqueue for background processing via shared TaskQueue
    try:
        job_id = await task_queue.enqueue_job(
            "process_payment_webhook_task",
            provider,
            event.event_id,
            event.event_type,
            event.normalized_type.value,
            event.payment_reference,
            event.customer_reference,
            event.data,
            event.created_at,
        )
        Logger.info(f"Webhook {event.event_id} queued for processing: job={job_id}")

        # Acknowledge receipt immediately
        # Most providers expect a 2xx response within a few seconds
        return {"received": True}

    except Exception as e:
        # If enqueueing fails, log but still acknowledge receipt
        # The webhook will likely be retried by the provider
        # Return identical response to avoid leaking internal state (MEDIUM-002)
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to enqueue webhook {event.event_id}: {e}\n{error_tb}")
        request.state.error_traceback = error_tb
        return {"received": True}


# Only register test endpoint in DEBUG mode (MEDIUM-001)
# This prevents information disclosure and enumeration in production
if settings.DEBUG:

    @router.get("/{provider}/test")
    async def test_webhook_endpoint(provider: str):
        """
        Test endpoint to verify webhook URL is reachable.

        This endpoint can be used to verify that the webhook URL is
        correctly configured and accessible.

        Note: This endpoint is only available in DEBUG mode and is not
        exposed in production.

        Args:
            provider: Provider name

        Returns:
            Simple acknowledgment
        """
        # Pre-validate provider against allowlist
        if provider not in VALID_PROVIDERS:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unknown provider",
                detail_code="common.not_found",
            )

        return {
            "status": "ok",
            "provider": provider,
            "message": f"Webhook endpoint for {provider} is reachable",
        }
