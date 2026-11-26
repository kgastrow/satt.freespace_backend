# SSO (Single Sign-On) Architecture

Provider-based OAuth with multi-tenant support. Identity-first lookup for returning users, account linking flow for existing email accounts.

## Key Files

```
app/backend/src/
├── models/
│   ├── organization_sso_settings.py  # Per-org SSO config
│   ├── user_identity.py              # Provider identity links
│   └── user.py                       # User model (created_via, nullable password)
├── crud/
│   ├── organization_sso_settings.py  # SSO settings CRUD
│   └── user_identity.py              # Identity lookup/creation
├── services/sso/
│   ├── base.py                       # BaseSSOProvider ABC
│   ├── google.py                     # Google OAuth
│   └── factory.py                    # Provider factory
└── api/
    ├── sso.py                        # OAuth flow (/sso/{provider}/authorize, callback)
    ├── account_linking.py            # POST /auth/sso/link
    └── user_identities.py            # User identity management
```

## Two-Tier Permission System

**CRITICAL**: Both tiers must be True for SSO to function.

| Tier | Controller | Field | Check |
|------|-----------|-------|-------|
| 1 | Super Admin | `sso_allowed` | Master org-level switch |
| 2 | Org Admin | `{provider}_enabled` | Per-provider toggle |

`get_enabled_providers()` checks both conditions.

## Data Models

### OrganizationSSOSettings
One-to-one with Organization:
- `sso_allowed` - Master switch (super admin)
- `google_enabled`, `google_client_id`, `google_client_secret` - Provider config

### UserIdentity
Links users to SSO accounts (user can have multiple):
- `provider`, `provider_user_id`, `provider_email`

**Partial unique constraints** (where `deleted_time IS NULL`):
- `(organization_id, provider, provider_user_id)` - One identity per provider account
- `(organization_id, user_id, provider)` - One identity per user per provider

### User Model SSO Fields
- `created_via` - Enum: `EMAIL`, `GOOGLE`
- `password` - Nullable (NULL for SSO-only users)

## Provider Interface

```python
class BaseSSOProvider(ABC):
    @abstractmethod
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str: ...
    @abstractmethod
    async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, Any]: ...
    @abstractmethod
    async def get_user_info(self, access_token: str) -> Dict[str, Any]: ...
```

Factory loads credentials from global settings:
```python
SSOProviderFactory.get_provider("google")  # Uses settings.GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
```

## OAuth Flow

### 1. Initiate: `GET /sso/{provider}/authorize?org_slug=...`
1. Validate org active + SSO enabled
2. Generate JWT state (org_id + nonce + 10min expiry)
3. Store nonce in Redis for single-use validation
4. Return `authorization_url`

### 2. Callback: `GET /sso/{provider}/callback?code=...&state=...`
1. Validate state JWT + Redis single-use check
2. Exchange code for access token
3. Get user info (must include `id`/`sub` and `email`)
4. **Identity lookup**: Check `user_identity` by `(provider, provider_user_id, org_id)`
   - Found -> `issue_session_for_user()` -> tokens, or a `requires_2fa` challenge
5. **No identity**: Check user by email
   - No user -> create user (`password=NULL`, `created_via=GOOGLE`) + identity -> tokens
   - User with same `created_via` -> auto-link (migration) -> tokens
   - User with different origin -> return `requires_linking` response

Every path that mints a session goes through `issue_session_for_user`
(`services/auth_session.py`), so the SSO callback applies the same gates as
`/auth/login`: organization active, suspension, email verified, then the 2FA
challenge. The endpoint is therefore a three-member union -
`AccessTokenResponse | LoginResponseWith2FA | SSOLinkingRequiredResponse`.

### 3. Account Linking: `POST /auth/sso/link`
When callback returns `requires_linking=True`:
1. Validate link_token JWT (5min expiry, `purpose="sso_link"`, org-scoped user lookup)
2. **Require proof of the existing account**, before anything is mutated or minted:
   - an `Authorization: Bearer` session for the SAME user in the SAME org, **or**
   - the account's `password` re-entered in the request body

   Possession of the link token is NOT sufficient. It only proves somebody
   completed an OAuth flow for an address matching an existing account.
3. Burn the single-use Redis nonce - deliberately AFTER the proof, so a mistyped
   password does not cost the user their link token. Fails CLOSED (503) when
   Redis is absent.
4. Create `user_identity` record
5. Mint the session through `issue_session_for_user` - the same org-active,
   suspension and 2FA gates as `/auth/login`

Responses: **401** `sso.link_proof_required` (no proof supplied), **403**
`auth.invalid_password` (proof supplied and rejected), **429**
`sso.link_attempts_exceeded` / `auth.ip_blocked` (attempt cap reached), **503**
`sso.link_verification_unavailable` (no Redis).

## Security Requirements

**CSRF Protection**: State JWT encodes org_id + random nonce + expiry. Nonce stored in Redis for single-use validation (prevents replay attacks).

**Multi-Tenancy Isolation**: SSO callback validates user belongs to org. Email uniqueness enforced per-org.

**Rate Limiting**: `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` on all endpoints.

**SSO-Only Users**: `password=NULL`, can only authenticate via SSO provider.

**2FA Enforced**: SSO does **not** skip local 2FA. A 2FA-enrolled account signing
in through a provider gets the same `{requires_2fa: true, two_factor_token}`
challenge as `POST /auth/login`, completed by `POST /auth/verify-2fa`. Gated by
`SSO_TWO_FACTOR_CHALLENGE_ENABLED` in `services/auth_session.py` (currently
`True`).

**Account Linking Security**:
- **Proof of the existing account is required** - a bearer session for that same
  user, or the account's password. The link token alone is refused
  (`_assert_link_proof`).
- The password proof is brute-force limited per link token (5 attempts), per
  target account (10 attempts / 15 min) and per IP, using the shared
  `brute_force_detector`. Hitting a cap refuses further attempts; it does not
  burn the token and does not lock the account out of `/auth/login`.
- Link tokens are single-use (Redis tracking with `getdel`), and the nonce guard
  fails CLOSED - no Redis means 503, not a replayable token
- 5-minute expiry
- User must have verified email
- JWT signed with user_id, provider, provider_user_id, nonce

## Adding a New Provider

1. **Create Provider** (`services/sso/{provider}.py`):
   - Implement `BaseSSOProvider` with `AUTHORIZATION_ENDPOINT`, `TOKEN_ENDPOINT`, `USERINFO_ENDPOINT`

2. **Update Models**:
   - Add `{provider}_enabled`, `{provider}_client_id`, `{provider}_client_secret` to `OrganizationSSOSettings`
   - Add to `CreatedVia` enum in `models/user.py`
   - Add to `PROVIDER_TO_CREATED_VIA` in `api/sso.py`
   - Add to `SUPPORTED_PROVIDERS` set in `api/sso.py`

3. **Update Factory** (`services/sso/factory.py`):
   - Add provider instantiation with settings credentials

4. **Update CRUD** (`crud/organization_sso_settings.py`):
   - Add provider check in `get_enabled_providers()`

5. **Add Config**: `{PROVIDER}_CLIENT_ID`, `{PROVIDER}_CLIENT_SECRET`, `{PROVIDER}_REDIRECT_URI` to settings

6. **Run**: `make migrate-new msg="add_{provider}_sso" && make migrate`

## Troubleshooting

| Error | Check |
|-------|-------|
| "Provider not enabled" | `sso_allowed=True` AND `{provider}_enabled=True` |
| "Invalid state" | State JWT expired (10min TTL), Redis nonce consumed |
| "State parameter already used" | Replay attack prevented - nonce deleted from Redis |
| "User creation fails" | Email unique constraint per org |
| "No provider user ID" | Provider must return `id` or `sub` in user_info |
| "Link token expired/used" | 5min TTL, single-use via Redis |
| "auth.sso_only_account" | User has `password=NULL` - must use SSO |

## Password Login for SSO Users

SSO-only users (`password=NULL`) cannot use password login. Returns:
```json
{"detail": "This account uses SSO...", "detail_code": "auth.sso_only_account"}
```

To enable password login: user must use password reset flow or unlink SSO via `user_identities.py` endpoints (which require setting a password first).
