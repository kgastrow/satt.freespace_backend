"""
SendGrid email notification provider.

Implements the NotificationProvider interface for SendGrid email API.
"""

from typing import Any, Optional
import uuid

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, HtmlContent, Mail, To

from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationProvider, NotificationResult


class SendGridProvider(NotificationProvider):
    """
    SendGrid email notification provider.

    Uses the SendGrid Web API v3 to send emails. Provides better
    deliverability and tracking compared to basic SMTP.
    """

    def __init__(
        self,
        api_key: str,
        sender_email: Optional[str] = None,
        sender_name: Optional[str] = None,
    ):
        """
        Initialize the SendGrid provider.

        Args:
            api_key: SendGrid API key
            sender_email: Default sender email address
            sender_name: Default sender name
        """
        self._api_key = api_key
        self._sender_email = sender_email
        self._sender_name = sender_name
        self._client = SendGridAPIClient(api_key)

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "sendgrid"

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
        Send an email via SendGrid.

        Args:
            recipient: Email address of the recipient
            message: Plain text email body
            subject: Email subject line (defaults to "Notification" if not provided)
            html_message: Optional HTML version of the email body
            metadata: Optional metadata with keys like 'sender_email', 'sender_name',
                     'reply_to', 'cc', 'bcc', 'categories', 'custom_args'

        Returns:
            NotificationResult with success status and SendGrid message ID
        """
        metadata = metadata or {}

        # Use default subject if not provided
        email_subject = subject or "Notification"

        # Determine sender
        sender_email = metadata.get("sender_email") or self._sender_email
        sender_name = metadata.get("sender_name") or self._sender_name

        if not sender_email:
            logger.error("SendGrid send failed: No sender email configured")
            return NotificationResult(
                success=False,
                error_message="No sender email configured",
                status="failed",
            )

        try:
            # Build the sender
            if sender_name:
                from_email = Email(sender_email, sender_name)
            else:
                from_email = Email(sender_email)

            # Build the message
            to_email = To(recipient)

            # Create mail object
            mail = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=email_subject,
            )

            # Add plain text content
            mail.add_content(Content("text/plain", message))

            # Add HTML content if provided
            if html_message:
                mail.add_content(HtmlContent(html_message))

            # Add reply-to if specified
            if metadata.get("reply_to"):
                from sendgrid.helpers.mail import ReplyTo

                mail.reply_to = ReplyTo(metadata["reply_to"])

            # Add categories for tracking
            if metadata.get("categories"):
                from sendgrid.helpers.mail import Category

                for cat in metadata["categories"]:
                    mail.add_category(Category(cat))

            # Send the email (synchronous call, but non-blocking for FastAPI)
            response = self._client.send(mail)

            # Check response status
            if response.status_code in (200, 201, 202):
                # Extract message ID from headers
                message_id = response.headers.get("X-Message-Id", str(uuid.uuid4()))
                logger.info(
                    f"SendGrid email sent successfully to {recipient}, "
                    f"message_id={message_id}, status={response.status_code}"
                )
                return NotificationResult(
                    success=True,
                    provider_message_id=message_id,
                    status="sent",
                    metadata={
                        "recipient": recipient,
                        "status_code": response.status_code,
                    },
                )
            else:
                logger.warning(
                    f"SendGrid send returned non-success status: {response.status_code}"
                )
                return NotificationResult(
                    success=False,
                    error_message=f"SendGrid returned status {response.status_code}",
                    status="failed",
                    metadata={"status_code": response.status_code},
                )

        except Exception as e:
            logger.error(f"SendGrid send error for {recipient}: {e}")
            return NotificationResult(
                success=False,
                error_message=str(e),
                status="failed",
            )

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent email.

        Note: SendGrid provides delivery tracking via webhooks. This method
        returns 'unknown' as real-time status checking requires webhook setup.

        For production, configure SendGrid Event Webhook to receive:
        - delivered, opened, clicked, bounced, dropped, etc.

        Args:
            message_id: The X-Message-Id from the send response

        Returns:
            Status string (always 'unknown' without webhook data)
        """
        # SendGrid doesn't provide synchronous delivery status API.
        # In production, you would:
        # 1. Configure SendGrid Event Webhook
        # 2. Store delivery events in database
        # 3. Query local database for status

        # For now, return unknown
        return "unknown"


# Factory function for creating providers
def create_sendgrid_provider(
    api_key: str,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> SendGridProvider:
    """
    Factory function to create a SendGrid provider instance.

    Args:
        api_key: SendGrid API key
        sender_email: Default sender email
        sender_name: Default sender name

    Returns:
        Configured SendGridProvider instance
    """
    return SendGridProvider(
        api_key=api_key,
        sender_email=sender_email,
        sender_name=sender_name,
    )
