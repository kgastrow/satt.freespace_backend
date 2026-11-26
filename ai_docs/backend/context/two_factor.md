# Two-Factor Authentication (2FA)

TOTP-based 2FA with backup codes, organization-level policies, and encrypted secret storage.

## Key Files

| File | Purpose |
|------|---------|
| `src/api/two_factor.py` | User-facing 2FA endpoints |
| `src/api/organization_two_factor_settings.py` | Org policy endpoints |
| `src/services/two_factor.py` | TOTP/backup code generation and verification |
| `src/crud/user_two_factor.py` | Database operations with encryption |
| `src/models/user_two_factor.py` | User 2FA record model |
| `src/models/user_two_factor_backup_code.py` | Backup codes model |
| `src/models/organization_two_factor_settings.py` | Org settings model |
| `src/serialisers/two_factor.py` | Request/response DTOs |

## Database Models

| Model | Key Fields |
|-------|------------|
| `OrganizationTwoFactorSettings` | `two_factor_allowed`, `two_factor_policy`, `grace_period_days`, `enforcement_start_time`, `two_factor_app_name` |
| `UserTwoFactor` | `user_id`, `secret` (encrypted), `is_enabled`, `verified_at` |
| `UserTwoFactorBackupCode` | `user_two_factor_id`, `code` (hashed), `used_at` |

## Organization Policies

| Policy | Behavior |
|--------|----------|
| `disabled` | 2FA unavailable for org |
| `optional` | Users can enable voluntarily |
| `mandatory` | Users must enable (with grace period) |

## API Endpoints

### User Endpoints (`/api/two-factor/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `GET` | `/policy` | Get org 2FA policy (any authenticated user) |
| `POST` | `/setup` | Initiate setup (returns secret + provisioning URI) |
| `POST` | `/verify-setup` | Verify code and enable 2FA (returns backup codes) |
| `GET` | `/status` | Get user's 2FA status |
| `GET` | `/backup-codes` | Get backup codes count (remaining/used) |
| `POST` | `/regenerate-backup-codes` | Generate new backup codes |
| `DELETE` | `/setup` | Disable 2FA (requires password) |
| `GET` | `/users-without-2fa` | List users without 2FA (`two_factor:read`) |
| `DELETE` | `/admin/users/{user_id}/2fa` | Admin disable user 2FA (super admin) |

### Org Settings (`/api/organization-two-factor-settings/`)

| Method | Endpoint | Permission |
|--------|----------|------------|
| `GET` | `/` | `two_factor:read` |
| `PUT` | `/` | `two_factor:write` |
| `PUT` | `/organization/{id}/allow` | Super admin |
| `GET` | `/organization/{id}` | Super admin |

## Setup Flow

```python
# 1. Initiate - returns secret for QR code
POST /api/two-factor/setup
Response: {"secret": "BASE32SECRET", "provisioning_uri": "otpauth://...", "qr_code_data": "..."}

# 2. Verify - user enters code from authenticator
POST /api/two-factor/verify-setup
Body: {"code": "123456", "secret": "BASE32SECRET"}
Response: {"backup_codes": ["A1B2C3D4", ...]}  # 10 codes, shown once
```

## Login Flow (with 2FA)

```python
# 1. Normal login
POST /api/auth/login
Response: {"requires_2fa": true, "two_factor_token": "..."}  # 5min expiry

# 2. Verify 2FA code (TOTP or backup code)
POST /api/auth/verify-2fa
Body: {"two_factor_token": "...", "code": "123456"}  # or 8-char backup code
Response: {"access_token": "...", "refresh_token": "..."}
```

## Service Usage

```python
from src.services.two_factor import TwoFactorService

# Generate TOTP secret
secret = TwoFactorService.generate_secret()

# Generate provisioning URI for QR code
uri = TwoFactorService.generate_provisioning_uri(secret, email, issuer="AppName")

# Verify TOTP code (valid_window=1 allows +/-30s drift)
is_valid = TwoFactorService.verify_totp(secret, code, valid_window=1)

# Generate backup codes (returns plain + hashed)
plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=10)

# Verify backup code
is_valid = TwoFactorService.verify_backup_code(plain_code, hashed_code)
```

## CRUD Operations

```python
from src.crud import user_two_factor as user_2fa_crud

# Get user's 2FA record
user_2fa = await user_2fa_crud.get_by_user_id(session, user_id, organization_id)

# Create with encrypted secret
user_2fa = await user_2fa_crud.create(session, {
    "user_id": user_id,
    "secret": secret,  # Auto-encrypted
    "is_enabled": True,
    "verified_at": datetime.now(timezone.utc)
}, organization_id)

# Get decrypted secret for verification
decrypted = await user_2fa_crud.get_decrypted_secret(session, user_id, organization_id)

# Get backup codes
codes = await user_2fa_crud.get_backup_codes(session, user_id, organization_id)

# Mark backup code as used
await user_2fa_crud.mark_backup_code_used(session, backup_code_id)
```

## Security Notes

| Aspect | Implementation |
|--------|----------------|
| Secret storage | Fernet encryption (AES-128-CBC + HMAC) via `src/core/encryption.py` |
| Backup codes | bcrypt hashed (same as passwords) |
| Rate limiting | `RATE_LIMIT_OTP_VERIFY` = 5/minute |
| 2FA token | JWT with 5-minute expiry, `purpose: "2fa_verification"` |
| Disable 2FA | Requires password re-authentication |
| Admin disable | Super admin only, logged to audit |

## Configuration

Settings in `src/core/config.py`:

| Setting | Purpose |
|---------|---------|
| `ENCRYPTION_KEY` | Fernet key for TOTP secret encryption |
| `ENCRYPTION_KEY_PREVIOUS` | Previous key for rotation support |
| `RATE_LIMIT_OTP_VERIFY` | Rate limit for 2FA verification (default: 5/minute) |
| `APP_NAME` | Default issuer name for TOTP (can be overridden per-org) |

## Common Tasks

### Check if user has 2FA enabled
```python
user_2fa = await user_2fa_crud.get_by_user_id(session, user_id, org_id)
has_2fa = user_2fa and user_2fa.is_enabled
```

### Check org allows 2FA
```python
settings = await org_2fa_crud.get_by_organization_id(session, org_id)
allowed = settings and settings.two_factor_allowed
```

## Gotchas

- TOTP secret must be encrypted before database storage (handled by `user_2fa_crud.create`)
- Backup codes are bcrypt-hashed and cannot be recovered - only regenerated
- Organization must have `two_factor_allowed=True` before users can enable 2FA
- Admin 2FA disable creates audit log entry
- Grace period for mandatory 2FA calculated from `enforcement_start_time`
