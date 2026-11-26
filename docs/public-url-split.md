# Public URL split: `public_url_frontend` vs `public_url_backend`

## Why

There used to be one setting, `public_url`, and it meant two incompatible
things depending on which module read it:

- Code that mailed a link to a human treated it as the **origin serving the
  SPA** — password-reset, invitation and unsubscribe links are all client-side
  routes in `app/frontend/src/router.tsx`, not API routes.
- Code that talked to a third-party system treated it as the **origin serving
  the API** — Twilio computes its webhook signature over the exact URL string,
  so a URL rebuilt from the wrong origin fails verification on every callback.

Its default was `http://localhost:8000`, the backend port. In local development
every emailed link therefore landed on a host that does not serve the frontend
bundle.

It is now two settings.

## The two settings

| Setting | config.json key | Default | Meaning |
| --- | --- | --- | --- |
| `PUBLIC_URL_FRONTEND` | `public_url_frontend` | `http://localhost:5173` | Origin serving the SPA bundle. |
| `PUBLIC_URL_BACKEND` | `public_url_backend` | `http://localhost:8000` | Origin serving this API under `/api/v1`. |

The frontend default matches the Vite dev server (`app/frontend/vite.config.ts`
falls back to port 5173; `.ports.env` `FRONTEND_PORT` overrides it there). The
backend default matches `SERVER_PORT`.

### What uses the FRONTEND origin

Everything a **person** clicks. Each of these is a client-side route:

| URL | Built in |
| --- | --- |
| `{frontend}/reset-password?token=…` | `src/api/auth.py`, `src/api/users.py` |
| `{frontend}/register?invite_token=…` | `src/api/invitation.py` |
| `{frontend}/unsubscribe?token=…` | `src/services/notifications/unsubscribe.py` |
| `{frontend}/oauth/callback` (SSO `redirect_uri` fallback) | `src/api/sso.py` |

The SSO one is worth spelling out: an OAuth `redirect_uri` is where the provider
sends the user's **browser**, and that lands on the SPA page `/oauth/callback`,
which then calls `GET /api/v1/sso/{provider}/callback` with the code. It is not
an API path. (In practice you still set `sso.google_redirect_uri` explicitly,
because the value has to byte-match a URI registered in Google Cloud Console —
the fallback only keeps an unconfigured deployment pointing somewhere real.)

### What uses the BACKEND origin

Everything a **machine** calls or signs:

| URL | Built in |
| --- | --- |
| `{backend}/api/v1/webhooks/notifications/twilio/sms-status` (signature reconstruction) | `src/api/webhooks_notifications.py` |
| the same path handed to Twilio as `status_callback` | `src/services/notifications/dispatcher.py` |
| `{backend}/api/v1/notifications/unsubscribe/one-click` (RFC 8058 POST target) | `src/services/notifications/unsubscribe.py` |
| `{backend}/api/v1/files/serve/…` and `/api/v1/files/upload` | `main.py`, `src/workers/settings.py` via `src/services/files/local_storage.py` |

Note that unsubscribe uses **both**: the footer link a person clicks is the
frontend page, while the `List-Unsubscribe` header a mailbox provider POSTs to
is the backend endpoint.

## What to put in your config.json

### Single origin (one host fronts both, e.g. `https://app.example.com` with
`/api` proxied to the backend)

Set both to the same value:

```json
{
  "public_url_frontend": "https://app.example.com",
  "public_url_backend": "https://app.example.com"
}
```

### Split origins (the SPA on one host, the API on another — this is what
`app/backend/deploy/nginx.conf` sets up)

```json
{
  "public_url_frontend": "https://app.example.com",
  "public_url_backend": "https://api.example.com"
}
```

Whatever you set as the frontend origin must also be an allowed CORS origin
(`cors.allowed_origins`) when the two differ.

### Local development

The defaults are already right; nothing to set. If `.ports.env` sets
`BACKEND_PORT`, the loader rewrites the port in `public_url_backend` (and in the
deprecated `public_url`) only — it never touches `public_url_frontend`, whose
port comes from `FRONTEND_PORT` and is read by Vite, not by the backend.

## Upgrading an existing deployment

`public_url` still works. If it is set and neither new key is, it back-fills
**both** origins — the exact behaviour the deployment had before the split — and
logs a warning at startup:

```
DEPRECATED: 'public_url' (PUBLIC_URL) is deprecated and will be removed. It has
been applied to both PUBLIC_URL_FRONTEND and PUBLIC_URL_BACKEND (…). Set
'public_url_frontend' … and 'public_url_backend' … explicitly.
```

So nothing silently re-points. To migrate, replace the one key with the two.

If you set one new key and leave `public_url`, the old key fills only the gap
(and still warns). The `PUBLIC_URL` field itself is retained for any straggling
reader and always resolves to `PUBLIC_URL_BACKEND`, because every remaining
in-tree reader of it builds an `/api/v1` path. Do not read it in new code.

Environment variables follow the same names: `PUBLIC_URL_FRONTEND`,
`PUBLIC_URL_BACKEND`, and the deprecated `PUBLIC_URL`.
