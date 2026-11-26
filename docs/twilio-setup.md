# Twilio SMS & WhatsApp Setup Guide

This guide covers configuring Twilio for SMS and WhatsApp notifications, including delivery status webhooks.

## Prerequisites

- Twilio account ([sign up](https://www.twilio.com/try-twilio))
- A Twilio phone number with SMS capability
- For WhatsApp: Twilio Sandbox or approved WhatsApp Business number
- Your application's public URL (for webhooks)

## 1. Twilio Console Setup

### Get Your Credentials

1. Log in to [Twilio Console](https://console.twilio.com/)
2. From the dashboard, copy:
   - **Account SID** (starts with `AC`)
   - **Auth Token** (click to reveal)

### Get a Phone Number

1. Go to **Phone Numbers** → **Manage** → **Buy a number**
2. Select a number with SMS capability
3. Copy the phone number in E.164 format (e.g., `+14155551234`)

### WhatsApp Sandbox (Development)

1. Go to **Messaging** → **Try it out** → **Send a WhatsApp message**
2. Follow instructions to join the sandbox (send "join <code>" to the sandbox number)
3. Note the sandbox number: `whatsapp:+14155238886`

## 2. Backend Configuration

Add Twilio settings to your `config.json`:

```json
{
  "twilio": {
    "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "auth_token": "your-auth-token",
    "sms_from": "+14155551234",
    "whatsapp_from": "whatsapp:+14155238886"
  },
  "notifications": {
    "default_sms_provider": "twilio_sms",
    "default_whatsapp_provider": "twilio"
  },
  "public_url_backend": "https://api.your-domain.com",
  "public_url_frontend": "https://your-domain.com"
}
```

| Setting | Description |
|---------|-------------|
| `account_sid` | Your Twilio Account SID |
| `auth_token` | Your Twilio Auth Token (used for API calls and webhook verification) |
| `sms_from` | Your Twilio phone number for SMS |
| `whatsapp_from` | Your WhatsApp sender (sandbox or business number) |
| `public_url_backend` | Origin serving this API under `/api/v1`. Required for webhooks - Twilio signs the exact URL string, so this must match the URL Twilio calls. See [public-url-split.md](./public-url-split.md). |

## 3. Webhook Configuration

The application automatically registers a status callback URL when sending messages. Twilio will POST status updates to:

```
{PUBLIC_URL_BACKEND}/api/v1/webhooks/notifications/twilio/sms-status
```

### How It Works

1. **Message sent** → Status: `queued`
2. **Twilio processes** → Webhook receives: `sending`
3. **Carrier accepts** → Webhook receives: `sent`
4. **Delivered to phone** → Webhook receives: `delivered`
5. **If failed** → Webhook receives: `failed` or `undelivered`

The webhook automatically updates the notification record in your database.

### Manual Webhook Configuration (Optional)

If you need to configure webhooks manually in Twilio Console:

1. Go to **Phone Numbers** → **Manage** → **Active numbers**
2. Click your number
3. Under **Messaging Configuration**:
   - Set **A MESSAGE COMES IN** webhook if handling inbound (optional)
4. For status callbacks, they're set per-message (handled automatically by the app)

### Webhook Security

The webhook endpoint uses Twilio's official `RequestValidator` from the SDK (as recommended by [Twilio's security docs](https://www.twilio.com/docs/usage/webhooks/webhooks-security)):

- Twilio signs each request with `X-Twilio-Signature` header (HMAC-SHA1)
- The SDK's `RequestValidator.validate()` verifies the signature
- Invalid signatures return `403 Forbidden`
- If `TWILIO_AUTH_TOKEN` is not set, signature verification is skipped (development only)

**Important**: Always use HTTPS in production. Twilio rejects self-signed certificates.

## 4. Testing

### Send a Test SMS

```bash
curl -X POST "http://localhost:8000/api/v1/notifications/send" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "channel": "sms",
    "user_id": "user-uuid",
    "content": "Test message"
  }'
```

### Verify Status Updates

1. Send an SMS notification
2. Check the notification status in the database or admin UI
3. Status should progress: `queued` → `sent` → `delivered`

### Check Webhook Logs

Watch your application logs for webhook activity:
```
Twilio SMS status callback: sid=SMxxxx, status=sent
Updated notification xxxx status to sent
```

## 5. Production Checklist

- [ ] Use production Twilio credentials (not test credentials)
- [ ] Set `public_url_backend` to your production API origin (HTTPS required). The single `public_url` key is deprecated - see [public-url-split.md](./public-url-split.md)
- [ ] Verify Auth Token is set (enables webhook signature verification)
- [ ] For WhatsApp: Apply for WhatsApp Business API access
- [ ] Monitor delivery rates in Twilio Console
- [ ] Set up Twilio error alerts for failed messages

## Troubleshooting

### Messages stuck in "queued"

- **Cause**: Webhook not receiving updates
- **Fix**: Verify `public_url_backend` is publicly accessible and correctly configured

### Webhook returns 403

- **Cause**: Invalid signature
- **Fix**: Ensure `TWILIO_AUTH_TOKEN` in config matches your Twilio Auth Token

### WhatsApp messages fail

- **Cause**: Recipient hasn't opted in to sandbox
- **Fix**: Have recipient send join message to sandbox, or use approved business number

### "No SMS sender number configured"

- **Cause**: Missing `sms_from` in config
- **Fix**: Add your Twilio phone number to `twilio.sms_from`

## Status Reference

| Twilio Status | Internal Status | Meaning |
|---------------|-----------------|---------|
| `accepted` | `queued` | Twilio accepted the message |
| `queued` | `queued` | Message queued for sending |
| `sending` | `queued` | Message being sent to carrier |
| `sent` | `sent` | Carrier accepted the message |
| `delivered` | `delivered` | Delivered to recipient's device |
| `undelivered` | `failed` | Carrier couldn't deliver |
| `failed` | `failed` | Message failed to send |
| `read` | `delivered` | WhatsApp: recipient read the message |
