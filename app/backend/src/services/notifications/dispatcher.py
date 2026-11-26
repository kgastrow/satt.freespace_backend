"""
Notification Dispatcher Service.

Orchestrates sending notifications across multiple channels (email, SMS, WhatsApp, in-app).
Checks user preferences before sending and records notification history.
"""

import time
from typing import Any, Optional
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.notification import BODY_PREVIEW_MAX_LENGTH, create_notification
from src.crud.notification_template import get_template_by_code
from src.crud.organization_email_settings import get_effective_email_config
from src.logger.logger import Logger as logger
from src.middleware.notification_metrics import (
    record_email_failure,
    record_notification_delivery,
    record_sms_delivery,
    record_whatsapp_delivery,
)
from src.services.notifications.email_provider import EmailProvider
from src.services.notifications.preference_checker import preference_checker
from src.services.notifications.template_renderer import template_renderer


# How much rendered content is handed to the persist path. Comfortably larger
# than BODY_PREVIEW_MAX_LENGTH so a credential sitting near the truncation
# boundary is scrubbed whole rather than sliced into a usable prefix, and small
# enough to bound the scrubber's work on a large HTML-ish body.
_BODY_PREVIEW_SOURCE_LIMIT = max(BODY_PREVIEW_MAX_LENGTH * 4, 1000)


class NotificationDispatcher:
    """
    Main notification dispatcher service.

    Orchestrates the sending of notifications across multiple channels,
    checking user preferences and recording notification history.
    """

    def __init__(self):
        self._providers: dict[str, Any] = {}
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Lazy initialization of providers."""
        if self._initialized:
            return

        # Initialize providers based on configuration.
        #
        # This instance has NO organization email config, so its send() refuses
        # rather than falling back to the process-global SMTP singleton. It is
        # only ever reached through _get_provider("email"); every real send
        # path resolves an org-specific provider via get_email_provider().
        self._providers["email"] = EmailProvider()

        # In-app provider for in-app notifications
        from src.services.notifications.in_app_provider import in_app_provider

        self._providers["in_app"] = in_app_provider

        # SMS provider (Twilio)
        try:
            from src.services.notifications.sms.twilio_sms import twilio_sms_provider

            self._providers["sms"] = twilio_sms_provider
            logger.info(
                f"SMS provider initialized: {twilio_sms_provider.provider_name}"
            )
        except ImportError as e:
            logger.warning(f"Twilio SMS provider not available: {e}")

        # WhatsApp provider (Twilio)
        try:
            from src.services.notifications.whatsapp.twilio_wa import (
                twilio_whatsapp_provider,
            )

            self._providers["whatsapp"] = twilio_whatsapp_provider
        except ImportError:
            logger.warning("Twilio WhatsApp provider not available")

        self._initialized = True

    async def send_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        channel: str,
        recipient: str,
        content: str,
        category_code: Optional[str] = None,
        is_urgent: bool = False,
        template_id: Optional[str] = None,
        subject: Optional[str] = None,
        html_content: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Send a notification to a recipient.

        This is the main entry point for sending notifications. It:
        1. Checks user preferences using PreferenceChecker
        2. If allowed, gets the appropriate provider and sends
        3. Creates a Notification record with the status
        4. Returns the notification record

        Args:
            session: Database session
            user_id: ID of the user receiving the notification
            organization_id: Organization ID for multi-tenancy
            channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')
            recipient: Email address or phone number (not used for in_app)
            content: Notification content (plain text)
            category_code: Optional category code for preference checking
            is_urgent: If True, bypasses quiet hours
            template_id: Optional template ID used for this notification
            subject: Optional subject line (for email)
            html_content: Optional HTML content (for email)
            metadata: Optional additional metadata

        Returns:
            Notification record dict or None if skipped
        """
        await self._ensure_initialized()

        UUID(user_id)
        UUID(organization_id)
        UUID(template_id) if template_id else None

        # Check user preferences
        preference_result = await preference_checker.check_can_send(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            channel=channel,
            category_code=category_code,
            is_urgent=is_urgent,
        )

        if not preference_result.allowed:
            # Record skipped notification metrics
            record_notification_delivery(channel, "skipped")

            # Record skipped notification
            return await self._record_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel=channel,
                recipient=recipient,
                content=content,
                status="skipped",
                provider=None,
                template_id=template_id,
                subject=subject,
                error_message=f"Skipped: {preference_result.skip_reason.value if preference_result.skip_reason else 'unknown'}",
                metadata=metadata,
            )

        # Get the appropriate provider
        if channel == "email":
            provider = await self.get_email_provider(session, organization_id)
        else:
            provider = self._get_provider(channel)

        if not provider:
            logger.error(f"No provider available for channel: {channel}")
            # Record failure metrics for missing provider
            record_notification_delivery(channel, "failed")

            return await self._record_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel=channel,
                recipient=recipient,
                content=content,
                status="failed",
                provider=None,
                template_id=template_id,
                subject=subject,
                error_message=f"No provider available for channel: {channel}",
                metadata=metadata,
            )

        # Send the notification
        try:
            # Add status callback URL for SMS/WhatsApp channels (Twilio)
            send_metadata = dict(metadata) if metadata else {}
            if (
                channel in ("sms", "whatsapp")
                and "status_callback" not in send_metadata
            ):
                from src.core.config import settings

                # Backend origin: Twilio calls this API route directly and
                # signs the exact URL, which webhooks_notifications.py rebuilds
                # from the same setting to verify.
                if settings.PUBLIC_URL_BACKEND:
                    webhook_path = "/api/v1/webhooks/notifications/twilio/sms-status"
                    send_metadata["status_callback"] = (
                        f"{settings.PUBLIC_URL_BACKEND.rstrip('/')}{webhook_path}"
                    )

            logger.info(
                f"Sending {channel} notification via {provider.provider_name} to {recipient}"
            )

            # Track delivery timing
            start_time = time.perf_counter()
            result = await provider.send(
                recipient=recipient,
                message=content,
                subject=subject,
                html_message=html_content,
                metadata=send_metadata,
            )
            duration = time.perf_counter() - start_time

            logger.info(
                f"Provider result: success={result.success}, status={result.status}, error={result.error_message}"
            )

            # Record metrics
            record_notification_delivery(channel, result.status, duration)
            self._record_channel_metric(
                channel, provider.provider_name, result.status, result.error_message
            )

            return await self._record_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel=channel,
                recipient=recipient,
                content=content,
                status=result.status,
                provider=provider.provider_name,
                template_id=template_id,
                subject=subject,
                provider_message_id=result.provider_message_id,
                error_message=result.error_message if not result.success else None,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error sending notification via {channel}: {e}")

            # Record failure metrics
            record_notification_delivery(channel, "failed")
            self._record_channel_metric(
                channel,
                provider.provider_name if provider else "unknown",
                "failed",
                str(e),
            )

            return await self._record_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                channel=channel,
                recipient=recipient,
                content=content,
                status="failed",
                provider=provider.provider_name if provider else None,
                template_id=template_id,
                subject=subject,
                error_message=str(e),
                metadata=metadata,
            )

    async def send_to_user(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        channel: str,
        content: str,
        category_code: Optional[str] = None,
        is_urgent: bool = False,
        template_code: Optional[str] = None,
        template_vars: Optional[dict[str, Any]] = None,
        subject: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Send a notification to a user by looking up their contact info.

        This method:
        1. Gets the user's email/phone from their profile or preferences
        2. Renders template if template_code is provided
        3. Calls send_notification with the resolved recipient

        Args:
            session: Database session
            user_id: ID of the user to notify
            organization_id: Organization ID for multi-tenancy
            channel: Notification channel ('email', 'sms', 'whatsapp', 'in_app')
            content: Notification content (used if no template)
            category_code: Optional category code for preference checking
            is_urgent: If True, bypasses quiet hours
            template_code: Optional template code to render
            template_vars: Variables for template rendering
            subject: Optional subject line (for email)

        Returns:
            Notification record dict or None if skipped/failed
        """
        from src.models.user import User

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Get user to find contact info
        result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.error(f"User not found: {user_id} in org {organization_id}")
            return None

        # Handle in_app channel specially - it doesn't need a recipient
        if channel == "in_app":
            return await self.send_in_app_notification(
                session=session,
                user_id=user_id,
                organization_id=organization_id,
                title=subject or "Notification",
                body=content,
                category_code=category_code,
                link=template_vars.get("link") if template_vars else None,
            )

        # Determine recipient based on channel using preference checker
        recipient = await preference_checker.get_effective_recipient(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            channel=channel,
        )

        if not recipient:
            logger.warning(f"No {channel} contact info for user {user_id}")
            return None

        # Render template if provided
        rendered_content = content
        rendered_subject = subject
        rendered_html = None
        template_id = None
        metadata: dict[str, Any] = dict(template_vars) if template_vars else {}

        if template_code:
            # Get template from database
            template = await get_template_by_code(
                session=session,
                code=template_code,
                channel=channel,
                organization_id=organization_id,
            )
            if template:
                template_id = str(template.id)
                vars_dict = template_vars or {}

                # For WhatsApp with provider_template_id (Twilio content_sid),
                # use Twilio's Content API instead of local rendering.
                # This is REQUIRED for business-initiated messages outside the 24-hour window.
                if channel == "whatsapp" and template.provider_template_id:
                    metadata["content_sid"] = template.provider_template_id
                    if vars_dict:
                        metadata["content_variables"] = vars_dict
                    # body_text is used as fallback preview, not sent to Twilio
                    rendered_content = template.body_text or content
                else:
                    # Local rendering for email, SMS, in-app, or WhatsApp without provider_template_id
                    rendered_content = template_renderer.render(
                        template.body_text or content, vars_dict
                    )
                    if template.subject:
                        rendered_subject = template_renderer.render(
                            template.subject, vars_dict
                        )
                    if template.body_html:
                        rendered_html = template_renderer.render_html(
                            template.body_html, vars_dict, escape_html=True
                        )

        return await self.send_notification(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            channel=channel,
            recipient=recipient,
            content=rendered_content,
            category_code=category_code,
            is_urgent=is_urgent,
            template_id=template_id,
            subject=rendered_subject,
            html_content=rendered_html,
            metadata=metadata,
        )

    async def send_in_app_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        title: str,
        body: Optional[str] = None,
        category_code: Optional[str] = None,
        link: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Send an in-app notification directly using the InAppProvider.

        This is a convenience method that bypasses the standard provider routing
        and directly uses the InAppProvider to create the notification and
        broadcast it via WebSocket.

        Args:
            session: Database session
            user_id: ID of the user to notify
            organization_id: Organization ID for multi-tenancy
            title: Notification title
            body: Notification body text (optional)
            category_code: Category code to resolve category_id (optional)
            link: Click-through URL (optional)

        Returns:
            Dict with notification details or None if failed
        """
        await self._ensure_initialized()

        provider = self._providers.get("in_app")
        if not provider:
            logger.error("InAppProvider not available")
            record_notification_delivery("in_app", "failed")
            return None

        # Resolve category_id from category_code if provided
        category_id = None
        if category_code:
            from src.crud.notification_category import get_category_by_code

            category = await get_category_by_code(
                session=session,
                code=category_code,
                organization_id=organization_id,
            )
            if category:
                category_id = str(category.id)

        # Track delivery timing
        start_time = time.perf_counter()
        result = await provider.send_in_app(
            session=session,
            organization_id=organization_id,
            user_id=user_id,
            title=title,
            body=body,
            link=link,
            category_id=category_id,
        )
        duration = time.perf_counter() - start_time

        # Record metrics
        record_notification_delivery("in_app", result.status, duration)

        if result.success:
            return {
                "id": result.provider_message_id,
                "channel": "in_app",
                "status": result.status,
                "user_id": user_id,
                "title": title,
            }
        else:
            logger.error(f"Failed to send in-app notification: {result.error_message}")
            return None

    async def get_email_provider(
        self,
        session: AsyncSession,
        organization_id: str,
    ) -> Optional[Any]:
        """
        Get the appropriate email provider based on organization settings.

        Args:
            session: Database session
            organization_id: Organization UUID string

        Returns:
            Email provider instance configured for the organization, or None if
            the organization's configured provider cannot be honoured. Never
            silently downgrades to a different provider than the one configured
            - callers treat None as "no provider available" and record a failed
            notification.
        """
        try:
            email_config = await get_effective_email_config(session, organization_id)

            if email_config.provider == "sendgrid":
                if not email_config.sendgrid_api_key:
                    # The org explicitly selected SendGrid but the key is
                    # missing or could not be decrypted. Falling through to
                    # SMTP here would send the mail over completely different
                    # infrastructure and record it as provider="smtp",
                    # status="sent" - a silent, invisible substitution.
                    # Refuse instead; send_notification() records a failed
                    # notification when no provider is available.
                    logger.error(
                        f"Email provider for org {organization_id} is configured as "
                        "'sendgrid' but no usable SendGrid API key is available "
                        "(missing or undecryptable). Refusing to downgrade to SMTP."
                    )
                    return None

                from src.services.notifications.sendgrid_provider import (
                    SendGridProvider,
                )

                logger.info(f"Using SendGrid provider for org {organization_id}")
                return SendGridProvider(
                    api_key=email_config.sendgrid_api_key,
                    sender_email=email_config.sender_email,
                    sender_name=email_config.sender_name,
                )
            else:
                # Use SMTP provider with organization-specific config.
                # EmailProvider routes through AsyncEmailService.send_with_config,
                # which honours config.provider instead of assuming SMTP and
                # hand-assigning connection attributes.
                logger.info(f"Using SMTP provider for org {organization_id}")
                return EmailProvider(email_config=email_config)

        except Exception as e:
            # The third silent-downgrade door. This used to build a platform-SMTP
            # provider from global config and return it, so an org that had
            # deliberately configured SendGrid got its mail sent over the
            # platform's SMTP, from the platform's sender, recorded as
            # provider="smtp", status="sent" - the exact substitution the
            # sendgrid branch above refuses, reached through the error path
            # instead. Resolving the org's config is the one thing that must
            # work before we can honour it, so failing to resolve it is a
            # failure to send, not a licence to send as someone else.
            logger.error(f"Error getting email provider for org {organization_id}: {e}")
            return None

    def _get_provider(self, channel: str) -> Optional[Any]:
        """
        Get the appropriate notification provider for a channel.

        Note: For email, use get_email_provider() instead to get org-specific config.

        Args:
            channel: The notification channel ('email', 'sms', 'whatsapp', 'in_app')

        Returns:
            The provider instance or None if not available
        """
        # Map channels to providers
        # Email -> Use get_email_provider() for org-specific config
        # SMS -> SNSProvider (default) or configured provider
        # WhatsApp -> TwilioWhatsAppProvider
        # In-app -> InAppProvider (saves to DB and broadcasts via WebSocket)

        if channel == "email":
            # Retained for interface symmetry only. The instance registered
            # here carries no organization email config, so its send() returns
            # a failed NotificationResult instead of relaying over the
            # platform's SMTP credentials. Callers that actually want to
            # deliver email must use get_email_provider().
            return self._providers.get("email")
        elif channel == "sms":
            # TODO: Check config for preferred SMS provider
            # For now, default to AWS SNS
            return self._providers.get("sms")
        elif channel == "whatsapp":
            return self._providers.get("whatsapp")
        elif channel == "in_app":
            return self._providers.get("in_app")
        else:
            logger.warning(f"Unknown notification channel: {channel}")
            return None

    def _record_channel_metric(
        self,
        channel: str,
        provider: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record channel-specific Prometheus metrics.

        Args:
            channel: Notification channel (email, sms, whatsapp, in_app)
            provider: Provider name (smtp, sendgrid, twilio, etc.)
            status: Delivery status (sent, failed, skipped)
            error_message: Optional error message for failure classification
        """
        if channel == "email" and status == "failed":
            # Classify email error type
            error_type = "unknown"
            if error_message:
                error_lower = error_message.lower()
                if "timeout" in error_lower:
                    error_type = "timeout"
                elif "connection" in error_lower:
                    error_type = "connection"
                elif "auth" in error_lower:
                    error_type = "authentication"
                elif "invalid" in error_lower or "recipient" in error_lower:
                    error_type = "invalid_recipient"
                elif "rate" in error_lower or "limit" in error_lower:
                    error_type = "rate_limit"
            record_email_failure(provider, error_type)
        elif channel == "sms":
            record_sms_delivery(provider, status)
        elif channel == "whatsapp":
            record_whatsapp_delivery(provider, status)

    async def _record_notification(
        self,
        session: AsyncSession,
        user_id: str,
        organization_id: str,
        channel: str,
        recipient: str,
        content: str,
        status: str,
        provider: Optional[str],
        template_id: Optional[str] = None,
        subject: Optional[str] = None,
        provider_message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Create a notification history record.

        Args:
            session: Database session
            user_id: ID of the user
            organization_id: Organization ID
            channel: Notification channel
            recipient: Email or phone number
            content: Notification content
            status: Notification status
            provider: Provider name used
            template_id: Optional template ID
            subject: Optional subject line
            provider_message_id: Optional message ID from provider
            error_message: Optional error message
            metadata: Optional additional metadata

        Returns:
            Dict representation of the notification record
        """
        # body_preview policy (scrub + truncate) lives in crud.notification, so
        # every persist path gets the same treatment. Hand over a bounded slice
        # of the *rendered* content: it is scrubbed before it reaches a column.
        # `provider.send` above already received the unscrubbed content - the
        # redaction is on the persist path only, never on the delivery path.
        body_preview = content[:_BODY_PREVIEW_SOURCE_LIMIT] if content else None

        try:
            notification = await create_notification(
                session=session,
                organization_id=organization_id,
                user_id=user_id,
                channel=channel,
                recipient=recipient,
                data={
                    "provider": provider,
                    "template_id": template_id,
                    "subject": subject,
                    "body_preview": body_preview,
                    "status": status,
                    "provider_message_id": provider_message_id,
                    "error_message": error_message,
                    "metadata": metadata,
                },
            )

            logger.info(
                f"Notification recorded: {notification.id} - {channel} to {recipient} - {status}"
            )

            return {
                "id": str(notification.id),
                "created_time": (
                    notification.created_time.isoformat()
                    if notification.created_time
                    else None
                ),
                "organization_id": (
                    str(notification.organization_id)
                    if notification.organization_id
                    else None
                ),
                "user_id": str(notification.user_id) if notification.user_id else None,
                "channel": notification.channel,
                "provider": notification.provider,
                "recipient": notification.recipient,
                "template_id": (
                    str(notification.template_id) if notification.template_id else None
                ),
                "subject": notification.subject,
                "body_preview": notification.body_preview,
                "status": notification.status,
                "provider_message_id": notification.provider_message_id,
                "error_message": notification.error_message,
                "retry_count": notification.retry_count,
            }
        except Exception as e:
            logger.error(f"Failed to record notification: {e}")
            # Return a dict with the data even if DB save fails
            return {
                "id": str(uuid.uuid4()),
                "organization_id": organization_id,
                "user_id": user_id,
                "channel": channel,
                "recipient": recipient,
                "status": status,
                "error_message": str(e),
            }


class NotificationResult:
    """
    Result of a notification send operation.

    This is a simplified version - the full version is in base.py.

    DEPRECATED. Its only producer was the EmailProviderWrapper class that used
    to live in this module; that class has been folded into
    ``notifications.email_provider.EmailProvider`` (see get_email_provider),
    which returns the real ``base.NotificationResult``. This shim is retained
    only because existing tests import ``NotificationResult`` from this module.
    New code must use ``src.services.notifications.base.NotificationResult``.
    """

    def __init__(
        self,
        success: bool,
        provider_message_id: Optional[str] = None,
        error_message: Optional[str] = None,
        status: str = "sent",
    ):
        self.success = success
        self.provider_message_id = provider_message_id
        self.error_message = error_message
        self.status = status


# Singleton instance
notification_dispatcher = NotificationDispatcher()
