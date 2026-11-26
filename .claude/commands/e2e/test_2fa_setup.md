# E2E Test: 2FA Setup

## Test Description
Validate the two-factor authentication setup flow including QR code display, TOTP verification, and backup codes generation.

## User Story
As a security-conscious user
I want to enable two-factor authentication on my account
So that my account has an additional layer of security

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user without 2FA enabled
- Organization allows 2FA setup
- Authenticator app or TOTP library for code generation

## Test Steps

### Test 1: Navigate to 2FA Setup Page

**Setup:**
- User logged in without 2FA enabled

**Steps:**
1. Login as user without 2FA
2. Navigate to `/settings/security/2fa`
3. **Screenshot:** 2FA settings page
4. Verify 2FA status shows as "disabled"
5. Verify "Enable 2FA" or "Start setup" button is visible
6. Verify description explains 2FA benefits

**Expected Results:**
- 2FA settings page accessible
- Current status clearly shown as disabled
- Setup option available

### Test 2: Initiate 2FA Setup

**Steps:**
1. On 2FA settings page (Test 1)
2. Click "Start setup" or "Enable 2FA" button
3. Wait for setup to load
4. **Screenshot:** QR code displayed
5. Verify QR code image is displayed
6. Verify manual entry code is shown (for manual setup)
7. Verify copy button for manual code works
8. Verify verification code input field is visible

**Expected Results:**
- QR code rendered successfully
- Manual entry secret displayed
- Copy functionality works
- Ready for verification input

### Test 3: Copy Manual Entry Code

**Setup:**
- 2FA setup initiated (Test 2)

**Steps:**
1. On setup page with QR code visible
2. Locate manual entry secret
3. Click copy button
4. **Screenshot:** Copy confirmation
5. Verify copy success feedback (toast or icon change)
6. Verify clipboard contains the secret (if testable)

**Expected Results:**
- Copy button works
- Success feedback shown
- Secret copied to clipboard

### Test 4: Verify 2FA with Valid TOTP Code

**Setup:**
- 2FA setup initiated
- TOTP code generated from secret

**Steps:**
1. On setup page with QR code
2. Get TOTP secret from manual entry field
3. Generate valid 6-digit TOTP code (using authenticator)
4. Enter TOTP code in verification field
5. **Screenshot:** Code entered
6. Click "Verify" button
7. Wait for verification
8. **Screenshot:** Backup codes displayed
9. Verify backup codes are shown (typically 8-10 codes)
10. Verify codes are in readable format
11. Verify copy and download options available

**Expected Results:**
- Valid TOTP code accepted
- Setup completed successfully
- Backup codes generated and displayed
- Clear instructions to save codes

### Test 5: Backup Codes Display and Download

**Setup:**
- 2FA successfully verified (Test 4)

**Steps:**
1. On backup codes display screen
2. **Screenshot:** Full backup codes view
3. Verify all codes are visible (typically 8-10)
4. Click "Copy all codes" button
5. Verify copy success feedback
6. Click "Download codes" button
7. **Screenshot:** Download initiated
8. Verify text file downloaded
9. Verify file contains the backup codes

**Expected Results:**
- All backup codes displayed clearly
- Copy all function works
- Download creates text file
- File contains valid backup codes

### Test 6: Verify 2FA Status After Setup

**Setup:**
- 2FA setup completed

**Steps:**
1. After completing 2FA setup
2. Navigate away and back to `/settings/security/2fa`
3. **Screenshot:** 2FA enabled status
4. Verify status shows "enabled" with badge
5. Verify setup date/time shown
6. Verify "Disable 2FA" option available
7. Verify "Export backup codes" option available

**Expected Results:**
- 2FA status shows enabled
- Configuration date displayed
- Management options available

### Test 7: Invalid TOTP Code During Setup

**Setup:**
- 2FA setup initiated

**Steps:**
1. On setup page with QR code
2. Enter invalid code: `000000`
3. Click "Verify" button
4. **Screenshot:** Invalid code error
5. Verify error message about invalid code
6. Verify can retry with correct code
7. Enter correct TOTP code
8. Verify setup completes successfully

**Expected Results:**
- Invalid code rejected
- Clear error message
- User can retry
- Valid code succeeds after retry

### Test 8: 2FA Setup When Already Enabled

**Setup:**
- User with 2FA already enabled

**Steps:**
1. Login as user with 2FA enabled
2. Navigate to `/settings/security/2fa`
3. **Screenshot:** Already enabled state
4. Verify no option to "enable" (already enabled)
5. Verify only disable and export options shown

**Expected Results:**
- Cannot setup 2FA twice
- Only management options shown
- Status clearly indicates enabled

### Test 9: 2FA Setup Not Allowed by Organization

**Setup:**
- Organization with 2FA disabled in settings

**Steps:**
1. Login as user in restricted organization
2. Navigate to `/settings/security/2fa`
3. **Screenshot:** 2FA not available
4. Verify message that 2FA is not available
5. Verify no setup option shown

**Expected Results:**
- Clear message about organization policy
- No setup option when not allowed

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/two-factor/status` | Check current 2FA status |
| GET | `/two-factor/setup` | Initiate 2FA setup, get QR code |
| POST | `/two-factor/setup` | Verify TOTP and complete setup |
| GET | `/two-factor/backup-codes` | Retrieve backup codes |

## Request/Response Format

**Setup Initiation Response:**
```json
{
  "secret": "BASE32_ENCODED_SECRET",
  "provisioning_uri": "otpauth://totp/...",
  "qr_code_data": "otpauth://totp/AppName:user@email.com?secret=..."
}
```

**Setup Verification Request:**
```json
{
  "code": "123456"
}
```

**Setup Verification Response:**
```json
{
  "message": "2FA has been enabled",
  "message_code": "two_factor.enabled",
  "backup_codes": [
    "XXXXXXXX",
    "YYYYYYYY",
    "..."
  ]
}
```

**Status Response:**
```json
{
  "is_enabled": true,
  "verified_at": "2024-01-15T10:30:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Start setup button | `getByRole('button', { name: /start|enable|setup/i })` |
| QR code image | `img[alt*="QR"]` or QR code component |
| Manual entry field | Text input or readonly field with secret |
| Copy button | `getByLabelText(/copy/i)` or button with copy icon |
| TOTP input | Input for 6-digit code |
| Verify button | `getByRole('button', { name: /verify/i })` |
| Backup codes list | List of code elements |
| Download button | `getByRole('button', { name: /download/i })` |
| Status badge | Badge component showing enabled/disabled |

## Success Criteria

- 2FA setup flow completes successfully
- QR code displays correctly for authenticator scanning
- Manual entry option works as alternative
- Valid TOTP codes are accepted
- Invalid codes show appropriate errors
- Backup codes generated and displayed
- Backup codes can be copied and downloaded
- 2FA status reflects correctly after setup
- Organization policy respected

## Notes

- TOTP codes are time-based (30-second window typically)
- Test with slight time drift to verify clock tolerance
- Backup codes are typically 8 characters alphanumeric
- Verify i18n for all labels and messages
- Test QR code scanning with real authenticator app if possible
