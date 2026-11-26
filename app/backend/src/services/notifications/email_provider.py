"""
Email notification provider.
Wraps the existing AsyncEmailService to implement the NotificationProvider interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional
import uuid

from src.logger.logger import Logger as logger
from src.services.email import AsyncEmailService, email_service
from src.services.notifications.base import NotificationProvider, NotificationResult


if TYPE_CHECKING:
    from src.crud.organization_email_settings import EmailConfig


class EmailProvider(NotificationProvider):
    """
    Email notification provider using the existing AsyncEmailService.

    This provider wraps the existing email service to provide a consistent
    interface with other notification channels (SMS, WhatsApp).
    """

    def __init__(
        self,
        email_svc: Optional[AsyncEmailService] = None,
        email_config: Optional[EmailConfig] = None,
    ):
        """
        Initialize the email provider.

        Args:
            email_svc: Optional AsyncEmailService instance. If not provided,
                      uses the default singleton email_service.
            email_config: Optional org-specific email config. When provided,
                         emails are sent via send_with_config using the org's
                         provider settings instead of global defaults.
        """
        self._email_service = email_svc or email_service
        self._email_config = email_config

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "smtp"

    @property
    def channel(self) -> str:
        """Notification channel type."""
        return "email"

    async def send(
        self,
        recipient: str,
        message: str,
        subject: Optional[str] = None,
        html_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> NotificationResult:
        """
        Send an email notification.

        An organization email config is REQUIRED. Without one this provider
        would fall through to the process-global config.json SMTP singleton,
        sending organization mail over platform credentials that the
        organization never configured and recording it as a successful send.
        That is a silent bypass of the configured provider, so it is refused.

        Args:
            recipient: Email address of the recipient
            message: Plain text email body
            subject: Email subject line (defaults to "Notification" if not provided)
            html_message: Optional HTML version of the email body
            metadata: Optional metadata (currently unused; retained for
                interface compatibility with the other providers)

        Returns:
            NotificationResult with success status. success=False /
            status="failed" when no organization email config is present.
        """
        # Use default subject if not provided
        email_subject = subject or "Notification"

        if self._email_config is None:
            logger.error(
                "EmailProvider has no organization email configuration; refusing "
                f"to send to {recipient} over the process-global SMTP defaults."
            )
            return NotificationResult(
                success=False,
                error_message=(
                    "No organization email configuration available. Refusing to send "
                    "via the process-global SMTP defaults - configure the "
                    "organization's email provider first."
                ),
                status="failed",
            )

        try:
            success = await self._email_service.send_with_config(
                to=recipient,
                subject=email_subject,
                body=message,
                config=self._email_config,
                html_body=html_message,
            )

            if success:
                # Generate a message ID for tracking (since SMTP doesn't always return one)
                message_id = str(uuid.uuid4())
                logger.info(
                    f"Email sent successfully to {recipient}, message_id={message_id}"
                )
                return NotificationResult(
                    success=True,
                    provider_message_id=message_id,
                    status="sent",
                    metadata={"recipient": recipient},
                )
            else:
                logger.warning(f"Email send failed for {recipient}")
                return NotificationResult(
                    success=False,
                    error_message="Email sending failed",
                    status="failed",
                )

        except Exception as e:
            logger.error(f"Email provider error for {recipient}: {e}")
            return NotificationResult(
                success=False,
                error_message=str(e),
                status="failed",
            )

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent email.

        Note: Standard SMTP does not provide delivery tracking.
        For production, consider using a service like AWS SES which
        provides delivery notifications via webhooks.

        Args:
            message_id: The provider_message_id from the send result

        Returns:
            Status string (always 'unknown' for basic SMTP)
        """
        # Standard SMTP doesn't support delivery status tracking
        # In production, you would use AWS SES with SNS notifications
        # or a similar service that provides delivery webhooks
        return "unknown"


# Singleton instance
email_provider = EmailProvider()
