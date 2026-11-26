"""
AWS SNS SMS provider.
Uses aioboto3 for async SNS operations to send SMS messages.
"""

from typing import Any, Optional

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.services.notifications.base import NotificationResult
from src.services.notifications.sms.base import SMSProvider


try:
    import aioboto3

    AIOBOTO3_AVAILABLE = True
except ImportError:
    AIOBOTO3_AVAILABLE = False
    aioboto3 = None


class SNSProvider(SMSProvider):
    """
    AWS SNS SMS provider.

    Uses AWS Simple Notification Service to send SMS messages.
    Requires aioboto3 for async operations.

    Configuration (from settings or passed directly):
        - AWS_REGION: AWS region (e.g., 'us-east-1')
        - AWS_ACCESS_KEY_ID: AWS access key
        - AWS_SECRET_ACCESS_KEY: AWS secret key
    """

    def __init__(
        self,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
    ):
        """
        Initialize the SNS provider.

        Args:
            region: AWS region. Defaults to settings.AWS_REGION
            access_key_id: AWS access key. Defaults to settings.AWS_ACCESS_KEY_ID
            secret_access_key: AWS secret key. Defaults to settings.AWS_SECRET_ACCESS_KEY
        """
        self._region = region or getattr(settings, "AWS_REGION", "us-east-1")
        self._access_key_id = access_key_id or getattr(
            settings, "AWS_ACCESS_KEY_ID", None
        )
        self._secret_access_key = secret_access_key or getattr(
            settings, "AWS_SECRET_ACCESS_KEY", None
        )
        self._session: Optional[aioboto3.Session] = None

    def _get_session(self) -> "aioboto3.Session":
        """Get or create an aioboto3 session."""
        if not AIOBOTO3_AVAILABLE:
            raise RuntimeError(
                "aioboto3 is required for SNS provider. Install with: pip install aioboto3"
            )

        if self._session is None:
            self._session = aioboto3.Session(
                aws_access_key_id=self._access_key_id,
                aws_secret_access_key=self._secret_access_key,
                region_name=self._region,
            )
        return self._session

    @property
    def provider_name(self) -> str:
        """Unique provider identifier."""
        return "aws_sns"

    @property
    def supports_sender_id(self) -> bool:
        """
        AWS SNS supports sender IDs in some countries.

        Note: Sender ID support varies by country. In the US, sender IDs
        are not supported for most messages.
        """
        return True

    @property
    def max_message_length(self) -> int:
        """
        Maximum SMS message length.

        AWS SNS supports messages up to 1600 characters when using
        concatenated SMS (up to 10 segments).
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
        Send an SMS message via AWS SNS.

        Args:
            recipient: Phone number in E.164 format (e.g., "+14155552671")
            message: SMS message content (max 1600 characters)
            subject: Ignored for SMS
            html_message: Ignored for SMS
            metadata: Optional metadata:
                - sender_id: Alphanumeric sender ID (country-dependent)
                - message_type: 'Transactional' or 'Promotional'
                - max_price: Maximum spend per message in USD

        Returns:
            NotificationResult with success status and SNS message ID
        """
        if not AIOBOTO3_AVAILABLE:
            return NotificationResult(
                success=False,
                error_message="aioboto3 not installed",
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

        # Build SMS attributes
        sms_attrs: dict[str, dict[str, str]] = {}

        # Set sender ID if provided
        sender_id = metadata.get("sender_id")
        if sender_id:
            sms_attrs["AWS.SNS.SMS.SenderID"] = {
                "DataType": "String",
                "StringValue": sender_id,
            }

        # Set message type (Transactional = higher deliverability, Promotional = lower cost)
        message_type = metadata.get("message_type", "Transactional")
        sms_attrs["AWS.SNS.SMS.SMSType"] = {
            "DataType": "String",
            "StringValue": message_type,
        }

        # Set max price if provided
        max_price = metadata.get("max_price")
        if max_price:
            sms_attrs["AWS.SNS.SMS.MaxPrice"] = {
                "DataType": "String",
                "StringValue": str(max_price),
            }

        try:
            session = self._get_session()
            async with session.client("sns", region_name=self._region) as sns_client:
                response = await sns_client.publish(
                    PhoneNumber=recipient,
                    Message=message,
                    MessageAttributes=sms_attrs if sms_attrs else None,
                )

                message_id = response.get("MessageId")
                logger.info(f"SMS sent via SNS to {recipient}, message_id={message_id}")

                return NotificationResult(
                    success=True,
                    provider_message_id=message_id,
                    status="sent",
                    metadata={
                        "recipient": recipient,
                        "message_type": message_type,
                    },
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"SNS SMS send error for {recipient}: {error_msg}")

            return NotificationResult(
                success=False,
                error_message=error_msg,
                status="failed",
            )

    async def check_delivery_status(self, message_id: str) -> str:
        """
        Check the delivery status of a sent SMS.

        Note: AWS SNS provides delivery status via CloudWatch Logs
        when configured. This method returns 'unknown' as direct
        status checking is not supported via the API.

        For production use, configure SNS delivery status logging
        to CloudWatch and query logs, or use SNS delivery receipts
        with a webhook endpoint.

        Args:
            message_id: The SNS message ID from the send result

        Returns:
            Status string (currently always 'unknown')
        """
        # AWS SNS doesn't provide direct delivery status API
        # Status must be obtained via CloudWatch Logs or delivery receipts
        # See: https://docs.aws.amazon.com/sns/latest/dg/sms_stats_cloudwatch.html
        logger.debug(f"Delivery status check requested for SNS message {message_id}")
        return "unknown"


# Singleton instance
sns_provider = SNSProvider()
