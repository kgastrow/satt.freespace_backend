# WhatsApp Message Templates

WhatsApp requires pre-approved message templates for business-initiated conversations (messages sent outside the 24-hour customer response window).

## Background

**Error 63016** occurs when sending freeform WhatsApp messages outside the allowed window:
- **User-initiated (24-hour window)**: After a customer messages you, freeform messages are allowed for 24 hours
- **Business-initiated (outside window)**: Must use pre-approved Message Templates with a `content_sid`

## Architecture

The notification system supports WhatsApp templates through:

1. **NotificationTemplate model** (`src/models/notification_template.py`)
   - `provider_template_id`: Stores Twilio's `content_sid` (e.g., `HXb5b62575e6e4ff6129ad7c8efe1f983d`)

2. **NotificationDispatcher** (`src/services/notifications/dispatcher.py`)
   - Detects WhatsApp channel + `provider_template_id` and passes `content_sid` to provider

3. **TwilioWhatsAppProvider** (`src/services/notifications/whatsapp/twilio_wa.py`)
   - Sends messages using Twilio's Content API when `content_sid` is provided

## Setup Guide

### Step 1: Create Template in Twilio

1. Go to **Twilio Console > Messaging > Content Editor**
2. Click **Create new** and select **WhatsApp**
3. Design your template with variables:
   ```
   Hi {{1}}, your appointment is confirmed for {{2}}.
   ```
4. Submit for Meta/WhatsApp approval (24-48 hours)
5. Once approved, copy the **Content SID** (starts with `HX...`)

### Step 2: Create Database Record

Insert a template record with the `provider_template_id`:

```sql
INSERT INTO notification_template (
    id,
    organization_id,  -- NULL for system template, or specific org UUID
    code,
    name,
    channel,
    body_text,
    provider_template_id,
    variables,
    is_active,
    created_time
) VALUES (
    gen_random_uuid(),
    NULL,  -- system-wide template
    'appointment_confirmed',
    'Appointment Confirmation',
    'whatsapp',
    'Hi {1}, your appointment is confirmed for {2}.',  -- preview/fallback only
    'HXb5b62575e6e4ff6129ad7c8efe1f983d',  -- Twilio content_sid
    '{"1": "Customer name", "2": "Appointment date/time"}',
    true,
    NOW()
);
```

### Step 3: Send Using Template

```python
from src.services.notifications.dispatcher import notification_dispatcher

await notification_dispatcher.send_to_user(
    session=session,
    user_id=str(user.id),
    organization_id=str(org.id),
    channel="whatsapp",
    content="",  # ignored when using template with provider_template_id
    template_code="appointment_confirmed",
    template_vars={"1": "John", "2": "Monday 10am"},
)
```

## Variable Format

Twilio uses numbered placeholders `{{1}}`, `{{2}}`, etc. Your `template_vars` must use these numbers as keys:

```python
# Correct - matches Twilio's {{1}}, {{2}}
template_vars={"1": "John", "2": "Monday 10am"}

# Wrong - named variables won't work
template_vars={"name": "John", "date": "Monday 10am"}
```

## Fallback Behavior

When `provider_template_id` is **not set** on a WhatsApp template:
- The system falls back to local rendering using `body_text`
- This only works within the 24-hour conversation window
- Outside the window, messages will fail with error 63016

## Common Template Types

| Template Code | Purpose | Example Variables |
|--------------|---------|-------------------|
| `otp_verification` | Send OTP codes | `{"1": "123456"}` |
| `appointment_reminder` | Remind of upcoming appointments | `{"1": "Dr. Smith", "2": "Tomorrow 2pm"}` |
| `order_confirmation` | Confirm orders | `{"1": "ORD-12345", "2": "$99.00"}` |
| `shipping_update` | Delivery notifications | `{"1": "ORD-12345", "2": "Out for delivery"}` |

## Troubleshooting

### Error 63016: Outside allowed window
- **Cause**: Sending freeform message without template outside 24-hour window
- **Fix**: Use a template with `provider_template_id` set

### Error 63024: Template not approved
- **Cause**: Template is pending approval or was rejected
- **Fix**: Check Twilio Console for template status

### Error 63025: Invalid content variables
- **Cause**: Variables don't match template placeholders
- **Fix**: Ensure `template_vars` keys match `{{1}}`, `{{2}}`, etc.

## Related Files

- `src/models/notification_template.py` - Template model with `provider_template_id`
- `src/services/notifications/dispatcher.py` - Dispatches to correct provider
- `src/services/notifications/whatsapp/twilio_wa.py` - Twilio WhatsApp provider
- `src/crud/notification_template.py` - Template CRUD operations
