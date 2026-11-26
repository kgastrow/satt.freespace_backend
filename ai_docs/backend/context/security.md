# Backend Security

## Critical Rules

| NEVER | ALWAYS |
|-------|--------|
| Deploy with `CORS_ALLOWED_ORIGINS="*"` | Configure specific origins before deployment |
| Use default `JWT_SECRET` in production | Generate secure secret: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| Deploy without `ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| Store secrets in source code | Use config.json (gitignored) or environment variables |
| Trust user input without validation | Use Pydantic models for all request validation |
| Skip tenant isolation in queries | Filter all tenant-scoped queries by `organization_id` |

## Startup Security Validation

The application validates critical security settings at startup (`main.py` lifespan). In non-testing mode, the server will **refuse to start** if:

1. **JWT_SECRET** is set to the default placeholder value
2. **CORS_ALLOWED_ORIGINS** is set to wildcard `"*"`
3. **ENCRYPTION_KEY** is not configured
4. **TRUSTED_CLIENT_IP_HEADER** names an append-only header (`X-Forwarded-For`,
   `Forwarded`, `X-Forwarded`). Proxies *append* to these, so their leftmost
   value is client-forgeable.

This prevents accidental production deployments with insecure defaults.

Leaving `TRUSTED_CLIENT_IP_HEADER` empty is a loud **WARNING**, not a refusal.

## Client IP resolution

`src/core/client_ip.py` is the single correct entry point. `get_client_ip()`
reads `TRUSTED_CLIENT_IP_HEADER` when configured and usable, otherwise falls back
to the connection peer as uvicorn resolved it. `client_ip_key()` is the slowapi
`key_func`; unresolvable clients share the `"unknown"` bucket.

This matters because the client IP keys both the rate limiter and the
brute-force machinery (`brute_force:failures:{ip}`, `brute_force:blocked:{ip}`).
Behind a proxy whose address is not named in uvicorn's `--forwarded-allow-ips`,
every visitor collapses into ONE bucket: five failed logins anywhere block
everyone. Never set `--forwarded-allow-ips='*'` - uvicorn then trusts the
leftmost, client-supplied `X-Forwarded-For` entry on every connection. Behind a
CDN, set `trusted_client_ip_header` to the header your edge overwrites (e.g.
`CF-Connecting-IP`) and lock the origin.

New code should import from `src.core.client_ip`; `src.services.audit` still
re-exports `get_client_ip` for existing call sites.

## CORS Configuration (SEC-B-001)

### Why Wildcard CORS is Dangerous

Setting `CORS_ALLOWED_ORIGINS="*"` allows **any website** to make authenticated requests to your API, enabling:

- **CSRF attacks**: Malicious sites can perform actions on behalf of authenticated users
- **Data exfiltration**: Attackers can read sensitive API responses from any origin
- **Credential theft**: Combined with other vulnerabilities, can lead to token theft

### Configuration

CORS is configured in `config.json` under the `cors` section:

```json
{
  "cors": {
    "allowed_origins": "https://app.example.com,https://admin.example.com"
  }
}
```

The setting maps to:
- **Config key**: `cors.allowed_origins` (JSON) or `CORS_ALLOWED_ORIGINS` (env var)
- **Format**: Comma-separated list of exact origin URLs
- **Default**: `"*"` (blocked in production by startup validation)

### Examples

**Single frontend:**
```json
{
  "cors": {
    "allowed_origins": "https://app.mycompany.com"
  }
}
```

**Multiple frontends (main app + admin portal):**
```json
{
  "cors": {
    "allowed_origins": "https://app.example.com,https://admin.example.com"
  }
}
```

**Development with multiple local ports:**
```json
{
  "cors": {
    "allowed_origins": "http://localhost:5173,http://localhost:3000"
  }
}
```

### Additional CORS Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| `CORS_ALLOWED_METHODS` | `GET,POST,PUT,PATCH,DELETE,OPTIONS` | HTTP methods allowed |
| `CORS_ALLOWED_HEADERS` | `Authorization,Content-Type,X-API-Key,X-Request-ID` | Request headers allowed |

### Credentials Handling

The backend automatically disables `allow_credentials` when wildcard origins are detected:

```python
# In main.py - credentials disabled if wildcard present
allow_credentials = "*" not in cors_origins
```

This is a defense-in-depth measure, but **production deployments should always use explicit origins**.

## Security Headers (SEC-B-002)

The `SecurityHeadersMiddleware` adds defense-in-depth headers to all responses:

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Frame-Options` | `DENY` | Prevents clickjacking |
| `X-Content-Type-Options` | `nosniff` | Prevents MIME type sniffing |
| `X-XSS-Protection` | `1; mode=block` | XSS filter for older browsers |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Enforces HTTPS |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Controls referrer information |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Restricts browser features |
| `Content-Security-Policy` | See `main.py` | Restricts resource loading |

## Cookie Configuration (SEC-B-004)

Cookie settings are configured in `app/backend/src/core/config.py` (lines 118-122) and used in `app/backend/src/core/cookies.py`.

### Current Configuration

| Setting | Default Value | Purpose |
|---------|---------------|---------|
| `COOKIE_DOMAIN` | `""` (request domain) | Domain scope for cookies |
| `COOKIE_SECURE` | `True` | HTTPS-only transmission |
| `COOKIE_SAMESITE` | `"lax"` | Cross-origin request policy |
| `COOKIE_PATH` | `"/api/v1/auth"` | Restricts cookie to auth endpoints |

### Cookie Usage

Cookies are used **only** for refresh token delivery:

```python
# src/core/cookies.py
response.set_cookie(
    key="refresh_token",
    value=refresh_token,
    httponly=True,      # JavaScript cannot read
    secure=True,        # HTTPS only
    samesite="lax",     # Cross-origin policy
    path="/api/v1/auth", # Only sent to auth endpoints
    max_age=2592000,    # 30 days
)
```

Access tokens are delivered in JSON response bodies and sent via `Authorization: Bearer` header, which is inherently CSRF-resistant.

### SameSite Attribute: Lax vs Strict

#### Current: `SameSite=Lax`

**Behavior:**
- Cookie sent on same-site requests (all methods)
- Cookie sent on cross-site top-level navigation (GET only)
- Cookie **blocked** on cross-site POST, PUT, DELETE, etc.
- Cookie **blocked** on cross-site requests from iframes, images, scripts

**Trade-offs:**

| Advantage | Disadvantage |
|-----------|--------------|
| CSRF protection for state-changing methods (POST/PUT/DELETE) | Allows cookie on cross-site GET navigation |
| Better UX: bookmarks, email links, external redirects work seamlessly | Theoretically vulnerable if GET endpoints have side effects |
| Compatible with OAuth/SSO redirect flows | - |

**Why Lax is appropriate for this application:**
1. Refresh cookies are scoped to `/api/v1/auth` - only auth endpoints receive them
2. Auth endpoints that accept refresh cookies (`POST /auth/refresh`) only return access tokens
3. No state-changing operations occur from refresh token alone
4. All API calls require `Authorization: Bearer` header (CSRF-resistant by design)

#### Alternative: `SameSite=Strict`

**Behavior:**
- Cookie **only** sent on same-site requests
- Cookie **blocked** on ALL cross-site requests, including top-level navigation

**When to consider Strict:**
- Applications with sensitive operations accessible via GET
- Applications where session hijacking risk outweighs UX concerns
- Internal admin tools with no external links expected
- Applications not using OAuth/SSO redirects from external providers

**Drawbacks of Strict:**
- Users clicking links from emails/bookmarks arrive logged out
- OAuth/SSO callbacks may fail if they rely on existing session cookies
- Third-party integrations with redirect flows may break

### Changing Cookie Configuration

#### Via Environment Variables

```bash
# .env
COOKIE_SAMESITE=strict
COOKIE_SECURE=true
COOKIE_PATH=/api/v1/auth
COOKIE_DOMAIN=.example.com
```

#### Via config.json

```json
{
  "cookies": {
    "samesite": "strict",
    "secure": true,
    "path": "/api/v1/auth",
    "domain": ".example.com"
  }
}
```

#### Local Development

```bash
# Local dev without HTTPS
COOKIE_SECURE=false
```

### CSRF Mitigation Summary

| Protection Layer | Mechanism |
|------------------|-----------|
| Primary | Authorization header required for all API calls (not vulnerable to CSRF) |
| Secondary | `SameSite=Lax` blocks cross-origin POST/PUT/DELETE |
| Tertiary | Refresh cookie scoped to `/api/v1/auth` (no state-changing endpoints) |
| Optional | `SameSite=Strict` if UX trade-offs acceptable |

### Recommendation: Authorization Header for State-Changing Operations

All state-changing API endpoints should require the `Authorization: Bearer` header, not just cookies. This is already implemented:

```python
@router.post("/resource")
async def create_resource(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],  # Validates Bearer token
    ...
):
    pass
```

The `get_current_user` dependency extracts the JWT from the `Authorization` header, not from cookies. This makes all protected endpoints inherently CSRF-resistant regardless of cookie SameSite setting.

For highly sensitive operations (password change, account deletion), consider requiring password re-entry:

```python
@router.post("/users/me/delete-account")
async def delete_account(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    password: PasswordConfirmation,  # Require password re-entry
):
    pass
```

## Request Size Limits (SEC-B-003)

`RequestSizeLimitMiddleware` rejects oversized requests before buffering:

- Default: `MAX_REQUEST_BODY_BYTES` (configurable in config.json)
- Prevents memory exhaustion attacks from large payloads

## Rate Limiting

The limiter is `FailOpenLimiter` in `src/core/rate_limit.py`, keyed by
`client_ip_key` (see "Client IP resolution" above). Storage is Redis with
1-second socket timeouts; a storage outage degrades to a per-worker in-memory
store - limits keep being enforced, per worker rather than per cluster - rather
than 500-ing every request.

Settings: `RATE_LIMIT_ENABLED`, `RATE_LIMIT_DEFAULT` (100/minute),
`RATE_LIMIT_LOGIN` (5/minute), `RATE_LIMIT_OTP_VERIFY`, `RATE_LIMIT_OTP_SEND`,
`RATE_LIMIT_EMAIL_TEST`, `RATE_LIMIT_METRICS`.

`FailOpenLimiter` overrides slowapi's private `_check_request_limit`, so the
`slowapi==0.1.9` pin is load-bearing; `tests/unit_tests/test_rate_limit_fail_open.py`
guards it.

## Security Checklist

### Before Production Deployment

- [ ] Generate and set unique `JWT_SECRET`
- [ ] Generate and set unique `ENCRYPTION_KEY`
- [ ] Configure `CORS_ALLOWED_ORIGINS` with specific domains
- [ ] Set `DEBUG=false`
- [ ] Change default `API_DOCS_USERNAME` and `API_DOCS_PASSWORD`
- [ ] Review and configure `COOKIE_SECURE=true` for HTTPS
- [ ] Review `COOKIE_SAMESITE` setting (lax or strict based on requirements)
- [ ] Configure `PUBLIC_URL_FRONTEND` (origin serving the SPA - password-reset,
      invitation and unsubscribe links a person clicks) **and**
      `PUBLIC_URL_BACKEND` (origin serving `/api/v1` - Twilio webhooks, the RFC
      8058 one-click unsubscribe target, file serve URLs). The single
      `PUBLIC_URL` is deprecated and logs a startup warning; see
      `docs/public-url-split.md`
- [ ] Set `TRUSTED_CLIENT_IP_HEADER` (or uvicorn's `--forwarded-allow-ips`) for
      your proxy topology - see "Client IP resolution" below
- [ ] Ensure database uses strong credentials
- [ ] Set up TLS/HTTPS at reverse proxy level

### Adding New Endpoints

- [ ] Use appropriate auth dependency (`get_current_user`, `require_permission`, etc.)
- [ ] Validate all inputs with Pydantic schemas
- [ ] Include `organization_id` filter for tenant-scoped data
- [ ] Add rate limiting if endpoint is sensitive
- [ ] Log sensitive operations to audit log

## Related Documentation

- Frontend security: `ai_docs/frontend/context/security.md`
- Authentication flows: `ai_docs/backend/context/auth.md`
- Cookie implementation: `app/backend/src/core/cookies.py`
- Configuration: `app/backend/src/core/config.py`
