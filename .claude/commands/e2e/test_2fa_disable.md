# E2E Test: 2FA Disable

## Test Description
Validate the two-factor authentication disable flow including password verification and confirmation.

## User Story
As a user with 2FA enabled
I want to be able to disable 2FA
So that I can simplify my login process if needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user with 2FA enabled
- Known user password for verification

## Test Steps

### Test 1: Navigate to 2FA Disable Option

**Setup:**
- User logged in with 2FA enabled

**Steps:**
1. Login as user with 2FA enabled
2. Navigate to `/settings/security/2fa`
3. **Screenshot:** 2FA settings showing enabled status
4. Verify 2FA status shows "Enabled" with badge
5. Verify "Disable 2FA" button/option is visible
6. Verify warning text about security implications

**Expected Results:**
- 2FA settings page accessible
- Status shows enabled
- Disable option available
- Security warning visible

### Test 2: Open Disable 2FA Dialog

**Steps:**
1. On 2FA settings page with 2FA enabled
2. Click "Disable 2FA" button
3. **Screenshot:** Confirmation dialog
4. Verify confirmation dialog/modal appears
5. Verify warning about losing 2FA protection
6. Verify password input field is shown
7. Verify "Confirm" and "Cancel" buttons

**Expected Results:**
- Dialog opens on button click
- Clear warning message
- Password required for confirmation
- Option to cancel

### Test 3: Successful 2FA Disable with Valid Password

**Steps:**
1. Open disable 2FA dialog (Test 2)
2. Enter correct password
3. **Screenshot:** Password entered
4. Click "Confirm" or "Disable" button
5. Wait for response
6. **Screenshot:** 2FA disabled confirmation
7. Verify success message
8. Verify 2FA status changes to "Disabled"
9. Verify setup option becomes available again

**Expected Results:**
- Valid password accepted
- 2FA successfully disabled
- Success message displayed
- Status updated to disabled
- Can re-enable later

### Test 4: Disable 2FA with Wrong Password

**Steps:**
1. Open disable 2FA dialog
2. Enter incorrect password
3. Click "Confirm" button
4. Wait for response
5. **Screenshot:** Password error
6. Verify error message about invalid password
7. Verify 2FA remains enabled
8. Verify can retry with correct password

**Expected Results:**
- Invalid password rejected
- Clear error message
- 2FA stays enabled
- Can retry

### Test 5: Cancel Disable 2FA

**Steps:**
1. Open disable 2FA dialog
2. **Screenshot:** Dialog open
3. Click "Cancel" button
4. Verify dialog closes
5. Verify 2FA remains enabled
6. Verify no changes made

**Expected Results:**
- Cancel closes dialog
- No action taken
- 2FA status unchanged

### Test 6: Verify Login After 2FA Disabled

**Setup:**
- 2FA successfully disabled (Test 3)

**Steps:**
1. After disabling 2FA, logout
2. Navigate to `/login`
3. Enter credentials for same user
4. Click "Login"
5. **Screenshot:** Direct login (no 2FA)
6. Verify login completes without 2FA prompt
7. Verify redirect directly to dashboard

**Expected Results:**
- Login no longer requires 2FA
- Direct authentication with credentials only
- Full access granted

### Test 7: Re-enable 2FA After Disable

**Setup:**
- 2FA was disabled

**Steps:**
1. Navigate to `/settings/security/2fa`
2. Verify status shows disabled
3. Click "Enable 2FA" or "Start setup"
4. **Screenshot:** Setup available again
5. Verify can go through full setup flow
6. Complete 2FA setup

**Expected Results:**
- Can re-enable 2FA after disable
- Full setup flow available
- 2FA works after re-enabling

### Test 8: Empty Password in Disable Dialog

**Steps:**
1. Open disable 2FA dialog
2. Leave password field empty
3. Click "Confirm" button
4. **Screenshot:** Validation error
5. Verify client-side validation error
6. Verify form doesn't submit

**Expected Results:**
- Empty password blocked
- Validation error shown
- No API call made

### Test 9: Rate Limiting on Password Attempts

**Steps:**
1. Open disable 2FA dialog
2. Enter wrong password 5+ times
3. **Screenshot:** After multiple attempts
4. Verify rate limiting or account protection
5. Check for lockout or wait message

**Expected Results:**
- Protection against brute force
- Clear feedback on too many attempts
- Account protection measures active

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/two-factor/status` | Check current 2FA status |
| DELETE | `/two-factor/setup` | Disable 2FA |

## Request/Response Format

**Disable 2FA Request:**
```json
{
  "password": "CurrentUserPassword123!"
}
```

**Disable 2FA Response (Success):**
```json
{
  "message": "2FA has been disabled",
  "message_code": "two_factor.disabled"
}
```

**Disable 2FA Response (Invalid Password):**
```json
{
  "detail": "Invalid password",
  "message_code": "auth.invalid_password"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Disable button | `getByRole('button', { name: /disable.*2fa/i })` |
| Dialog/Modal | Dialog component or `role="dialog"` |
| Password input | `getByLabelText(/password/i)` |
| Confirm button | `getByRole('button', { name: /confirm|disable/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Status badge | Badge showing enabled/disabled |
| Error message | Error text or toast |
| Success message | Success text or toast |

## Success Criteria

- Disable option visible when 2FA enabled
- Password verification required to disable
- Invalid password prevents disable
- Successful disable updates status
- Login works without 2FA after disable
- Can re-enable 2FA after disable
- Cancel action works correctly
- Rate limiting protects against brute force

## Security Notes

- Password re-verification is critical for disabling 2FA
- Consider requiring 2FA code in addition to password
- Log 2FA disable events for security audit
- Consider notification email when 2FA is disabled
- Rate limit password attempts in disable dialog
