# Web Push (VAPID) Deployment Guide

How to turn on browser push notifications. Web push ships in the app but is
**dormant until a VAPID keypair is configured** — nothing crashes, no prompt
appears, and every other notification channel keeps working. This is the
operator procedure for switching it on, verifying it, and running it.

---

## 1. What VAPID is here, and what happens without it

Browsers do not accept push messages from anyone. Each vendor's push service
(Google FCM for Chrome/Edge, Mozilla autopush for Firefox, Apple for Safari)
requires every push request to be signed by a keypair that identifies *this*
server. That keypair is VAPID (Voluntary Application Server Identification).

- The **public key** is handed to the browser when a user subscribes. It is
  baked into the resulting subscription — a subscription created under one
  public key can only be pushed to by the matching private key.
- The **private key** signs every outgoing push. It stays server-side, always.
- A **subject** (contact URI) is included in the signature so a push service
  operator can reach you if your traffic misbehaves.

### Behaviour when unconfigured (the default)

This is a **graceful degrade**, not a failure:

| Surface | Unconfigured behaviour |
|---|---|
| `GET /api/v1/notifications/push/vapid-key` | `503` with `detail_code` `push.not_configured` |
| `WebPushCard` on the notification settings page | The VAPID fetch is the "is push configured?" probe. On 503 the toggle reports `push.error.notConfigured` rather than a generic failure |
| `send_web_push_to_user` | Returns `{"sent": 0, "failed": 0, "pruned": 0, "skipped": true}` and logs `Web push skipped: VAPID private key not configured`. No exception |
| In-app notifications, WebSocket, email, SMS | Completely unaffected |

So "no VAPID" is a safe state. It is also indistinguishable from a healthy
system unless you look — see §6.

---

## 2. Prerequisites

1. **HTTPS.** Service workers and the Push API are secure-context only. The
   single exception is `http://localhost` for local development.

2. **The PWA service worker must be built in.** The push handlers live in
   `app/frontend/public/sw-push.js`, which `VitePWA` pulls into the generated
   worker via `workbox.importScripts`. But `vite.config.ts` sets
   `disable: process.env.VITE_ENABLE_PWA !== 'true'`, and `src/registerSW.ts`
   only registers the worker when `VITE_ENABLE_PWA === 'true'`.

   **`VITE_ENABLE_PWA=true` must be set at frontend BUILD time.** It is a Vite
   build-time variable, not a runtime one — setting it after the fact does
   nothing until you rebuild and redeploy. `app/frontend/.env.example` ships
   `VITE_ENABLE_PWA=false`, so this is easy to miss.

3. **`pywebpush` installed.** It is in `requirements.txt`. The provider imports
   it defensively, so a missing library degrades to a logged skip rather than a
   crash — which also means its absence is silent.

4. **Serving rules.** `sw.js` and `sw-push.js` must be served `no-store` and
   must 404 rather than fall through to `index.html`. See the cache tiers in
   `app/backend/apache_site_config/ayzer_backend.conf`. `importScripts()` on an
   HTML body throws, which aborts installation of the new service worker and
   leaves every client stuck on the previous one — a failure mode with no
   client-side recovery.

---

## 3. Generate a keypair

### Option A — the API (recommended)

`POST /api/v1/notifications/push/providers/web-push/generate` returns a fresh
keypair for preview. It does **not** persist anything; you save it in the next
step. Requires `notification_providers:write`.

### Option B — offline, on the backend host

This reproduces exactly what the server does
(`services/notifications/web_push_config.py::generate_vapid_keypair`). Run it
from `app/backend/`; it touches nothing but stdout:

```bash
cd app/backend && ./.venv/bin/python -c "
import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def b64u(raw): return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')

priv = ec.generate_private_key(ec.SECP256R1())
pub = priv.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print('public_key :', b64u(pub))
print('private_key:', b64u(priv.private_numbers().private_value.to_bytes(32, 'big')))
"
```

### Sanity check the output

| Field | Expected |
|---|---|
| `public_key` | 87 characters, base64url (no `=` padding), starts with `B` |
| `private_key` | 43 characters, base64url (no `=` padding) |

The public key is the uncompressed P-256 point (what the browser calls the
`applicationServerKey`); the private key is the raw 32-byte scalar, which is
the form `pywebpush` expects.

### Do NOT use the `vapid` CLI for the private key

`py-vapid` ships a `vapid` binary in the venv. It emits a **PEM** private key,
which is *not* the raw-scalar format this stack stores. Its printed
"Application Server Key" is a valid public key, so it is useful only to
cross-check one.

---

## 4. Where the keys go

### Route A — SystemConfig, via the API (recommended)

`PUT /api/v1/notifications/push/providers/web-push` with
`{public_key, private_key, subject, purge_subscriptions}`. Requires
`notification_providers:write`. Takes effect without a restart. The private key
is Fernet-encrypted at rest, because the generic SystemConfig key-pattern
matcher does not treat `VAPID_PRIVATE_KEY` as sensitive.

### Route B — `config.json` / environment (requires a restart)

```json
"web_push": {
  "public_key": "B...",
  "private_key": "...",
  "subject": "mailto:ops@example.com"
}
```

### ⚠ Precedence — read before mixing the two

Two resolution paths exist and they do **not** agree:

- The **status/read** path (`get_web_push_config`) resolves
  **database → startup settings → unset** and reports which one won in the
  `source` field (`"database"` / `"settings"` / `"unset"`).
- The **send** path (`WebPushProvider._resolve_keys`) short-circuits: if the
  process-level singleton was constructed with a non-empty
  `settings.VAPID_PRIVATE_KEY`, that key is authoritative and the database
  value is **never consulted**.

Consequence: a private key present in `config.json`/env silently wins over
anything saved through the API — while the status endpoint still reports
`source: "database"`. That looks like a working save that does nothing.

**Configure via exactly one route.** If you use the API, leave
`web_push.private_key` empty/absent in `config.json`. If you pin keys in
`config.json`, treat the API as read-only.

### Public vs private — non-negotiable

- Only `VAPID_PUBLIC_KEY` is ever exposed to a browser, via
  `GET /api/v1/notifications/push/vapid-key` (authentication required).
- The private key is **never** returned by the status endpoint — it reports
  only the boolean `private_key_configured`. The sole endpoint that emits a
  private key is the `generate` preview, which does not persist it.
- The private key is not logged. Keep it out of tickets, screenshots and chat.
  Anyone holding it can push notifications to every subscribed device.

---

## 5. The subject (contact URI)

VAPID requires a `sub` claim in every signature. This implementation sends
`vapid_claims={"sub": <subject>}` on each push.

- Accepted formats, enforced by the request validator: must start with
  `mailto:` or `https://`. Anything else is rejected.
- Default if unset: `mailto:admin@example.com` — change this.

Set it to a **real, monitored** address or URL. Push service operators use it
to contact you about abuse or malformed traffic; a dead address means your
first warning is a block.

---

## 6. Verify it end to end

### 6.1 Server side

```bash
# Unconfigured: 503 with detail_code push.not_configured
curl -i -H "Authorization: Bearer $TOKEN" \
  https://<host>/api/v1/notifications/push/vapid-key

# Configured: 200 {"public_key": "B..."}
# Status (needs notification_providers:read):
curl -s -H "Authorization: Bearer $TOKEN" \
  https://<host>/api/v1/notifications/push/providers/web-push | jq
```

The status response tells you `configured`, `private_key_configured`, `source`
and `active_subscriptions`. `source` is the field that catches a mixed
configuration.

### 6.2 Client side

1. Chrome or Firefox on desktop, or Android. On iOS, install to the Home Screen
   first — see §7.
2. DevTools → Application → Service Workers shows an active worker. If not,
   `VITE_ENABLE_PWA` was not set at build time.
3. Settings → Notifications: turn on **Web push** (the account gate) *and* the
   **Push notifications (this device)** switch (the device gate). Both are
   required; one without the other delivers nothing.
4. Send yourself a notification through the web_push channel. The service
   worker renders `{title, body, url}`; tapping it focuses an existing window
   on that URL or opens one.

### 6.3 "Not configured" vs "configured but failing"

| Symptom | Meaning |
|---|---|
| `vapid-key` → 503 | No keypair at all. Configure one |
| `vapid-key` → 200, toggle still fails | Look at the error line under the switch: `rejected` is a 4xx from `/subscriptions`, `network` is a failed request |
| Toggle succeeds, nothing arrives | Check the three gates in §7, then the dispatch summary counters |
| Every send returns `failed`, never `pruned` | Usually a keypair mismatch: subscriptions were created under a different public key. 403 from the push service is not 404/410, so nothing prunes them. Rotate with `purge_subscriptions: true` |

---

## 7. Operational notes

- **Dead subscriptions self-heal.** When a push endpoint returns `404` or
  `410` (browser uninstalled, profile wiped, permission revoked), the dispatch
  soft-deletes the subscription (`deleted_time`) and counts it under `pruned`.
  Subscriptions missing their `p256dh`/`auth` keys count as `failed` and are
  never sent.
- **Rotation is destructive.** Saving a new keypair invalidates every existing
  subscription. Always pair a rotation with `purge_subscriptions: true`, and
  expect users to re-opt-in before they receive push again.
- **Three independent gates** must all be open for a push to land: (1) a live
  `web_push_subscription` row for the device, (2) the organisation's
  `web_push_enabled` notification setting, (3) the user's own
  `web_push_enabled` channel preference plus the relevant category toggle and
  quiet hours.
- **The endpoint is the device identity.** Registering an endpoint already on
  file reassigns it to whoever is signed in now, rather than adding a second
  live row. Keyed per (user, endpoint) instead, a shared device keeps
  delivering the previous user's notification titles and bodies to the current
  one. Reassignments are audited as `push.subscription_reassigned`.
- **Endpoints are allowlisted.** `services/notifications/push_endpoint.py`
  refuses anything that is not an HTTPS URL at a known browser push service.
  A push endpoint is a URL the *server* POSTs to on a schedule the client
  influences; unvalidated, that is an SSRF primitive.
- **iOS/Safari:** web push only works once the site has been added to the Home
  Screen and launched as an installed PWA. In a plain Safari tab the API is
  absent and the card says so specifically (`push.iosInstall`), not
  "unsupported".
- **Denied permission is sticky.** Once a user denies notifications the app
  cannot re-prompt — they have to reset it in browser site settings.
- **Payload shape** is fixed at `{title, body, url}` and is a contract between
  `services/notifications/web_push_provider.py` and `public/sw-push.js`. Change
  both or neither.
- **Deploying a frontend change?** Keep `VITE_ENABLE_PWA=true` in the build
  environment. Dropping it silently removes the service worker on the next
  deploy and push stops working with no server-side signal.

### Known gap: endpoint rotation

`pushsubscriptionchange` is **not** handled. When a push service retires a
device's endpoint, the browser announces it only to the service worker scope,
and reporting the replacement needs an unauthenticated server route that
authorises the swap by proof-of-possession of the old subscription's `auth`
key. Until that exists, a rotated device goes quiet until its next
authenticated app load re-registers it through `useWebPush` — with the switch
still reading "on" in the meantime.

---

## 8. Troubleshooting

**No prompt, and the device switch is greyed out.**
On iPhone/iPad in a Safari tab this is expected — the card says to add to the
Home Screen. Elsewhere: is the site on HTTPS? Does DevTools → Application →
Service Workers show an active worker (if not: `VITE_ENABLE_PWA` at build
time)? Has the browser permission already been denied?

**The switch animates on, then snaps back.**
Read the error line beneath it. `notConfigured` is a 503 (no keypair),
`rejected` a 4xx from `/subscriptions` (an endpoint the allowlist refused, or
the per-user device cap of 20), `network` a request that never completed,
`denied` a blocked permission.

**Nothing arrives on an installed iOS PWA, but the toggle is on.**
iOS grants push per *installed instance*. A Home Screen install has its own
service worker registration separate from Safari's; subscribing in Safari does
not subscribe the installed app.

---

## 9. Regression cover

- `src/__tests__/integration/pwa-config.integration.test.ts` — asserts the
  worker pulls in `sw-push.js` and that the file exists.
- The push handlers themselves are exercised manually; there is no service
  worker test harness in this repo.
