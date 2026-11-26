"""
Base classes for notification providers.
All notification providers (email, SMS, WhatsApp) implement this interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class NotificationResult:
    """
    Result of a notification send operation.

    Attributes:
        success: Whether the notification was sent successfully
        provider_message_id: The message ID returned by the provider (for tracking)
        error_message: Error message if the send failed
        status: Current status of the notification ('sent', 'queued', 'failed')
        metadata: Additional provider-specific metadata
    """

    success: bool
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    status: str = "sent"  # 'sent', 'queued', 'failed'
    metadata: dict[str, Any] = field(default_factory=dict)


class NotificationProvider(ABC):
    """
    Abstract base class for notification providers.

    All notification providers (email, SMS, WhatsApp) must implement this interface.
    This allows the notification dispatcher to work with any provider uniformly.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Unique identifier for this provider.

        Examples: 'aws_ses', 'aws_sns', 'twilio', 'twilio_whatsapp'
        """
        pass

    @property
    @abstractmethod
    def channel(self) -> str:
        """
        The notification channel this provider handles.

        Values: 'email', 'sms', 'whatsapp', 'in_app'
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
        Send a notification to a recipient.

        Args:
            recipient: The recipient address (email, phone number with country code)
            message: The plain text message content
            subject: Optional subject line (primarily for email)
            html_message: Optional HTML version of the message (for email)
            metadata: Optional provider-specific metadata

        Returns:
            NotificationResult with success status and provider details
        """
        pass

    @abstractmethod
    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a previously sent message.

        Args:
            message_id: The provider_message_id from the NotificationResult

        Returns:
            Status string: 'pending', 'sent', 'delivered', 'failed', 'bounced', 'unknown'
        """
        pass
