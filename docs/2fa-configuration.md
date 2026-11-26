# Two-Factor Authentication (2FA) Configuration Guide

This guide covers the complete setup and configuration of Two-Factor Authentication in the Freespace Webapp.

## Table of Contents

- [Overview](#overview)
- [Supported Methods](#supported-methods)
- [Environment Configuration](#environment-configuration)
- [Organization Settings](#organization-settings)
- [User Setup Flow](#user-setup-flow)
- [Login with 2FA](#login-with-2fa)
- [Backup Codes](#backup-codes)
- [API Reference](#api-reference)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

---

## Overview

Two-Factor Authentication adds an extra layer of security by requiring users to provide two forms of identification:
1. Something they know (password)
2. Something they have (authenticator app or backup code)

The implementation uses **TOTP (Time-based One-Time Password)** following RFC 6238, compatible with popular authenticator apps like Google Authenticator, Authy, Microsoft Authenticator, and 1Password.

---

## Supported Methods

### TOTP (Primary)
- 6-digit codes generated every 30 seconds
- Compatible with any TOTP-compliant authenticator app
- ±1 time window tolerance (allows 30-second clock drift)

### Backup Codes (Secondary)
- 10 alphanumeric codes (8 characters each)
- Each code can only be used once
- Designed for emergency access when authenticator is unavailable

---

## Configuration

All 2FA settings are configured in `app/backend/config.json`.

### Required Settings

```json
{
  "app": {
    "name": "FREESPACE"
  },
  "jwt": {
    "secret": "your-jwt-secret-key-here"
  },
  "encryption": {
    "key": "your-fernet-encryption-key-here"
  }
}
```

Generate an encryption key with:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Rate Limiting (Optional)

```json
{
  "rate_limit": {
    "enabled": true,
    "login": "5/minute",
    "otp_verify": "5/minute",
    "otp_send": "3/minute"
  }
}
```

### Encryption Key Rotation

To rotate encryption keys without disrupting existing users:

1. Move current `key` to `key_previous`
2. Generate a new `key`
3. Deploy the changes

```json
{
  "encryption": {
    "key": "new-fernet-key-here",
    "key_previous": "old-fernet-key-here"
  }
}
```

The system will decrypt using the previous key and re-encrypt with the new key on next access.

---

## Organization Settings

2FA is managed at the organization level through three policy settings:

### Policy Options

| Policy | Description |
|--------|-------------|
| `disabled` | 2FA is not available for users in this organization |
| `optional` | Users can choose to enable 2FA voluntarily |
| `mandatory` | Users must enable 2FA (with grace period) |

### Configuration via API

```bash
# Get current settings
GET /api/organization-two-factor-settings

# Update settings (requires two_factor:write permission)
PUT /api/organization-two-factor-settings
Content-Type: application/json

{
  "two_factor_policy": "optional",
  "grace_period_days": 7
}
```

### Super Admin Controls

Super admins can enable/disable 2FA capability for entire organizations:

```bash
# Allow or disallow 2FA for an organization
PUT /api/organization-two-factor-settings/organization/{org_id}/allow
Content-Type: application/json

{
  "two_factor_allowed": true
}
```

### Mandatory Policy Enforcement

When setting `mandatory` policy:
1. `enforcement_start_time` is recorded
2. Users without 2FA receive notification
3. Grace period countdown begins
4. After grace period expires, users are prompted to set up 2FA on login

---

## User Setup Flow

### Step 1: Initiate Setup

User requests 2FA setup from their settings page.

**Request:**
```bash
POST /api/two-factor/setup
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "provisioning_uri": "otpauth://totp/FREESPACE:user@example.com?secret=JBSWY3DPEHPK3PXP&issuer=FREESPACE",
  "qr_code_data": "otpauth://totp/..."
}
```

### Step 2: Scan QR Code

User scans the QR code with their authenticator app, or manually enters the secret.

### Step 3: Verify Setup

User enters the 6-digit code from their authenticator to complete setup.

**Request:**
```bash
POST /api/two-factor/verify-setup
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "code": "123456",
  "secret": "JBSWY3DPEHPK3PXP"
}
```

**Response:**
```json
{
  "message": "Two-factor authentication has been enabled successfully",
  "message_code": "two_factor.enabled",
  "backup_codes": [
    "A1B2C3D4",
    "E5F6G7H8",
    "I9J0K1L2",
    "M3N4O5P6",
    "Q7R8S9T0",
    "U1V2W3X4",
    "Y5Z6A7B8",
    "C9D0E1F2",
    "G3H4I5J6",
    "K7L8M9N0"
  ]
}
```

### Step 4: Save Backup Codes

User must save backup codes securely. These are only shown once at setup time.

---

## Login with 2FA

### Step 1: Initial Login

User submits credentials.

**Request:**
```bash
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123",
  "organization_slug": "myorg"
}
```

**Response (2FA Required):**
```json
{
  "requires_2fa": true,
  "two_factor_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Step 2: Verify 2FA Code

User submits TOTP code or backup code.

**Request:**
```bash
POST /api/auth/verify-2fa
Content-Type: application/json

{
  "two_factor_token": "eyJhbGciOiJIUzI1NiIs...",
  "code": "123456"
}
```

**Response (Success):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "abc123..."
}
```

### Using Backup Codes

Backup codes can be used in place of TOTP codes:

```json
{
  "two_factor_token": "eyJhbGciOiJIUzI1NiIs...",
  "code": "A1B2C3D4"
}
```

Each backup code can only be used once. After use, it's marked as consumed.

---

## Backup Codes

### Check Remaining Codes

```bash
GET /api/two-factor/backup-codes
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "total_codes": 10,
  "remaining_codes": 8,
  "used_codes": 2
}
```

### Regenerate Backup Codes

Invalidates all existing codes and generates 10 new ones.

```bash
POST /api/two-factor/regenerate-backup-codes
Authorization: Bearer {access_token}
```

**Response:**
```json
{
  "backup_codes": [
    "X1Y2Z3A4",
    "B5C6D7E8",
    ...
  ]
}
```

### Disabling 2FA

Requires password re-authentication.

```bash
DELETE /api/two-factor/setup
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "password": "current-password"
}
```

---

## API Reference

### User Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/two-factor/setup` | Initiate 2FA setup |
| POST | `/api/two-factor/verify-setup` | Verify and enable 2FA |
| GET | `/api/two-factor/status` | Get current 2FA status |
| GET | `/api/two-factor/backup-codes` | Get backup codes info |
| POST | `/api/two-factor/regenerate-backup-codes` | Generate new backup codes |
| DELETE | `/api/two-factor/setup` | Disable 2FA |

### Organization Endpoints

| Method | Endpoint | Permission | Description |
|--------|----------|------------|-------------|
| GET | `/api/organization-two-factor-settings` | `two_factor:read` | Get org settings |
| PUT | `/api/organization-two-factor-settings` | `two_factor:write` | Update org settings |
| PUT | `/api/organization-two-factor-settings/organization/{id}/allow` | Super Admin | Allow/disallow 2FA |

### Auth Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/verify-2fa` | Verify 2FA code during login |

---

## Security Considerations

### TOTP Secret Storage

- Secrets are encrypted at rest using Fernet (AES-128-CBC with HMAC)
- Encryption keys should be stored securely (environment variables, secrets manager)
- Never log or expose decrypted secrets

### Backup Code Storage

- Backup codes are hashed using bcrypt (same as passwords)
- Original codes cannot be recovered after display
- Users must regenerate codes if lost

### Rate Limiting

- 5 verification attempts per minute (prevents brute force)
- Failed attempts should be monitored for suspicious activity

### Token Security

- 2FA tokens expire after 5 minutes
- Tokens are single-use for the verification step
- Users must complete verification before tokens expire

### Best Practices

1. **Always require password** when disabling 2FA
2. **Log 2FA events** for security auditing (enable, disable, failed attempts)
3. **Notify users** when 2FA settings change
4. **Encourage backup codes** - remind users to save them securely
5. **Monitor for attacks** - watch for repeated failed 2FA attempts

---

## Troubleshooting

### Common Issues

#### "Invalid verification code"

- Ensure device time is synchronized (NTP)
- Check that user scanned the correct QR code
- Verify the authenticator app is using 6-digit TOTP (not HOTP)

#### "2FA not enabled for this organization"

- Check `two_factor_allowed` is `true` for the organization
- Verify `two_factor_policy` is not `disabled`

#### "2FA already set up for this user"

- User already has 2FA enabled
- To reset, user must disable and re-enable 2FA

#### Clock Skew Issues

The implementation allows ±1 time window (30 seconds). For persistent issues:
1. Ensure server time is synchronized with NTP
2. User should sync their device time
3. Consider increasing `valid_window` in verification (not recommended)

### Database Queries for Debugging

```sql
-- Check user's 2FA status
SELECT * FROM user_two_factor
WHERE user_id = 'user-uuid' AND deleted_time IS NULL;

-- Check organization settings
SELECT * FROM organization_two_factor_settings
WHERE organization_id = 'org-uuid' AND deleted_time IS NULL;

-- Check backup codes usage
SELECT COUNT(*) as total,
       SUM(CASE WHEN used_at IS NOT NULL THEN 1 ELSE 0 END) as used
FROM user_two_factor_backup_code
WHERE user_two_factor_id = 'user-2fa-uuid' AND deleted_time IS NULL;
```

---

## Frontend Integration

### React Components

The frontend provides these main components:

- `TwoFactorSetup` - Setup wizard with QR code and verification
- `TwoFactorStatus` - Current status display with disable option
- `TwoFactorVerification` - Login verification form
- `BackupCodesDisplay` - Display and download backup codes

### API Hooks

```typescript
import {
  useInitiateTwoFactorSetupMutation,
  useVerifyTwoFactorSetupMutation,
  useGetUserTwoFactorStatusQuery,
  useGetBackupCodesInfoQuery,
  useRegenerateBackupCodesMutation,
  useDisableTwoFactorMutation,
} from '@/store/api/twoFactorApi'
```

### Example: Enable 2FA Flow

```typescript
// 1. Initiate setup
const [initiateSetup] = useInitiateTwoFactorSetupMutation()
const { secret, provisioning_uri } = await initiateSetup().unwrap()

// 2. Display QR code to user (using provisioning_uri)

// 3. Verify setup with user's code
const [verifySetup] = useVerifyTwoFactorSetupMutation()
const { backup_codes } = await verifySetup({ code, secret }).unwrap()

// 4. Display backup codes to user
```

---

## Migration Notes

When migrating from another 2FA system:

1. **Secrets cannot be migrated** - users must re-enroll
2. **Plan for re-enrollment period** - set policy to `optional` first
3. **Communicate to users** - notify them of the change and timeline
4. **Support period** - allow users to access without 2FA temporarily

---

## Compliance

This implementation supports compliance with:

- **SOC 2** - Multi-factor authentication requirement
- **PCI DSS** - Strong authentication for administrative access
- **HIPAA** - Access controls and authentication
- **GDPR** - Appropriate security measures for personal data

For audit purposes, ensure you:
- Log all 2FA enable/disable events
- Track failed authentication attempts
- Maintain backup code generation records
- Document organization policy changes
