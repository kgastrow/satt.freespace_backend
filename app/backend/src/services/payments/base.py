"""
Payment provider base classes and types.

Defines the abstract interface that all payment providers must implement,
along with standardized types for payment operations.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class PaymentStatus(str, Enum):
    """Normalized payment statuses across all providers."""

    PENDING = "pending"
    PROCESSING = "processing"
    REQUIRES_ACTION = "requires_action"  # 3DS, redirect, etc.
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    DISPUTED = "disputed"


class PaymentMethod(str, Enum):
    """Supported payment method types."""

    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"  # Apple Pay, Google Pay, etc.
    BUY_NOW_PAY_LATER = "bnpl"
    CRYPTO = "crypto"
    OTHER = "other"


class NormalizedEventType(str, Enum):
    """
    Normalized webhook event types across all providers.

    Providers must map their native events to these types
    for consistent handling in the service layer.
    """

    # Payment lifecycle
    PAYMENT_CREATED = "payment.created"
    PAYMENT_PROCESSING = "payment.processing"
    PAYMENT_REQUIRES_ACTION = "payment.requires_action"
    PAYMENT_SUCCEEDED = "payment.succeeded"
    PAYMENT_FAILED = "payment.failed"
    PAYMENT_CANCELLED = "payment.cancelled"

    # Capture/Authorization
    PAYMENT_AUTHORIZED = "payment.authorized"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_CAPTURE_FAILED = "payment.capture_failed"

    # Refunds
    REFUND_CREATED = "refund.created"
    REFUND_SUCCEEDED = "refund.succeeded"
    REFUND_FAILED = "refund.failed"

    # Disputes
    DISPUTE_CREATED = "dispute.created"
    DISPUTE_UPDATED = "dispute.updated"
    DISPUTE_CLOSED = "dispute.closed"

    # Customers
    CUSTOMER_CREATED = "customer.created"
    CUSTOMER_UPDATED = "customer.updated"
    CUSTOMER_DELETED = "customer.deleted"

    # Payment Methods
    PAYMENT_METHOD_ATTACHED = "payment_method.attached"
    PAYMENT_METHOD_DETACHED = "payment_method.detached"
    PAYMENT_METHOD_UPDATED = "payment_method.updated"

    # Subscriptions (for future use)
    SUBSCRIPTION_CREATED = "subscription.created"
    SUBSCRIPTION_UPDATED = "subscription.updated"
    SUBSCRIPTION_CANCELLED = "subscription.cancelled"
    SUBSCRIPTION_PAYMENT_FAILED = "subscription.payment_failed"

    # Checkout
    CHECKOUT_COMPLETED = "checkout.completed"
    CHECKOUT_EXPIRED = "checkout.expired"

    # Unknown/unmapped events
    UNKNOWN = "unknown"


class SubscriptionStatus(str, Enum):
    """Normalized subscription statuses."""

    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    UNPAID = "unpaid"
    INCOMPLETE = "incomplete"
    PAUSED = "paused"


class ProviderCapabilities(BaseModel):
    """
    Advertises what features a payment provider supports.

    Used by the service layer for graceful degradation when
    a provider doesn't support a requested feature.
    """

    # Core payment features
    supports_checkout_sessions: bool = True
    supports_payment_intents: bool = True
    supports_authorization_capture: bool = False  # Separate auth/capture
    supports_partial_capture: bool = False
    supports_partial_refund: bool = True
    supports_void: bool = True  # Cancel uncaptured payments

    # Customer management
    supports_customers: bool = False
    supports_saved_payment_methods: bool = False

    # Security
    supports_3ds: bool = False
    supports_webhook_signatures: bool = True

    # Subscriptions
    supports_subscriptions: bool = False
    supports_metered_billing: bool = False
    supports_trials: bool = False

    # Advanced features
    supports_split_payments: bool = False  # Marketplace/Connect
    supports_payment_links: bool = False
    supports_invoicing: bool = False

    # Webhook events this provider can emit
    supported_webhook_events: list[NormalizedEventType] = []

    # Provider limitations
    min_amount_cents: int = 50  # Minimum charge amount
    max_amount_cents: Optional[int] = None  # Maximum charge amount


class PaymentResult(BaseModel):
    """Standardized result from payment operations."""

    success: bool
    provider_reference: str
    status: PaymentStatus
    amount_cents: int
    currency: str
    payment_method: Optional[PaymentMethod] = None
    failure_reason: Optional[str] = None
    failure_code: Optional[str] = None
    raw_response: Optional[dict] = None
    # Client secret for frontend SDK (Stripe PaymentIntent, etc.)
    client_secret: Optional[str] = None


class CheckoutSession(BaseModel):
    """Result from creating a checkout session."""

    session_id: str
    checkout_url: str
    expires_at: Optional[str] = None


class RefundResult(BaseModel):
    """Result from refund operations."""

    success: bool
    refund_reference: str
    amount_cents: int
    status: str
    failure_reason: Optional[str] = None


class WebhookEvent(BaseModel):
    """
    Parsed webhook event with normalized type.

    Providers parse their native event format into this structure,
    mapping to NormalizedEventType for consistent handling.
    """

    event_id: str
    event_type: str  # Provider's native event type (e.g., "charge.succeeded")
    normalized_type: NormalizedEventType  # Mapped to standard type
    payment_reference: Optional[str] = None
    customer_reference: Optional[str] = None
    data: dict
    created_at: str


class SubscriptionResult(BaseModel):
    """Standardized subscription result."""

    subscription_id: str
    status: SubscriptionStatus
    customer_id: str
    current_period_start: Optional[str] = None
    current_period_end: Optional[str] = None
    cancel_at_period_end: bool = False
    cancelled_at: Optional[str] = None
    trial_end: Optional[str] = None
    metadata: Optional[dict] = None


class PaymentProvider(ABC):
    """
    Abstract base class for payment providers.

    All payment providers must implement this interface to ensure
    consistent behavior across the application.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Unique identifier for this provider.
        Examples: 'stripe', 'payfast', 'paypal'
        """
        pass

    @property
    @abstractmethod
    def supported_currencies(self) -> list[str]:
        """List of ISO 4217 currency codes supported by this provider."""
        pass

    @property
    @abstractmethod
    def supported_payment_methods(self) -> list[PaymentMethod]:
        """List of payment methods supported by this provider."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """
        Advertise provider capabilities.

        Service layer uses this to check feature support before
        attempting operations that may not be available.

        Example:
            if not provider.capabilities.supports_partial_refund:
                raise ValueError("Provider does not support partial refunds")
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # Checkout / Payment Creation
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def create_checkout_session(
        self,
        amount_cents: int,
        currency: str,
        customer_email: str,
        description: str,
        metadata: dict[str, str],
        success_url: str,
        cancel_url: str,
        payment_methods: Optional[list[PaymentMethod]] = None,
        idempotency_key: Optional[str] = None,
    ) -> CheckoutSession:
        """
        Create a hosted checkout session.

        This redirects the customer to the provider's hosted payment page.
        Use this for PCI compliance - card details never touch your server.

        Args:
            amount_cents: Payment amount in smallest currency unit (cents)
            currency: ISO 4217 currency code (e.g., 'USD', 'ZAR')
            customer_email: Customer's email for receipt
            description: Human-readable payment description
            metadata: Key-value pairs stored with the payment
            success_url: Redirect URL after successful payment
            cancel_url: Redirect URL if customer cancels
            payment_methods: Restrict to specific payment methods
            idempotency_key: Unique key to prevent duplicate operations

        Returns:
            CheckoutSession with URL to redirect customer
        """
        pass

    @abstractmethod
    async def create_payment_intent(
        self,
        amount_cents: int,
        currency: str,
        customer_id: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
        capture: bool = True,
        idempotency_key: Optional[str] = None,
    ) -> PaymentResult:
        """
        Create a payment intent for custom checkout flows.

        Use this when you need more control over the checkout UI
        or are using the provider's client-side SDK.

        Args:
            amount_cents: Payment amount in smallest currency unit
            currency: ISO 4217 currency code
            customer_id: Provider's customer ID (if saved)
            payment_method_id: Saved payment method to charge
            metadata: Key-value pairs stored with the payment
            capture: If False, only authorize (capture later)
            idempotency_key: Unique key to prevent duplicate operations

        Returns:
            PaymentResult with client_secret for frontend
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # Payment Operations
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def capture_payment(
        self,
        payment_reference: str,
        amount_cents: Optional[int] = None,
    ) -> PaymentResult:
        """
        Capture a previously authorized payment.

        Args:
            payment_reference: Provider's payment/intent ID
            amount_cents: Amount to capture (None = full amount)

        Returns:
            PaymentResult with updated status
        """
        pass

    @abstractmethod
    async def cancel_payment(
        self,
        payment_reference: str,
        reason: Optional[str] = None,
    ) -> PaymentResult:
        """
        Cancel an uncaptured payment authorization.

        Args:
            payment_reference: Provider's payment/intent ID
            reason: Cancellation reason for records

        Returns:
            PaymentResult with cancelled status
        """
        pass

    @abstractmethod
    async def refund_payment(
        self,
        payment_reference: str,
        amount_cents: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> RefundResult:
        """
        Refund a captured payment (full or partial).

        Args:
            payment_reference: Provider's payment/intent ID
            amount_cents: Amount to refund (None = full refund)
            reason: Refund reason for records

        Returns:
            RefundResult with refund details
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # Status & Retrieval
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    async def get_payment(
        self,
        payment_reference: str,
    ) -> PaymentResult:
        """
        Retrieve current payment status from provider.

        Args:
            payment_reference: Provider's payment/intent ID

        Returns:
            PaymentResult with current status
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # Webhooks
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        webhook_secret: Optional[str] = None,
    ) -> bool:
        """
        Verify webhook payload authenticity.

        Args:
            payload: Raw request body bytes
            signature: Signature from request headers
            webhook_secret: Secret for verification (if not in config)

        Returns:
            True if signature is valid
        """
        pass

    @abstractmethod
    def parse_webhook_event(
        self,
        payload: bytes,
    ) -> WebhookEvent:
        """
        Parse webhook payload into standardized event.

        Args:
            payload: Raw request body bytes

        Returns:
            WebhookEvent with normalized event data
        """
        pass

    # ─────────────────────────────────────────────────────────────
    # Customer Management (Optional)
    # ─────────────────────────────────────────────────────────────

    async def create_customer(
        self,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> str:
        """
        Create a customer record with the provider.

        Override if provider supports saved customers.

        Returns:
            Provider's customer ID
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support customer management"
        )

    async def get_customer_payment_methods(
        self,
        customer_id: str,
    ) -> list[dict]:
        """
        List saved payment methods for a customer.

        Override if provider supports saved payment methods.

        Returns:
            List of payment method details
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support saved payment methods"
        )

    async def attach_payment_method(
        self,
        customer_id: str,
        payment_method_id: str,
        set_as_default: bool = False,
    ) -> dict:
        """
        Attach a payment method to a customer.

        Override if provider supports saved payment methods.

        Returns:
            Payment method details
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support saved payment methods"
        )

    async def detach_payment_method(
        self,
        payment_method_id: str,
    ) -> bool:
        """
        Detach a payment method from its customer.

        Override if provider supports saved payment methods.

        Returns:
            True if successfully detached
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support saved payment methods"
        )

    # ─────────────────────────────────────────────────────────────
    # Subscriptions (Optional - Future Use)
    # ─────────────────────────────────────────────────────────────

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: Optional[int] = None,
        metadata: Optional[dict[str, str]] = None,
        idempotency_key: Optional[str] = None,
    ) -> SubscriptionResult:
        """
        Create a recurring subscription.

        Override if provider supports subscriptions.
        Check capabilities.supports_subscriptions before calling.

        Args:
            customer_id: Provider's customer ID
            price_id: Provider's price/plan ID
            trial_days: Free trial period (if capabilities.supports_trials)
            metadata: Key-value pairs stored with subscription
            idempotency_key: Unique key to prevent duplicates

        Returns:
            SubscriptionResult with subscription details
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support subscriptions"
        )

    async def cancel_subscription(
        self,
        subscription_id: str,
        cancel_at_period_end: bool = True,
    ) -> SubscriptionResult:
        """
        Cancel a subscription.

        Args:
            subscription_id: Provider's subscription ID
            cancel_at_period_end: If True, cancel at end of billing period

        Returns:
            SubscriptionResult with updated status
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support subscriptions"
        )

    async def get_subscription(
        self,
        subscription_id: str,
    ) -> SubscriptionResult:
        """
        Get current subscription status.

        Returns:
            SubscriptionResult with current details
        """
        raise NotImplementedError(
            f"{self.provider_name} does not support subscriptions"
        )
