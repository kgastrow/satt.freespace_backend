# Payment Integration Flows

Provider-agnostic payment infrastructure supporting multiple providers (Stripe, PayFast, PayPal) with per-organization configuration.

## Architecture Overview

```
API Layer                    Service Layer                   Provider Layer
-----------                  -------------                   --------------
/payments/*          -->     PaymentService          -->     PaymentProvider (ABC)
/payment-methods/*           (business logic)                   |
/payment-settings/*                                             +-- StripeProvider
/webhooks/payments/*         PaymentProviderFactory             +-- PayfastProvider
                             (provider resolution)              +-- PaypalProvider
```

**Key Files:**
| Component | Location |
|-----------|----------|
| Service | `src/services/payments/service.py` |
| Provider ABC | `src/services/payments/base.py` |
| Factory | `src/services/payments/factory.py` |
| Provider Registration | `src/services/payments/providers/__init__.py` |
| Models | `src/models/payment.py`, `src/models/payment_customer.py` |
| CRUD | `src/crud/payment.py` |
| API Endpoints | `src/api/payments.py`, `src/api/payment_methods.py`, `src/api/payment_settings.py` |
| Webhooks | `src/api/webhooks_payments.py` |
| Background Tasks | `src/workers/payment_tasks.py` |

## Payment Service Architecture

### PaymentProvider (Abstract Base Class)

All providers implement `src/services/payments/base.py:PaymentProvider`:

```python
class PaymentProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...          # 'stripe', 'payfast', 'paypal'
    def supported_currencies(self) -> list[str]: ... # ['USD', 'ZAR', 'EUR']
    def supported_payment_methods(self) -> list[PaymentMethod]: ...
    def capabilities(self) -> ProviderCapabilities: ...

    # Core Operations
    async def create_checkout_session(...) -> CheckoutSession: ...
    async def create_payment_intent(...) -> PaymentResult: ...
    async def capture_payment(...) -> PaymentResult: ...
    async def cancel_payment(...) -> PaymentResult: ...
    async def refund_payment(...) -> RefundResult: ...
    async def get_payment(...) -> PaymentResult: ...

    # Webhooks
    def verify_webhook_signature(...) -> bool: ...
    def parse_webhook_event(...) -> WebhookEvent: ...

    # Customer Management (optional)
    async def create_customer(...) -> str: ...
    async def get_customer_payment_methods(...) -> list[dict]: ...
    async def attach_payment_method(...) -> dict: ...
    async def detach_payment_method(...) -> bool: ...

    # Subscriptions (optional, future use)
    async def create_subscription(...) -> SubscriptionResult: ...
    async def cancel_subscription(...) -> SubscriptionResult: ...
```

### Provider Capabilities

Providers advertise supported features via `ProviderCapabilities`:

```python
class ProviderCapabilities(BaseModel):
    supports_checkout_sessions: bool = True
    supports_payment_intents: bool = True
    supports_authorization_capture: bool = False  # Separate auth/capture
    supports_partial_capture: bool = False
    supports_partial_refund: bool = True
    supports_void: bool = True
    supports_customers: bool = False
    supports_saved_payment_methods: bool = False
    supports_3ds: bool = False
    supports_webhook_signatures: bool = True
    supports_subscriptions: bool = False
    min_amount_cents: int = 50
    max_amount_cents: Optional[int] = None
```

**Usage in service layer:**
```python
if not provider.capabilities.supports_partial_refund:
    raise ValueError("Provider does not support partial refunds")
```

### PaymentProviderFactory

Resolves provider instances with credential management:

```python
# System-wide provider (global credentials)
provider = PaymentProviderFactory.get_provider("stripe")

# Organization-specific provider (org credentials or Connect accounts)
provider = await PaymentProviderFactory.get_provider_for_org(
    session, organization_id, provider_name="stripe"
)
```

**Credential Resolution Order:**
1. Organization custom credentials (if configured)
2. Organization Stripe Connect account ID
3. Fall back to system-wide credentials

### PaymentService

Orchestrates business logic between API, providers, and database:

```python
# Create checkout session
result = await PaymentService.create_checkout(
    session, organization_id, user_id,
    amount_cents=1000, currency="USD",
    description="Product purchase",
    success_url="https://app.example.com/success",
    cancel_url="https://app.example.com/cancel",
)
# Returns: {"payment_id": "uuid", "checkout_url": "https://..."}

# Process refund
result = await PaymentService.refund_payment(
    session, organization_id, payment_id,
    amount_cents=500,  # Partial refund, None for full
    reason="Customer request",
    actor_id=admin_user_id,
)
```

## Adding a New Payment Provider

### 1. Create Provider Class

Create `src/services/payments/providers/newprovider.py`:

```python
from src.services.payments.base import (
    PaymentProvider, PaymentMethod, PaymentStatus,
    ProviderCapabilities, PaymentResult, CheckoutSession,
    RefundResult, WebhookEvent, NormalizedEventType,
)

class NewProvider(PaymentProvider):
    def __init__(
        self,
        api_key: Optional[str] = None,
        webhook_secret: Optional[str] = None,
    ):
        self._api_key = api_key or settings.NEW_PROVIDER_API_KEY
        self._webhook_secret = webhook_secret or settings.NEW_PROVIDER_WEBHOOK_SECRET

    @property
    def provider_name(self) -> str:
        return "newprovider"

    @property
    def supported_currencies(self) -> list[str]:
        return ["USD", "EUR", "GBP"]

    @property
    def supported_payment_methods(self) -> list[PaymentMethod]:
        return [PaymentMethod.CARD, PaymentMethod.BANK_TRANSFER]

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_checkout_sessions=True,
            supports_payment_intents=True,
            supports_partial_refund=True,
            supports_customers=True,
            supports_saved_payment_methods=True,
            supports_webhook_signatures=True,
        )

    async def create_checkout_session(
        self, amount_cents: int, currency: str, customer_email: str,
        description: str, metadata: dict[str, str],
        success_url: str, cancel_url: str,
        payment_methods: Optional[list[PaymentMethod]] = None,
        idempotency_key: Optional[str] = None,
    ) -> CheckoutSession:
        # Call provider API
        response = await self._client.create_session(...)
        return CheckoutSession(
            session_id=response.id,
            checkout_url=response.url,
            expires_at=response.expires_at.isoformat(),
        )

    async def refund_payment(
        self, payment_reference: str,
        amount_cents: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> RefundResult:
        response = await self._client.refund(payment_reference, amount_cents)
        return RefundResult(
            success=response.status == "succeeded",
            refund_reference=response.id,
            amount_cents=response.amount,
            status=response.status,
        )

    def verify_webhook_signature(
        self, payload: bytes, signature: str,
        webhook_secret: Optional[str] = None,
    ) -> bool:
        secret = webhook_secret or self._webhook_secret
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def parse_webhook_event(self, payload: bytes) -> WebhookEvent:
        data = json.loads(payload)
        return WebhookEvent(
            event_id=data["id"],
            event_type=data["type"],
            normalized_type=self._map_event_type(data["type"]),
            payment_reference=data.get("payment_id"),
            customer_reference=data.get("customer_id"),
            data=data,
            created_at=data["created_at"],
        )

    def _map_event_type(self, native_type: str) -> NormalizedEventType:
        mapping = {
            "payment.completed": NormalizedEventType.PAYMENT_SUCCEEDED,
            "payment.failed": NormalizedEventType.PAYMENT_FAILED,
            "refund.completed": NormalizedEventType.REFUND_SUCCEEDED,
            # ... map all provider events to normalized types
        }
        return mapping.get(native_type, NormalizedEventType.UNKNOWN)
```

### 2. Register Provider

Update `src/services/payments/providers/__init__.py`:

```python
# NewProvider
if getattr(settings, "NEW_PROVIDER_API_KEY", ""):
    try:
        from .newprovider import NewProvider
        PaymentProviderFactory.register("newprovider", NewProvider)
    except ImportError:
        pass
```

### 3. Add Configuration

Update `src/core/config.py`:

```python
NEW_PROVIDER_API_KEY: str = ""
NEW_PROVIDER_WEBHOOK_SECRET: str = ""
```

### 4. Update Webhook Endpoint

Update `src/api/webhooks_payments.py`:

```python
VALID_PROVIDERS = {"stripe", "payfast", "paypal", "newprovider"}

SIGNATURE_HEADERS = {
    # ... existing
    "newprovider": "x-newprovider-signature",
}
```

### 5. Add Organization Settings (Optional)

If provider supports per-org credentials, update `OrganizationPaymentSettings` model and factory credential extraction.

## Payment Processing Flow

### Checkout Flow (Hosted Payment Page)

```
1. Frontend: User clicks "Pay Now"
         |
         v
2. POST /api/v1/payments/checkout
   {amount_cents: 1000, currency: "USD", success_url: "...", cancel_url: "..."}
         |
         v
3. PaymentService.create_checkout()
   - Generate idempotency key (prevents duplicates)
   - Check for existing payment with same key
   - Get provider via PaymentProviderFactory
   - Call provider.create_checkout_session()
   - Create local Payment record (status: "pending")
   - Create PaymentEvent (type: "checkout.created")
         |
         v
4. Response: {payment_id: "uuid", checkout_url: "https://provider.com/checkout/..."}
         |
         v
5. Frontend: Redirect to checkout_url
         |
         v
6. Customer completes payment on provider's hosted page
         |
         v
7. Provider redirects to success_url or cancel_url
         |
         v
8. Provider sends webhook -> POST /api/v1/webhooks/payments/stripe
   (See Webhook Handling section)
```

### Idempotency

Checkout requests support idempotency to prevent duplicate payments:

```python
# If payment exists with same idempotency_key, return existing checkout info
existing = await payment_crud.get_payment_by_idempotency_key(
    session, organization_id, idempotency_key
)
if existing:
    return {"payment_id": str(existing.id), "checkout_url": ..., "existing": True}
```

## Webhook Handling

### Webhook Endpoint Flow

```
1. POST /api/v1/webhooks/payments/{provider}
         |
         v
2. Validate provider against allowlist (prevents enumeration)
         |
         v
3. Verify signature using provider.verify_webhook_signature()
         |
         v
4. Validate timestamp (replay attack protection)
   - Extract timestamp from header/signature
   - Check within PAYMENTS_WEBHOOK_TOLERANCE_SECONDS
         |
         v
5. Parse event using provider.parse_webhook_event()
         |
         v
6. Enqueue for background processing via ARQ
   -> process_payment_webhook_task
         |
         v
7. Return {"received": True} immediately (< 2 seconds)
```

### Background Webhook Processing

```python
# src/workers/payment_tasks.py
async def process_payment_webhook_task(ctx, provider, event_id, event_type, ...):
    # Reconstruct WebhookEvent
    event = WebhookEvent(...)

    # Process via PaymentService
    await PaymentService.process_webhook_event(session, provider, event)
```

**PaymentService.process_webhook_event():**
1. Find payment by provider_reference
2. Check for duplicate event (idempotency)
3. Map normalized event type to payment status
4. Update payment status if changed
5. Record PaymentEvent for audit trail

### Normalized Event Types

Providers map native events to normalized types for consistent handling:

| Normalized Type | Stripe | PayFast | PayPal |
|----------------|--------|---------|--------|
| `PAYMENT_SUCCEEDED` | `payment_intent.succeeded` | `COMPLETE` | `PAYMENT.CAPTURE.COMPLETED` |
| `PAYMENT_FAILED` | `payment_intent.payment_failed` | `FAILED` | `PAYMENT.CAPTURE.DENIED` |
| `REFUND_SUCCEEDED` | `charge.refunded` | `REFUND` | `PAYMENT.REFUND.COMPLETED` |
| `DISPUTE_CREATED` | `charge.dispute.created` | N/A | `CUSTOMER.DISPUTE.CREATED` |

### Webhook Security

1. **Signature Verification**: Each provider has its own signature scheme
2. **Timestamp Validation**: Reject old webhooks (configurable tolerance)
3. **Provider Allowlist**: Only accept webhooks from known providers
4. **Idempotent Processing**: Track provider_event_id to prevent duplicates
5. **Test Endpoint**: Only available in DEBUG mode

## Error Handling and Refunds

### Refund Flow

```python
result = await PaymentService.refund_payment(
    session, organization_id, payment_id,
    amount_cents=500,  # Partial refund (None for full)
    reason="Customer request",
    actor_id=current_user.id,
)
```

**Validation:**
1. Payment must be in `succeeded` or `partially_refunded` status
2. Refund amount cannot exceed available (original - already refunded)
3. Check provider supports partial refunds if amount specified

**Status Transitions:**
- Full refund: `succeeded` -> `refunded`
- Partial refund: `succeeded` -> `partially_refunded`
- Additional partial: `partially_refunded` -> `partially_refunded` or `refunded`

### Payment Statuses

```python
class PaymentStatus(str, Enum):
    PENDING = "pending"              # Checkout created, awaiting completion
    PROCESSING = "processing"        # Payment being processed
    REQUIRES_ACTION = "requires_action"  # 3DS, redirect needed
    SUCCEEDED = "succeeded"          # Payment captured
    FAILED = "failed"                # Payment failed
    CANCELLED = "cancelled"          # Payment cancelled
    REFUNDED = "refunded"            # Fully refunded
    PARTIALLY_REFUNDED = "partially_refunded"
    DISPUTED = "disputed"            # Chargeback/dispute opened
```

### Reconciliation (Missed Webhooks)

Background task reconciles payments stuck in transient states:

```python
# Runs every 15 minutes via ARQ cron
async def reconcile_pending_payments_task(ctx):
    # Find payments in pending/processing/requires_action for > 30 minutes
    # Sync status with provider
    # Update local records
```

Manual sync available:
```python
await PaymentService.sync_payment_status(session, payment_id)
```

## Security Considerations

### Multi-Tenancy

**CRITICAL**: All payment operations are organization-scoped:

```python
# CRUD always filters by organization_id
payment = await payment_crud.get_payment(session, organization_id, payment_id)

# Exception: webhook processing uses provider_reference (no org context)
payment = await payment_crud.get_payment_by_provider_reference(
    session, provider, provider_reference
)
```

### Credential Security

1. **Never log credentials**: API keys, webhook secrets
2. **Organization credentials**: Stored encrypted in `OrganizationPaymentSettings`
3. **System credentials**: Environment variables only
4. **API responses**: Never expose credentials, only `stripe_connect_configured: bool`

### PCI Compliance

1. **Hosted checkout**: Card details never touch application servers
2. **Payment method storage**: Only non-sensitive display info (last_four, brand)
3. **Provider references**: Store provider's payment method ID, not card details

### Webhook Security

1. **Signature verification**: Always verify before processing
2. **Timestamp validation**: Prevent replay attacks
3. **Provider allowlist**: Reject unknown providers
4. **Test endpoints**: Disabled in production
5. **Idempotent processing**: Prevent duplicate event processing

## API Endpoints

### Payment Operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/payments/checkout` | POST | Create checkout session |
| `/payments` | GET | List payments (paginated) |
| `/payments/{id}` | GET | Get payment details |
| `/payments/{id}/refund` | POST | Refund payment |

### Payment Methods

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/payment-methods` | GET | List saved payment methods |
| `/payment-methods/{id}` | DELETE | Delete payment method |
| `/payment-methods/{id}/default` | POST | Set as default |

### Payment Settings

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/payment-settings` | GET | Get org payment settings |
| `/payment-settings` | PUT | Update settings |
| `/payment-settings/enabled-providers` | GET | List enabled providers |
| `/payment-settings/providers/{name}/capabilities` | GET | Get provider capabilities |
| `/payment-settings/organization/{id}/payments-allowed` | PUT | Enable/disable payments (super admin) |

### Webhooks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/payments/stripe` | POST | Stripe webhook |
| `/webhooks/payments/payfast` | POST | PayFast webhook |
| `/webhooks/payments/paypal` | POST | PayPal webhook |

## Database Models

### Payment

```python
class Payment(Base):
    __tablename__ = "payment"

    id: UUID
    organization_id: UUID  # Multi-tenancy
    user_id: Optional[UUID]
    provider: str  # 'stripe', 'payfast', 'paypal'
    provider_reference: str  # Provider's payment ID
    customer_id: Optional[UUID]  # Link to PaymentCustomer
    idempotency_key: Optional[str]
    amount_cents: int
    currency: str  # ISO 4217
    refunded_amount_cents: int
    status: str
    payment_method: Optional[str]
    description: Optional[str]
    failure_code: Optional[str]
    failure_reason: Optional[str]
    extra_data: Optional[dict]  # Custom metadata
    provider_data: Optional[dict]  # Provider-specific data
    captured_time: Optional[datetime]
```

### PaymentEvent (Audit Trail)

```python
class PaymentEvent(Base):
    __tablename__ = "payment_event"

    id: UUID
    payment_id: UUID
    event_type: str  # 'checkout.created', 'refund.created', etc.
    event_source: str  # 'api', 'webhook', 'system'
    provider_event_id: Optional[str]  # For deduplication
    previous_status: Optional[str]
    new_status: Optional[str]
    payload: dict
    actor_id: Optional[UUID]
    actor_type: Optional[str]  # 'user', 'system', 'webhook'
```

### PaymentCustomer

```python
class PaymentCustomer(Base):
    __tablename__ = "payment_customer"

    id: UUID
    organization_id: UUID
    user_id: Optional[UUID]  # NULL for guest checkout
    provider: str
    provider_customer_id: str
    email: str
    name: Optional[str]
    default_payment_method_id: Optional[UUID]
```

### SavedPaymentMethod

```python
class SavedPaymentMethod(Base):
    __tablename__ = "saved_payment_method"

    id: UUID
    organization_id: UUID
    customer_id: UUID
    provider: str
    provider_payment_method_id: str
    type: str  # 'card', 'bank_account', 'sepa_debit'
    last_four: Optional[str]
    brand: Optional[str]  # 'visa', 'mastercard'
    exp_month: Optional[int]
    exp_year: Optional[int]
    bank_name: Optional[str]
    account_last_four: Optional[str]
    display_name: Optional[str]
    is_default: bool
    is_expired: bool
```

## Testing Payments

### Unit Tests

```python
# tests/service_tests/test_payment_service.py
async def test_create_checkout(session, mock_provider):
    mock_provider.create_checkout_session.return_value = CheckoutSession(
        session_id="cs_test", checkout_url="https://...", expires_at=None
    )

    result = await PaymentService.create_checkout(
        session, org_id, user_id,
        amount_cents=1000, currency="USD",
        description="Test", success_url="...", cancel_url="...",
    )

    assert result["payment_id"]
    assert result["checkout_url"]
```

### Webhook Tests

```python
# tests/api_tests/test_webhooks_payments.py
async def test_stripe_webhook(client, mock_stripe_signature):
    response = await client.post(
        "/api/v1/webhooks/payments/stripe",
        content=b'{"type": "payment_intent.succeeded", ...}',
        headers={"stripe-signature": mock_stripe_signature},
    )
    assert response.status_code == 200
    assert response.json() == {"received": True}
```

### Provider Sandbox Mode

Most providers support sandbox/test mode. Configure via organization settings:

```python
# OrganizationPaymentSettings
payfast_sandbox: bool = True  # Use sandbox environment
paypal_sandbox: bool = True
```
