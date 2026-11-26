"""
Notifications service package.
Provides notification dispatch, bulk processing, and preference management.
"""

# Base classes
from src.services.notifications.base import NotificationProvider, NotificationResult
from src.services.notifications.bulk_processor import BulkProcessor, bulk_processor

# Higher-level services
from src.services.notifications.dispatcher import (
    NotificationDispatcher,
    notification_dispatcher,
)

# Providers
from src.services.notifications.email_provider import EmailProvider, email_provider
from src.services.notifications.preference_checker import (
    PreferenceChecker,
    PreferenceCheckResult,
    SkipReason,
    preference_checker,
)
from src.services.notifications.sms import (
    SMSProvider,
    SNSProvider,
    TwilioSMSProvider,
    sns_provider,
    twilio_sms_provider,
)
from src.services.notifications.template_renderer import (
    TemplateRenderer,
    template_renderer,
)
from src.services.notifications.unsubscribe import (
    UnsubscribeService,
    unsubscribe_service,
)
from src.services.notifications.whatsapp import (
    TwilioWhatsAppProvider,
    twilio_whatsapp_provider,
)


__all__ = [
    # Base classes
    "NotificationProvider",
    "NotificationResult",
    # Email
    "EmailProvider",
    "email_provider",
    # SMS
    "SMSProvider",
    "SNSProvider",
    "sns_provider",
    "TwilioSMSProvider",
    "twilio_sms_provider",
    # WhatsApp
    "TwilioWhatsAppProvider",
    "twilio_whatsapp_provider",
    # Higher-level services
    "notification_dispatcher",
    "NotificationDispatcher",
    "bulk_processor",
    "BulkProcessor",
    "preference_checker",
    "PreferenceChecker",
    "SkipReason",
    "PreferenceCheckResult",
    "template_renderer",
    "TemplateRenderer",
    "unsubscribe_service",
    "UnsubscribeService",
]
