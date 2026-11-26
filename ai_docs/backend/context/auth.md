# Authentication and Authorization

JWT-based auth via FastAPI dependencies in `app/backend/src/api/deps.py`.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `get_current_user` | Validates JWT, email verification, org context |
| `get_current_super_admin` | Requires `is_admin=True` |
| `get_current_user_admin` | Requires `owner`/`admin` role OR super admin |
| `require_role(name)` | Factory: requires specific role |
| `require_permission(code)` | Factory: requires permission code (format: `resource:action`) |
| `require_any_permission(*codes)` | Factory: requires ANY of listed permissions |
| `require_feature_flag(key)` | Factory: requires feature flag enabled for org |
| `get_current_api_key` | Validates API key via `X-API-Key` header |
| `get_current_user_or_api_key` | Accepts JWT or API key, returns `UnifiedAuthContext` |

## CurrentUser Object

```python
class CurrentUser:
    id: str
    email: str
    organization_id: str
    is_admin: bool           # Super admin - bypasses all checks
    email_verified: bool
    roles: List[str]
    org_is_active: bool
    org_name: Optional[str]
    is_impersonating: bool   # True if admin is impersonating
    impersonator_id: Optional[str]

    def has_role(self, name: str) -> bool:  # Admins have all roles
```

## Authentication Flows

### Two-Step Login
1. `POST /auth/check-email` - Returns `{exists, auth_methods: ["password", "google"]}`
2. `POST /auth/login` - Returns tokens OR `{requires_2fa: true, two_factor_token}`
3. If 2FA: `POST /auth/verify-2fa` with `two_factor_token` + `code` - Returns tokens

### SSO
1. `GET /sso/{provider}/authorize?org_slug=X` - Returns authorization URL
2. Callback creates user or returns `{requires_linking: true, link_token, email, provider}`.
   It can also return `{requires_2fa: true, two_factor_token}` - SSO does not
   skip local 2FA.
3. If linking needed: `POST /auth/sso/link` with `link_token` **plus proof of the
   existing account** - an `Authorization` bearer session for that same user, or
   its password in the body. The token alone is refused with 401
   `sso.link_proof_required`; a wrong password is 403 `auth.invalid_password`.

SSO-only users have `password=NULL`. Password login returns `detail_code: "auth.sso_only_account"`.

### Every session-minting path goes through `issue_session_for_user`

`src/services/auth_session.py` holds the single gate every login path shares:
organization active, suspension, email verified, then the 2FA challenge. This is
deliberate - the SSO callback used to skip all of them, and adding a new login
path that mints its own tokens reintroduces exactly that class of bug.

Registered call sites: `POST /auth/login`, `POST /auth/verify-2fa`,
`GET /sso/{provider}/callback`, `POST /auth/sso/link`, and
`POST /user-otp/verify-email` (the last with `allow_two_factor_challenge=False`).
`tests/unit_tests/test_session_mint_call_sites.py` fails if a new call site
appears without being registered there.

### 2FA Management
- `POST /two-factor/setup` - Returns secret + provisioning URI
- `POST /two-factor/verify-setup` - Enables 2FA, returns backup codes
- `GET /two-factor/policy` - Org policy: `disabled | optional | mandatory`
- `DELETE /two-factor/setup` - Disable (requires password)

### Password Reset
- `POST /auth/password-reset/request` - Always returns success (prevents enumeration)
- `POST /auth/password-reset/confirm` - Invalidates all sessions

### Email Change (multi-step)
1. `POST /users/me/email/change` - Creates request
2. `POST /users/me/email/change/verify` - Verify identity (password), sends OTP to new email
3. `POST /users/me/email/change/otp` - Confirm with OTP, invalidates all sessions

### Connected Accounts
- `GET /user/me/identities` - List linked providers
- `DELETE /user/me/identities/{provider}` - Unlink (requires password set)
- `POST /user/me/identities/{provider}/unlink-with-setup` - For SSO-only users: set password + unlink

## Security

| Feature | Details |
|---------|---------|
| Brute force | IP blocked after threshold exceeded (see `brute_force_detector.py`) |
| 2FA lockout | Account locked after 5 failed attempts (15 min), per `is_2fa_locked()` |
| Password reset | IP rate limited to 5 requests/hour via `record_password_reset_request()` |
| Suspension | Checked BEFORE 2FA token issued |
| Tokens | Access: short-lived, cached in Redis. Refresh: DB-stored with device info |
| SSO state | Single-use tokens stored in Redis to prevent replay attacks |

### BruteForceDetector Methods

| Method | Purpose |
|--------|---------|
| `is_blocked(ip)` | Pre-login IP check |
| `record_failure(ip, failure_type, threshold=…, window_seconds=…)` | Increment failures; returns True when the threshold trips |
| `block_ip(ip, reason=…)` / `unblock_ip(ip)` | Explicit IP block / unblock |
| `record_account_failure(email, org_slug)` / `is_account_locked(...)` / `clear_account_failures(...)` | Per-account progressive lockout |
| `record_2fa_failure(user_id)` | Track 2FA failures per user |
| `is_2fa_locked(user_id)` | Check 2FA lockout status |
| `get_2fa_lockout_ttl(user_id)` | Get remaining lockout time |
| `clear_2fa_failures(user_id)` | Reset on successful 2FA |
| `record_password_reset_request(ip)` | Rate limit password resets |

## Token Invalidation

```python
await cache_service.invalidate_jwt_for_user(user_id)       # Logout, password change
await cache_service.invalidate_user_roles(org_id, user_id) # Permission/role change
```

## Usage

```python
@router.get("/protected")
async def protected(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    org_id = current_user.organization_id  # Use in all CRUD calls

@router.get("/admin-only")
async def admin(current_user: Annotated[CurrentUser, Depends(require_permission("users:write"))]):
    pass

@router.get("/feature-gated")
async def feature(current_user: Annotated[CurrentUser, Depends(require_feature_flag("my_feature"))]):
    pass
```
