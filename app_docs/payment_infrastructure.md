# Payment Infrastructure

Multi-tenant, provider-agnostic payment system supporting Stripe, PayFast, PayPal with per-organization configuration.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  API Layer: /payments, /payment-methods, /payment-settings│
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│          PaymentService (orchestration)                  │
└──────────────────┬───────────────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────────────┐
│  PaymentProviderFactory (registration & caching)         │
└──────────────────┬───────────────────────────────────────┘
                   ▼
     ┌─────────────┬─────────────┬─────────────┐
     ▼             ▼             ▼
  Stripe      PayFast        PayPal
```

## Permissions

Two-tier system (both must be `True`):
- **Super Admin**: `payments_allowed` (organization master switch)
- **Org Admin**: `{provider}_enabled` (per-provider toggle)

## Database Models

| Table | Purpose |
|-------|---------|
| `payment` | Core payment records |
| `payment_event` | Audit trail for status changes (deduplication by `provider_event_id`) |
| `payment_customer` | Maps users to provider customer IDs |
| `saved_payment_method` | Stored cards, bank accounts |
| `invoice` | Invoice records |
| `payment_invoice` | Links payments to invoices |
| `organization_payment_settings` | Per-org provider configuration |

Relationships: `Organization ──1:1──▶ OrganizationPaymentSettings ──1:N──▶ PaymentCustomer ──1:N──▶ SavedPaymentMethod ──1:N──▶ Payment ──1:N──▶ PaymentEvent`

## API Endpoints

### Payment Operations (`/api/v1/payments`)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/checkout` | POST | User | Create hosted checkout session |
| `/` | GET | User | List organization payments |
| `/{id}` | GET | User | Get payment details |
| `/{id}/refund` | POST | User | Full or partial refund |

### Payment Methods (`/api/v1/payment-methods`)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | User | List saved methods |
| `/{id}` | DELETE | User | Delete saved method |
| `/{id}/default` | POST | User | Set as default |

### Payment Settings (`/api/v1/payment-settings`)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | User | Get org settings (read-only) |
| `/` | PUT | `organization:write` | Update settings |
| `/enabled-providers` | GET | User | List enabled providers |
| `/providers/{name}/capabilities` | GET | User | Get provider capabilities |
| `/organization/{id}/payments-allowed` | PUT | Super Admin | Enable/disable payments |
| `/organization/{id}` | GET | Super Admin | View any org settings |

### Webhooks (`/api/v1/webhooks/payments`)
| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/{provider}` | POST | Signature | Receive provider webhooks |
| `/{provider}/test` | GET | None | Test webhook reachability |

## Implementing a New Payment Provider

### Step 1: Create Provider Class

Create `src/services/payments/providers/{provider_name}.py`:

```python
from src.services.payments.base import PaymentProvider, PaymentMethod, ProviderCapabilities, PaymentStatus, PaymentResult, CheckoutSession, RefundResult, WebhookEvent, NormalizedEventType

class MyProvider(PaymentProvider):
    def __init__(self, api_key: Optional[str] = None, webhook_secret: Optional[str] = None, sandbox: bool = True):
        from src.core.config import settings
        self._api_key = api_key or getattr(settings, "MYPROVIDER_API_KEY", "")
        self._webhook_secret = webhook_secret or getattr(settings, "MYPROVIDER_WEBHOOK_SECRET", "")
        self._sandbox = sandbox

    @property
    def provider_name(self) -> str:
        return "myprovider"

    @property
    def supported_currencies(self) -> list[str]:
        return ["USD", "EUR", "GBP"]

    @property
    def supported_payment_methods(self) -> list[PaymentMethod]:
        return [PaymentMethod.CARD]

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_checkout_sessions=True,
            supports_payment_intents=True,
            supports_partial_refund=True,
            supports_customers=True,
            supports_saved_payment_methods=True,
            supports_webhook_signatures=True,
            min_amount_cents=50,
            supported_webhook_events=[
                NormalizedEventType.PAYMENT_SUCCEEDED,
                NormalizedEventType.PAYMENT_FAILED,
                NormalizedEventType.REFUND_SUCCEEDED,
            ],
        )

    async def create_checkout_session(self, amount_cents: int, currency: str, customer_email: str, description: str, metadata: dict[str, str], success_url: str, cancel_url: str, payment_methods: Optional[list[PaymentMethod]] = None, idempotency_key: Optional[str] = None) -> CheckoutSession:
        response = await self._call_api("checkout/sessions", method="POST", data={...}, idempotency_key=idempotency_key)
        return CheckoutSession(session_id=response["id"], checkout_url=response["url"], expires_at=response.get("expires_at"))

    async def create_payment_intent(self, amount_cents: int, currency: str, customer_id: Optional[str] = None, payment_method_id: Optional[str] = None, metadata: Optional[dict[str, str]] = None, capture: bool = True, idempotency_key: Optional[str] = None) -> PaymentResult:
        # Implement provider API call

    async def capture_payment(self, payment_reference: str, amount_cents: Optional[int] = None) -> PaymentResult:
        # Implement or raise NotImplementedError

    async def cancel_payment(self, payment_reference: str, reason: Optional[str] = None) -> PaymentResult:
        # Implement or raise NotImplementedError

    async def refund_payment(self, payment_reference: str, amount_cents: Optional[int] = None, reason: Optional[str] = None) -> RefundResult:
        # Implement provider API call

    async def get_payment(self, payment_reference: str) -> PaymentResult:
        # Implement provider API call

    def verify_webhook_signature(self, payload: bytes, signature: str, webhook_secret: Optional[str] = None) -> bool:
        secret = webhook_secret or self._webhook_secret
        # Implement signature verification per provider docs

    def parse_webhook_event(self, payload: bytes) -> WebhookEvent:
        import json
        data = json.loads(payload)
        event_mapping = {
            "payment.completed": NormalizedEventType.PAYMENT_SUCCEEDED,
            "payment.failed": NormalizedEventType.PAYMENT_FAILED,
            "refund.completed": NormalizedEventType.REFUND_SUCCEEDED,
        }
        return WebhookEvent(
            event_id=data["id"],
            event_type=data["type"],
            normalized_type=event_mapping.get(data["type"], NormalizedEventType.UNKNOWN),
            payment_reference=data.get("payment_id"),
            customer_reference=data.get("customer_id"),
            data=data,
            created_at=data["created_at"],
        )
```

### Step 2: Register Provider

In `src/services/payments/providers/__init__.py`:

```python
from src.services.payments.factory import PaymentProviderFactory
from .myprovider import MyProvider

PaymentProviderFactory.register("myprovider", MyProvider)
```

### Step 3: Add Configuration

In `src/core/config.py`:

```python
MYPROVIDER_API_KEY: str = ""
MYPROVIDER_WEBHOOK_SECRET: str = ""
MYPROVIDER_SANDBOX: bool = True
```

### Step 4: Add Organization Settings

In `src/models/organization_payment_settings.py`:

```python
myprovider_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
myprovider_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
myprovider_webhook_secret: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
myprovider_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

### Step 5: Update Factory Credential Methods

In `src/services/payments/factory.py`:

```python
@classmethod
def _has_org_credentials(cls, provider: str, org_settings) -> bool:
    elif provider == "myprovider":
        return bool(org_settings.myprovider_api_key)

@classmethod
def _extract_org_credentials(cls, provider: str, org_settings) -> dict:
    elif provider == "myprovider":
        return {
            "api_key": org_settings.myprovider_api_key or getattr(settings, "MYPROVIDER_API_KEY", ""),
            "webhook_secret": org_settings.myprovider_webhook_secret or getattr(settings, "MYPROVIDER_WEBHOOK_SECRET", ""),
            "sandbox": org_settings.myprovider_sandbox,
        }
```

### Step 6: Update CRUD Provider Check

In `src/crud/organization_payment_settings.py`:

```python
async def is_provider_enabled(...) -> bool:
    elif provider == "myprovider":
        return settings.myprovider_enabled
```

### Step 7: Add Webhook Signature Header

In `src/api/webhooks_payments.py`:

```python
SIGNATURE_HEADERS = {
    "stripe": "stripe-signature",
    "payfast": "pf-request-signature",
    "paypal": "paypal-transmission-sig",
    "myprovider": "x-myprovider-signature",
}
```

### Step 8: Create Migration

```bash
cd app/backend
make migrate-new msg="add_myprovider_payment_settings"
make migrate
```

## Webhook Processing

Flow: Receive → Verify signature → Parse to `WebhookEvent` → Normalize event type → `PaymentService.process_webhook_event()` → Update database → Respond 200

Event deduplication: Checked by `provider_event_id` in `payment_event` table via `is_event_already_processed()`

### Normalized Event Types

| Type | Description |
|------|-------------|
| `payment.succeeded` | Payment completed successfully |
| `payment.failed` | Payment failed |
| `payment.cancelled` | Payment cancelled |
| `refund.succeeded` | Refund completed |
| `checkout.completed` | Hosted checkout completed |
| `payment_method.attached` | Card saved to customer |

## Payment Statuses

```python
PENDING, PROCESSING, REQUIRES_ACTION, SUCCEEDED, FAILED, CANCELLED, REFUNDED, PARTIALLY_REFUNDED, DISPUTED
```

## Testing

```bash
cd app/backend
pytest tests/crud_tests/test_payment_crud.py \
       tests/crud_tests/test_payment_settings_crud.py \
       tests/service_tests/test_payment_service.py \
       tests/api_tests/test_payment_api.py \
       tests/api_tests/test_payment_methods_api.py \
       tests/api_tests/test_payment_settings_api.py -v
```

Coverage: 59 CRUD tests, 27 service tests (mocked providers), 46 API tests (endpoints, permissions, org isolation)

Key fixtures: `payment_settings`, `payment_customer`, `saved_payment_method`, `test_payment`

## Security

1. **PCI Compliance**: Use hosted checkout - never store card details
2. **Webhook Signatures**: Always verify before processing
3. **Credential Storage**: Encrypt provider API keys at rest
4. **Tenant Isolation**: All queries filter by `organization_id`
5. **Soft Deletes**: Use `deleted_time` for audit trail

## Environment Variables

```bash
# System defaults (fallback when org has no custom credentials)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
PAYFAST_MERCHANT_ID=...
PAYFAST_MERCHANT_KEY=...
PAYFAST_PASSPHRASE=...
PAYPAL_CLIENT_ID=...
PAYPAL_CLIENT_SECRET=...
PAYMENTS_DEFAULT_PROVIDER=stripe
```

## File Reference

| File | Purpose |
|------|---------|
| `src/api/payments.py` | Payment endpoints |
| `src/api/payment_methods.py` | Saved methods endpoints |
| `src/api/payment_settings.py` | Settings endpoints |
| `src/api/webhooks_payments.py` | Webhook endpoints |
| `src/services/payments/base.py` | Provider interface |
| `src/services/payments/factory.py` | Provider factory & credential handling |
| `src/services/payments/service.py` | Business logic & webhook processing |
| `src/models/payment.py` | Payment, Event, Invoice models |
| `src/models/payment_customer.py` | Customer, SavedMethod models |
| `src/models/organization_payment_settings.py` | Settings model |
| `src/crud/payment.py` | Payment CRUD |
| `src/crud/organization_payment_settings.py` | Settings CRUD |
| `src/serialisers/payment.py` | Request/response models |
| `src/serialisers/payment_settings.py` | Settings serializers |
