# E2E Test: 2FA Login

## Test Description
Validate the two-factor authentication login flow where users must provide a TOTP code or backup code after entering valid credentials.

## User Story
As a user with 2FA enabled
I want to verify my identity with a second factor
So that my account remains secure even if my password is compromised

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with 2FA enabled and known TOTP secret
- Backup codes available for testing
- Authenticator app or TOTP library for code generation

## Test Steps

### Test 1: Login Triggers 2FA Prompt

**Setup:**
- User with 2FA enabled

**Steps:**
1. Navigate to `/login`
2. Enter valid email and password for 2FA-enabled user
3. Click "Login" button
4. Wait for response
5. **Screenshot:** 2FA verification screen
6. Verify 2FA verification form appears
7. Verify email/password form is replaced with 2FA form
8. Verify 6-digit code input is shown
9. Verify "Use backup code" option is available

**Expected Results:**
- Valid credentials trigger 2FA step
- 2FA verification UI displays
- Clear instructions for entering code
- Backup code option visible

### Test 2: Successful 2FA with TOTP Code

**Setup:**
- Reached 2FA prompt (Test 1)
- TOTP code generated from user's secret

**Steps:**
1. On 2FA verification screen
2. Generate current TOTP code
3. Enter 6-digit code in input field
4. **Screenshot:** Code entered
5. Click "Verify" button (or auto-submit on complete)
6. Wait for verification
7. **Screenshot:** Dashboard after successful login
8. Verify redirect to dashboard
9. Verify user is fully authenticated
10. Verify tokens stored in browser

**Expected Results:**
- Valid TOTP code accepted
- Full login completed
- Redirect to dashboard
- Session established

### Test 3: Invalid TOTP Code

**Setup:**
- Reached 2FA prompt

**Steps:**
1. On 2FA verification screen
2. Enter invalid code: `000000`
3. Click "Verify" button
4. Wait for response
5. **Screenshot:** Invalid code error
6. Verify error message about invalid code
7. Verify can retry with correct code
8. Verify still on 2FA screen (not logged out)

**Expected Results:**
- Invalid code rejected
- Clear error message
- User can retry
- Not kicked back to login

### Test 4: Login with Backup Code

**Setup:**
- Reached 2FA prompt
- Have valid backup code available

**Steps:**
1. On 2FA verification screen
2. Click "Use backup code" link/button
3. **Screenshot:** Backup code input
4. Verify form changes to backup code input (8 chars)
5. Enter valid backup code
6. Click "Verify" button
7. Wait for verification
8. **Screenshot:** Successful login
9. Verify login completes successfully
10. Verify redirect to dashboard

**Expected Results:**
- Backup code option works
- Valid backup code accepted
- Full login completed
- Backup code marked as used (can't reuse)

### Test 5: Invalid Backup Code

**Setup:**
- Reached 2FA prompt, switched to backup code

**Steps:**
1. On backup code input screen
2. Enter invalid backup code: `XXXXXXXX`
3. Click "Verify" button
4. Wait for response
5. **Screenshot:** Invalid backup code error
6. Verify error message
7. Verify can retry

**Expected Results:**
- Invalid backup code rejected
- Clear error message
- User can retry or switch to TOTP

### Test 6: Already Used Backup Code

**Setup:**
- Have a backup code that was already used

**Steps:**
1. Complete login with a backup code (Test 4)
2. Logout
3. Login again, reach 2FA prompt
4. Switch to backup code input
5. Enter the same backup code used before
6. Click "Verify" button
7. **Screenshot:** Used backup code error
8. Verify code is rejected as already used

**Expected Results:**
- Used backup codes are rejected
- Clear message about code being used
- Encourages using different code

### Test 7: Toggle Between TOTP and Backup Code

**Setup:**
- Reached 2FA prompt

**Steps:**
1. On 2FA verification screen (TOTP input)
2. **Screenshot:** Initial TOTP view
3. Click "Use backup code" link
4. Verify form switches to backup code input
5. **Screenshot:** Backup code view
6. Click "Back to code" or equivalent
7. Verify form switches back to TOTP input
8. **Screenshot:** Back to TOTP view

**Expected Results:**
- Can toggle between input types
- Smooth transition between views
- State preserved during toggle

### Test 8: 2FA Token Expiration

**Setup:**
- Reached 2FA prompt
- Wait for 2FA token to expire (5 minutes)

**Steps:**
1. Reach 2FA verification screen
2. Wait for 2FA token expiration (5 minutes typical)
3. Enter valid TOTP code
4. Click "Verify" button
5. **Screenshot:** Token expired error
6. Verify error about expired session
7. Verify user must restart login flow

**Expected Results:**
- Expired 2FA token rejected
- Clear message about expiration
- User directed to restart login

### Test 9: Rate Limiting on 2FA Verification

**Steps:**
1. Reach 2FA verification screen
2. Enter wrong code repeatedly (5+ times)
3. **Screenshot:** After multiple attempts
4. Verify rate limiting kicks in
5. Check for rate limit error message

**Expected Results:**
- Rate limiting prevents brute force
- Clear feedback about too many attempts
- Temporary lockout if configured

### Test 10: 2FA Required During Session (Re-authentication)

**Setup:**
- User already logged in
- Sensitive action requiring re-auth

**Steps:**
1. As logged-in user with 2FA
2. Attempt sensitive action (if applicable)
3. **Screenshot:** Re-authentication prompt
4. Enter TOTP code for re-authentication
5. Verify action proceeds after verification

**Expected Results:**
- Sensitive actions may require 2FA
- 2FA verification allows action
- Session continues

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/login` | Initial login (returns 2FA token) |
| POST | `/auth/verify-2fa` | Verify TOTP/backup code |

## Request/Response Format

**Login Response (2FA Required):**
```json
{
  "requires_2fa": true,
  "two_factor_token": "temporary_token_uuid"
}
```

**2FA Verification Request:**
```json
{
  "two_factor_token": "temporary_token_uuid",
  "code": "123456"
}
```

**2FA Verification Response (Success):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "refresh_token_uuid"
}
```

**2FA Verification Response (Invalid):**
```json
{
  "detail": "Invalid verification code",
  "message_code": "auth.invalid_2fa_code"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| TOTP input | InputOTP component with 6 slots |
| Backup code input | Input for 8-character code |
| Verify button | `getByRole('button', { name: /verify/i })` |
| Use backup code link | `getByRole('button', { name: /backup code/i })` |
| Back to TOTP link | `getByRole('button', { name: /back.*code/i })` |
| Error message | `role="alert"` or error toast |

## Success Criteria

- 2FA prompt appears after valid credentials
- Valid TOTP codes complete login
- Invalid codes show appropriate errors
- Backup codes work as alternative
- Used backup codes are rejected
- Toggle between TOTP and backup works
- 2FA token expiration handled
- Rate limiting prevents brute force

## Notes

- TOTP codes have 30-second validity window
- Most apps allow +-1 window for clock drift
- Backup codes are typically 8 characters
- 2FA token typically expires in 5 minutes
- Test both auto-submit on 6 digits and manual submit
