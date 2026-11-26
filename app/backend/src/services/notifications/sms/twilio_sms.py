"""
Twilio SMS provider.
Uses the Twilio library to send SMS messages via the Twilio API.
"""

from typing import Any, Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationResult
from src.services.notifications.sms.base import SMSProvider


try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    TwilioClient = None
    TwilioRestException = Exception


class TwilioSMSProvider(SMSProvider):
    """
    Twilio SMS notification provider.

    Uses Twilio's Programmable SMS API to send text messages.
    Requires the twilio library.

    Configuration (from settings or passed directly):
        - TWILIO_ACCOUNT_SID: Twilio account SID
        - TWILIO_AUTH_TOKEN: Twilio auth token
        - TWILIO_SMS_FROM: SMS sender number (e.g., "+14155238886")
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        """
        Initialize the Twilio SMS provider.

        Args:
            account_sid: Twilio account SID. Defaults to settings.TWILIO_ACCOUNT_SID
            auth_token: Twilio auth token. Defaults to settings.TWILIO_AUTH_TOKEN
            from_number: SMS sender number. Defaults to settings.TWILIO_SMS_FROM
        """
        if not TWILIO_AVAILABLE:
            logger.warning(
                "twilio library not installed. Twilio SMS provider will not work."
            )

        self._account_sid = account_sid or getattr(settings, "TWILIO_ACCOUNT_SID", None)
        self._auth_token = auth_token or getattr(settings, "TWILIO_AUTH_TOKEN", None)
        self._from_number = from_number or getattr(settings, "TWILIO_SMS_FROM", None)
        self._client: Optional[TwilioClient] = None

    def _get_client(self) -> "TwilioClient":
        """Get or create a Twilio client."""
        if not TWILIO_AVAILABLE:
            raise RuntimeError(
                "twilio library is required. Install with: pip install twilio"
            )

        if not self._account_sid or not self._auth_token:
            raise RuntimeError("Twilio account_sid and auth_token are required")

        if self._client is None:
            self._client = TwilioClient(self._account_sid, self._auth_token)
        return self._client

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "twilio_sms"

    @property
    def supports_sender_id(self) -> bool:
        """
        Twilio supports alphanumeric sender IDs in some countries.

        Note: In the US and Canada, alphanumeric sender IDs are not supported.
        A valid Twilio phone number must be used instead.
        """
        return True

    @property
    def max_message_length(self) -> int:
        """
        Maximum SMS message length.

        Twilio supports concatenated SMS for longer messages (up to 1600 characters).
        Standard SMS is 160 characters for GSM-7 encoding.
        """
        return 1600

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send an SMS message via Twilio.

        Args:
            recipient: Phone number in E.164 format (e.g., "+14155552671")
            message: SMS message content (max 1600 characters)
            subject: Ignored for SMS
            html_message: Ignored for SMS
            metadata: Optional metadata:
                - from_number: Override the default sender number
                - status_callback: URL for delivery status webhooks
                - messaging_service_sid: Use a Messaging Service instead of from_number

        Returns:
            NotificationResult with success status and Twilio message SID
        """
        logger.info(f"Twilio SMS send called for {recipient}")

        if not TWILIO_AVAILABLE:
            logger.error("Twilio library not available")
            return NotificationResult(
                success=False,
                error_message="twilio library not installed",
                status="failed",
            )

        # Validate phone number
        if not self.validate_phone_number(recipient):
            return NotificationResult(
                success=False,
                error_message=f"Invalid phone number format: {recipient}. Expected E.164 format (e.g., +14155552671)",
                status="failed",
            )

        # Truncate message if too long
        if len(message) > self.max_message_length:
            logger.warning(
                f"SMS message truncated from {len(message)} to {self.max_message_length} characters"
            )
            message = message[: self.max_message_length]

        metadata = metadata or {}

        # Determine sender number or messaging service
        from_number = metadata.get("from_number", self._from_number)
        messaging_service_sid = metadata.get("messaging_service_sid")

        if not from_number and not messaging_service_sid:
            logger.error("No SMS sender number configured")
            return NotificationResult(
                success=False,
                error_message="No SMS sender number or messaging service configured",
                status="failed",
            )

        logger.info(f"Twilio SMS: from={from_number}, to={recipient}")

        try:
            client = self._get_client()

            # Build message parameters
            msg_params: dict[str, Any] = {
                "to": recipient,
                "body": message,
            }

            # Use messaging service if provided, otherwise use from number
            if messaging_service_sid:
                msg_params["messaging_service_sid"] = messaging_service_sid
            else:
                msg_params["from_"] = from_number

            # Add status callback if provided
            status_callback = metadata.get("status_callback")
            if status_callback:
                msg_params["status_callback"] = status_callback

            # Send the message
            twilio_message = client.messages.create(**msg_params)

            message_sid = twilio_message.sid
            status = self._map_twilio_status(twilio_message.status)

            logger.info(
                f"SMS sent via Twilio to {recipient}, sid={message_sid}, status={status}"
            )

            return NotificationResult(
                success=True,
                provider_message_id=message_sid,
                status=status,
                metadata={
                    "recipient": recipient,
                    "twilio_status": twilio_message.status,
                },
            )

        except TwilioRestException as e:
            error_msg = f"Twilio error {e.code}: {e.msg}"
            logger.error(f"Twilio SMS send error for {recipient}: {error_msg}")

            return NotificationResult(
                success=False,
                error_message=error_msg,
                status="failed",
                metadata={"twilio_error_code": e.code},
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"SMS send error for {recipient}: {error_msg}")

            return NotificationResult(
                success=False,
                error_message=error_msg,
                status="failed",
            )

    def _map_twilio_status(self, twilio_status: str) -> str:
        """
        Map Twilio message status to our standard status.

        Twilio statuses: accepted, queued, sending, sent, delivered, undelivered, failed
        Our statuses: pending, queued, sent, delivered, failed

        Note: Initial statuses (accepted/queued/sending) are mapped to 'queued'.
        Twilio will send webhook callbacks to update status to sent/delivered/failed.
        """
        status_map = {
            "accepted": "queued",
            "queued": "queued",
            "sending": "queued",
            "sent": "sent",
            "delivered": "delivered",
            "undelivered": "failed",
            "failed": "failed",
        }
        return status_map.get(twilio_status, "queued")

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent SMS.

        Args:
            message_id: The Twilio message SID from the send result

        Returns:
            Status string: 'pending', 'queued', 'sent', 'delivered', 'failed', 'unknown'
        """
        if not TWILIO_AVAILABLE:
            return "unknown"

        if not message_id:
            return "unknown"

        try:
            client = self._get_client()
            message = client.messages(message_id).fetch()
            status = self._map_twilio_status(message.status)
            logger.debug(
                f"SMS message {message_id} status: {message.status} -> {status}"
            )
            return status
        except TwilioRestException as e:
            logger.warning(f"Error checking SMS status for {message_id}: {e.msg}")
            return "unknown"
        except Exception as e:
            logger.warning(f"Error checking SMS status for {message_id}: {e}")
            return "unknown"


# Singleton instance
twilio_sms_provider = TwilioSMSProvider()
