"""
Base class for SMS notification providers.
Extends the base NotificationProvider with SMS-specific functionality.
"""

from abc import abstractmethod
from typing import Any, Optional

from src.services.notifications.base import NotificationProvider, NotificationResult


class SMSProvider(NotificationProvider):
    """
    Abstract base class for SMS providers.

    Extends NotificationProvider with SMS-specific properties and methods.
    All SMS providers (AWS SNS, Twilio SMS, etc.) should extend this class.
    """

    @property
    def channel(self) -> str:
        """SMS channel identifier."""
        return "sms"

    @property
    @abstractmethod
    def supports_sender_id(self) -> bool:
        """
        Whether this provider supports alphanumeric sender IDs.

        Some countries/providers allow custom sender IDs (e.g., "MyApp")
        instead of a phone number.
        """
        pass

    @property
    @abstractmethod
    def max_message_length(self) -> int:
        """
        Maximum message length in characters.

        Standard SMS is 160 characters for GSM-7 encoding,
        or 70 characters for Unicode. Providers may support
        concatenated messages for longer content.
        """
        pass

    @abstractmethod
    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send an SMS message.

        Args:
            recipient: Phone number with country code (e.g., "+1234567890")
            message: SMS message content
            subject: Ignored for SMS
            html_message: Ignored for SMS
            metadata: Optional metadata (sender_id, message_type, etc.)

        Returns:
            NotificationResult with success status and message ID
        """
        pass

    @abstractmethod
    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent SMS.

        Args:
            message_id: The provider_message_id from the send result

        Returns:
            Status string: 'pending', 'sent', 'delivered', 'failed', 'unknown'
        """
        pass

    def validate_phone_number(self, phone_number: str) -> bool:
        """
        Validate that a phone number is in E.164 format.

        E.164 format: +[country code][subscriber number]
        Example: +14155552671

        Args:
            phone_number: The phone number to validate

        Returns:
            True if valid E.164 format, False otherwise
        """
        if not phone_number:
            return False

        # Must start with +
        if not phone_number.startswith("+"):
            return False

        # Remove + and check remaining is digits
        digits = phone_number[1:]
        if not digits.isdigit():
            return False

        # E.164 allows 1-15 digits after country code
        if len(digits) < 7 or len(digits) > 15:
            return False

        return True
