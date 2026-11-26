"""
Payment provider implementations.

This module auto-registers enabled providers with the factory on import.
To add a new provider:
1. Create a provider class implementing PaymentProvider
2. Add configuration check and registration below
"""

from src.core.config import settings
from src.services.payments.factory import PaymentProviderFactory


# Auto-register enabled providers on import
# Providers are conditionally imported based on configuration

# Stripe provider (most common)
if getattr(settings, "STRIPE_SECRET_KEY", ""):
    try:
        from .stripe import StripeProvider

        PaymentProviderFactory.register("stripe", StripeProvider)
    except ImportError:
        pass  # Stripe SDK not installed

# PayFast provider (South Africa)
if getattr(settings, "PAYFAST_MERCHANT_ID", ""):
    try:
        from .payfast import PayfastProvider

        PaymentProviderFactory.register("payfast", PayfastProvider)
    except ImportError:
        pass  # PayFast provider not available

# PayPal provider
if getattr(settings, "PAYPAL_CLIENT_ID", ""):
    try:
        from .paypal import PaypalProvider

        PaymentProviderFactory.register("paypal", PaypalProvider)
    except ImportError:
        pass  # PayPal provider not available
