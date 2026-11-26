# Notification System Patterns

Multi-channel notification system with templates, user preferences, and bulk messaging.

## Overview

| Feature | Details |
|---------|---------|
| Channels | Email, SMS, WhatsApp, In-App |
| Providers | SMTP, SendGrid (email); Twilio, AWS SNS (SMS); Twilio (WhatsApp) |
| Scope | Organization-scoped + system-wide (org_id=NULL) |
| Processing | Async via ARQ background workers |

**Core Principles:**
- Always filter by `organization_id` (except system notifications)
- Check user preferences before sending
- Use soft deletes (`deleted_time`)
- Log all notifications with status tracking

## Models

All models in `app/backend/src/models/`:

| Model | Key Fields |
|-------|------------|
| `NotificationTemplate` | `organization_id` (NULL=system), `code`, `channel`, `body_text`, `body_html`, `subject`, `provider_template_id` |
| `Notification` | `organization_id`, `user_id`, `status`, `recipient`, `provider_message_id`, `extra_data` |
| `UserNotification` | `user_id`, `title`, `body`, `link`, `category_id`, `read_time` (for in-app) |
| `BulkNotification` | `organization_id`, `status`, `total_recipients`, `sent_count`, `failed_count`, `extra_data` |
| `OrganizationNotificationSettings` | Channel enabled flags, `notification_retention_days` |
| `UserNotificationPreference` | Channel enabled flags, quiet hours settings |
| `NotificationCategory` | `code`, `user_configurable` (false=mandatory) |

Categories are seeded as **system** rows (`organization_id IS NULL`) by
`seed_default_notification_categories`, run on a deployed environment via
`app/backend/scripts/seed_maintenance.py`. Until those rows exist the whole
category layer is inert: `_get_category()` returns `None`, so no per-category
opt-out is enforceable and no mandatory-category bypass applies. The seeded codes
are exactly `account`, `phone_verification` (both mandatory) and `onboarding`,
`marketing` (both user-configurable; `marketing` is the unsubscribe target).

**Notification Status Flow:** `pending` -> `queued` -> `sent` -> `delivered` / `bounced`

`skipped` and `failed` are reached **without** passing through `sent`: `skipped`
from the preference check, `failed` from "no provider available" - both before
any send is attempted.

## Services Architecture

```
app/backend/src/services/notifications/
├── base.py              # NotificationProvider ABC, NotificationResult dataclass
├── dispatcher.py        # Main dispatcher (send_to_user, send_notification, send_in_app_notification)
├── preference_checker.py # User preference validation, batch_load_preferences
├── template_renderer.py # {variable} substitution, XSS protection
├── bulk_processor.py    # Bulk notification handling with rate limiting
├── unsubscribe.py       # JWT token generation for unsubscribe links
├── email_provider.py    # EmailProvider - REFUSES to send without an org email config
├── sendgrid_provider.py # SendGrid API provider
├── in_app_provider.py   # DB persistence + WebSocket broadcasting
├── sms/
│   ├── base.py          # SMSProvider base class with E.164 validation
│   ├── twilio_sms.py    # Twilio SMS implementation
│   └── aws_sns.py       # AWS SNS SMS implementation
└── whatsapp/twilio_wa.py # Twilio WhatsApp with Content API support
```

### NotificationDispatcher

The singleton `notification_dispatcher` uses **lazy initialization** - providers are only loaded on first use via `_ensure_initialized()`. This avoids import errors when optional dependencies (Twilio, aioboto3) are not installed.

**Email provider auto-selection** (in `get_email_provider()`):
1. Calls `get_effective_email_config(session, organization_id)` to get org settings
2. `provider == "sendgrid"` AND a usable `sendgrid_api_key` -> SendGrid
3. `provider == "sendgrid"` but the key is missing or undecryptable -> returns
   `None`. It does **not** downgrade to SMTP: that would send over completely
   different infrastructure, from the platform's sender, and record it as
   `provider="smtp", status="sent"`.
4. Any other provider -> `EmailProviderWrapper` with the org's SMTP config
5. Config resolution raises -> returns `None`, same reasoning as 3

A `None` provider is not a silent no-op: `send_notification` records the
notification with `status="failed"` and
`error_message="No provider available for channel: email"`.

### Provider Interface

```python
from src.services.notifications.base import NotificationProvider, NotificationResult

@dataclass
class NotificationResult:
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None
    status: str = "sent"  # 'sent', 'queued', 'failed'
    metadata: dict[str, Any] = field(default_factory=dict)

class NotificationProvider(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def channel(self) -> str: ...

    @abstractmethod
    async def send(self, recipient: str, message: str, subject: str | None = None,
                   html_message: str | None = None, metadata: dict | None = None) -> NotificationResult: ...

    @abstractmethod
    async def check_delivery_status(self, message_id: str) -> str: ...
```

### SMS Provider Extension

```python
class SMSProvider(NotificationProvider, ABC):
    def validate_phone_number(self, phone: str) -> bool:
        """Validate E.164 format (e.g., +14155552671)."""

    @property
    @abstractmethod
    def max_message_length(self) -> int: ...

    @property
    @abstractmethod
    def supports_sender_id(self) -> bool: ...
```

### Preference Resolution Order

1. **Mandatory check**: Category `user_configurable=False` -> Always send
2. **Organization check**: Channel enabled for org?
3. **User global check**: User disabled channel?
4. **User category check**: User disabled category for channel?
5. **Quiet hours check**: Within quiet hours AND not urgent?

## Background Workers

```python
# app/backend/src/workers/tasks.py
send_notification_task(notification_id)       # Process single notification
process_bulk_notification_task(bulk_id)       # Process bulk batch (100/batch)
check_delivery_status_task(notification_id)   # Poll provider status
cleanup_old_notifications_task()              # Cron: cleanup past retention
```

## Template Rendering

```python
from src.services.notifications.template_renderer import template_renderer

# {variable} syntax (single braces)
body = template_renderer.render("Hello {user_name}!", {"user_name": "John"})

# HTML with XSS protection
html = template_renderer.render_html("<p>Hello {name}</p>", {"name": "John"}, escape_html=True)

# Validation
missing = template_renderer.get_missing_variables("Hello {name} from {city}!", {"name": "Alice"})
# Returns ["city"]
```

## In-App Notifications

Flow:
1. Save to `user_notifications` table via `create_user_notification()` CRUD
2. Broadcast via WebSocket (`message_broadcaster.send_to_user()`) - fire-and-forget
3. If user offline, notification persists for later retrieval

**WebSocket Payload:**
```python
{
    "type": "notification",
    "payload": {
        "notification": {
            "id": "uuid",
            "title": "New Message",
            "body": "You have a new message",
            "link": "/messages/123",
            "category_id": "uuid" | None,
            "read_time": None,
            "created_time": "2024-01-15T10:30:00Z"
        }
    }
}
```

## Security

| Concern | Mitigation |
|---------|------------|
| Credentials | Encrypt provider config, mask in API responses |
| Rate limiting | Per-provider limits (50/sec default for bulk) |
| Unsubscribe | JWT tokens with 30-day expiry, RFC 8058 List-Unsubscribe headers. The human page is `{PUBLIC_URL_FRONTEND}/unsubscribe?token=…` (SPA route); the one-click POST target is `{PUBLIC_URL_BACKEND}/api/v1/notifications/unsubscribe/one-click`. Unsubscribe is the one feature that uses **both** origins. |
| Multi-tenancy | Always filter by organization_id |
| XSS Prevention | HTML escaping in template_renderer.render_html() |
| Input Validation | E.164 phone validation for SMS |

## Common Usage

### Send Notification to User (High-Level)

```python
from src.services.notifications.dispatcher import notification_dispatcher

result = await notification_dispatcher.send_to_user(
    session=session,
    user_id=user_id,
    organization_id=org_id,
    channel="email",  # 'email', 'sms', 'whatsapp', 'in_app'
    content="Fallback content if no template",
    category_code="account",
    is_urgent=False,
    template_code="welcome_email",
    template_vars={"user_name": "John"},
    subject="Welcome!",
)
```

### Send In-App Notification

```python
result = await notification_dispatcher.send_in_app_notification(
    session=session,
    user_id=user_id,
    organization_id=org_id,
    title="New Message",
    body="You have a new message from Admin",
    category_code="account",
    link="/messages/123",
)
```

### Batch Preference Loading (Bulk Notifications)

```python
from src.services.notifications.preference_checker import preference_checker

# Load preferences for all recipients in one query
pref_map = await preference_checker.batch_load_preferences(
    session, user_ids=recipient_ids, organization_id=org_id
)

# Check each recipient using cached data (no additional DB queries)
for user_id in recipient_ids:
    pref_data = pref_map.get(user_id)
    result = preference_checker.check_can_send_with_cached_prefs(
        channel="email",
        pref_data=pref_data,
        category_is_mandatory=False,
        is_urgent=False
    )
```

### Create Bulk Notification

```python
# BulkNotification.extra_data structure:
extra_data = {
    "recipient_filters": {
        # Filters combine with AND; each one only NARROWS. Omit them all to
        # select every user in the organization.
        "user_ids": ["uuid1", "uuid2"],
        "role_ids": ["role-uuid"],
        "exclude_user_ids": ["uuid3"],   # applied last, always wins
        "verified_contact_only": True,   # channel-aware, see below
    },
    "category_code": "marketing",
    "is_urgent": False,
}
# Throttled to 50 notifications/second.
#
# KNOWN MISMATCH: bulk_processor.py reads
# `getattr(settings, "NOTIFICATION_BULK_RATE_LIMIT", 50)`, but no such field
# exists on Settings - the declared setting is BULK_RATE_LIMIT_PER_SECOND
# (config.py, loaded from the `notifications` config block). Neither key
# currently changes the throttle: it is always the hard-coded 50. Do not
# document either as a working knob until the two names are reconciled.
```

`RecipientFilter` sets `extra="forbid"`, so the API rejects anything outside
`user_ids`, `role_ids`, `exclude_user_ids` and `verified_contact_only` with a
422. The legacy keys `specific_user_ids`, `role` (a role NAME), `all_users:
false` and `email_verified_only` are still READ back out of already-persisted
`extra_data` rows, but are not accepted on new input - except
`email_verified_only`, which is translated to `verified_contact_only` with a
deprecation warning rather than rejected.

**Per-channel verification.** `verified_contact_only` (default `True`) checks the
contact column the bulk's **own channel** uses:

| channel | column checked |
|---------|----------------|
| `email` | `User.email_verified` |
| `sms`, `whatsapp` | `User.phone_verified` |
| `in_app` | nothing to verify |

An unknown channel applies no verification filter and logs a warning.
`BulkProcessor.get_recipients()` and `count_recipients()` both take `channel` as
a **required** argument - deliberately not defaulted, so a forgotten argument is
a `TypeError` rather than a silent fallback to email semantics.

```python
```

## Gotchas

1. **WhatsApp templates**: Business-initiated messages require `provider_template_id` (Twilio content_sid). Without it, messages outside the 24-hour window will fail.

2. **Email provider config**: Store org email settings via `OrganizationEmailSettings` model. Set `provider="sendgrid"` AND a decryptable `sendgrid_api_key` for SendGrid; `provider="smtp"` uses the org's SMTP settings. Selecting `sendgrid` without a usable key records the notification as `failed` - it never falls back to SMTP or to the platform defaults.

3. **check_delivery_status is abstract**: The base `NotificationProvider.check_delivery_status()` is abstract and must be implemented. Email SMTP returns "unknown".

4. **In-app WebSocket is non-blocking**: WebSocket broadcast failures do not fail the notification - it's already persisted to DB.

5. **Bulk cancellation via status field**: Set `bulk_notification.status = "cancelled"` - processor checks this before each batch.
