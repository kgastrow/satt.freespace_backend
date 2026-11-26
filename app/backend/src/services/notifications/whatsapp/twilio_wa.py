"""
Twilio WhatsApp provider.
Uses the Twilio library to send WhatsApp messages via the Twilio API.
"""

from typing import Any, Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationProvider, NotificationResult


try:
    from twilio.base.exceptions import TwilioRestException
    from twilio.rest import Client as TwilioClient

    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False
    TwilioClient = None
    TwilioRestException = Exception


class TwilioWhatsAppProvider(NotificationProvider):
    """
    Twilio WhatsApp notification provider.

    Uses Twilio's WhatsApp Business API to send WhatsApp messages.
    Requires the twilio library.

    Configuration (from settings or passed directly):
        - TWILIO_ACCOUNT_SID: Twilio account SID
        - TWILIO_AUTH_TOKEN: Twilio auth token
        - TWILIO_WHATSAPP_FROM: WhatsApp sender number (e.g., "whatsapp:+14155238886")
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        """
        Initialize the Twilio WhatsApp provider.

        Args:
            account_sid: Twilio account SID. Defaults to settings.TWILIO_ACCOUNT_SID
            auth_token: Twilio auth token. Defaults to settings.TWILIO_AUTH_TOKEN
            from_number: WhatsApp sender number. Defaults to settings.TWILIO_WHATSAPP_FROM
        """
        if not TWILIO_AVAILABLE:
            logger.warning(
                "twilio library not installed. WhatsApp provider will not work."
            )

        self._account_sid = account_sid or getattr(settings, "TWILIO_ACCOUNT_SID", None)
        self._auth_token = auth_token or getattr(settings, "TWILIO_AUTH_TOKEN", None)
        self._from_number = from_number or getattr(
            settings, "TWILIO_WHATSAPP_FROM", None
        )
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
        return "twilio_whatsapp"

    @property
    def channel(self) -> str:
        """Notification channel type."""
        return "whatsapp"

    def _format_whatsapp_number(self, phone_number: str) -> str:
        """
        Format a phone number for WhatsApp.

        Twilio requires WhatsApp numbers in the format "whatsapp:+14155552671"

        Args:
            phone_number: Phone number in E.164 format (e.g., "+14155552671")

        Returns:
            Formatted WhatsApp number (e.g., "whatsapp:+14155552671")
        """
        if phone_number.startswith("whatsapp:"):
            return phone_number
        return f"whatsapp:{phone_number}"

    def _validate_phone_number(self, phone_number: str) -> bool:
        """
        Validate that a phone number is in E.164 format.

        Args:
            phone_number: The phone number to validate

        Returns:
            True if valid, False otherwise
        """
        # Remove whatsapp: prefix if present
        number = phone_number
        if number.startswith("whatsapp:"):
            number = number[9:]

        if not number.startswith("+"):
            return False

        digits = number[1:]
        if not digits.isdigit():
            return False

        if len(digits) < 7 or len(digits) > 15:
            return False

        return True

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send a WhatsApp message via Twilio.

        Args:
            recipient: Phone number in E.164 format (e.g., "+14155552671")
            message: WhatsApp message content
            subject: Ignored for WhatsApp
            html_message: Ignored for WhatsApp
            metadata: Optional metadata:
                - from_number: Override the default sender number
                - media_url: URL to media attachment (image, document, etc.)
                - content_sid: Content template SID for pre-approved templates
                - content_variables: Variables for template substitution

        Returns:
            NotificationResult with success status and Twilio message SID
        """
        if not TWILIO_AVAILABLE:
            return NotificationResult(
                success=False,
                error_message="twilio library not installed",
                status="failed",
            )

        # Validate phone number
        if not self._validate_phone_number(recipient):
            return NotificationResult(
                success=False,
                error_message=f"Invalid phone number format: {recipient}. Expected E.164 format (e.g., +14155552671)",
                status="failed",
            )

        metadata = metadata or {}

        # Determine sender number
        from_number = metadata.get("from_number", self._from_number)
        if not from_number:
            return NotificationResult(
                success=False,
                error_message="No WhatsApp sender number configured",
                status="failed",
            )

        # Format numbers for WhatsApp
        to_whatsapp = self._format_whatsapp_number(recipient)
        from_whatsapp = self._format_whatsapp_number(from_number)

        try:
            client = self._get_client()

            # Build message parameters
            msg_params: dict[str, Any] = {
                "from_": from_whatsapp,
                "to": to_whatsapp,
            }

            # Check if using a content template
            content_sid = metadata.get("content_sid")
            if content_sid:
                msg_params["content_sid"] = content_sid
                content_variables = metadata.get("content_variables")
                if content_variables:
                    import json

                    msg_params["content_variables"] = json.dumps(content_variables)
            else:
                msg_params["body"] = message

            # Add media URL if provided
            media_url = metadata.get("media_url")
            if media_url:
                msg_params["media_url"] = (
                    [media_url] if isinstance(media_url, str) else media_url
                )

            # Add status callback if provided
            status_callback = metadata.get("status_callback")
            if status_callback:
                msg_params["status_callback"] = status_callback

            # Send the message (Twilio client is sync, run in executor would be ideal for prod)
            # Note: For true async, consider using httpx to call Twilio API directly
            twilio_message = client.messages.create(**msg_params)

            message_sid = twilio_message.sid
            status = self._map_twilio_status(twilio_message.status)

            logger.info(
                f"WhatsApp sent via Twilio to {recipient}, sid={message_sid}, status={status}"
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
            logger.error(f"Twilio WhatsApp send error for {recipient}: {error_msg}")

            return NotificationResult(
                success=False,
                error_message=error_msg,
                status="failed",
                metadata={"twilio_error_code": e.code},
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"WhatsApp send error for {recipient}: {error_msg}")

            return NotificationResult(
                success=False,
                error_message=error_msg,
                status="failed",
            )

    def _map_twilio_status(self, twilio_status: str) -> str:
        """
        Map Twilio message status to our standard status.

        Twilio statuses: queued, sending, sent, delivered, undelivered, failed, read
        Our statuses: pending, queued, sent, delivered, failed
        """
        status_map = {
            "queued": "queued",
            "sending": "queued",
            "sent": "sent",
            "delivered": "delivered",
            "read": "delivered",
            "undelivered": "failed",
            "failed": "failed",
        }
        return status_map.get(twilio_status, "sent")

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent WhatsApp message.

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
                f"WhatsApp message {message_id} status: {message.status} -> {status}"
            )
            return status
        except TwilioRestException as e:
            logger.warning(f"Error checking WhatsApp status for {message_id}: {e.msg}")
            return "unknown"
        except Exception as e:
            logger.warning(f"Error checking WhatsApp status for {message_id}: {e}")
            return "unknown"


# Singleton instance
twilio_whatsapp_provider = TwilioWhatsAppProvider()
