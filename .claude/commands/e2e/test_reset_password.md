# E2E Test: Reset Password

## Test Description
Validate the password reset confirmation flow where users set a new password using a valid reset token.

## User Story
As a user with a password reset link
I want to set a new password
So that I can regain access to my account with new credentials

## Prerequisites
- Backend server running
- Frontend dev server running
- Valid password reset token (from forgot password flow)
- Test organization exists: `test-org`

## Test Steps

### Test 1: Successful Password Reset

**Setup:**
- Obtain valid password reset token from `/auth/password-reset/request`

**Steps:**
1. Navigate to `/reset-password?token={valid_token}&org=test-org`
2. **Screenshot:** Reset password page loaded
3. Verify form shows new password and confirm fields
4. Enter new password: `NewSecurePass123!`
5. Enter confirm password: `NewSecurePass123!`
6. Observe password requirements indicator
7. **Screenshot:** Filled form with requirements met
8. Click "Reset password" button
9. Verify button shows "Resetting..." state
10. Wait for response
11. **Screenshot:** Success message
12. Verify success message about password reset
13. Verify redirect or link to login page
14. Navigate to login and verify new password works

**Expected Results:**
- Form loads with valid token
- Password requirements enforced
- Success message displayed
- User can log in with new password
- All existing sessions invalidated

### Test 2: Password Requirements Validation

**Setup:**
- Valid reset token

**Steps:**
1. Navigate to reset password page with valid token
2. Enter password without special char: `Password123`
3. Observe requirements indicator
4. **Screenshot:** Missing special character indicator
5. Enter password without number: `SecurePassword!`
6. Observe requirements indicator
7. Enter password too short: `Pa1!`
8. Observe requirements indicator
9. **Screenshot:** Length requirement not met
10. Enter valid password meeting all requirements
11. Verify all indicators show as met

**Expected Results:**
- Real-time password validation feedback
- Clear indication of unmet requirements
- All criteria: 8+ chars, uppercase, lowercase, number, special char

### Test 3: Password Confirmation Mismatch

**Setup:**
- Valid reset token

**Steps:**
1. Navigate to reset password page with valid token
2. Enter new password: `NewSecurePass123!`
3. Enter confirm password: `DifferentPass123!`
4. Click "Reset password" button
5. **Screenshot:** Mismatch error
6. Verify error about passwords not matching
7. Verify form doesn't submit

**Expected Results:**
- Mismatch detected before submission
- Clear error message
- User can correct and retry

### Test 4: Invalid Reset Token

**Steps:**
1. Navigate to `/reset-password?token=invalid_token_12345&org=test-org`
2. **Screenshot:** Invalid token page
3. Verify invalid/expired token message displays
4. Verify "Request new link" option is shown
5. Click "Request new link" or equivalent
6. Verify navigation to forgot password page

**Expected Results:**
- Invalid token shows appropriate error
- User guided to request new reset link
- No information leakage about token validity

### Test 5: Expired Reset Token

**Setup:**
- Obtain reset token and wait for expiration (or use expired token)

**Steps:**
1. Navigate to reset password page with expired token
2. **Screenshot:** Expired token message
3. Verify message about link expiration
4. Verify option to request new link

**Expected Results:**
- Expired token handled gracefully
- Clear expiration message
- Path to get new reset link

### Test 6: Already Used Reset Token

**Setup:**
- Complete password reset with a token

**Steps:**
1. Try to use same token again
2. Navigate to reset password page with used token
3. **Screenshot:** Used token error
4. Verify token cannot be reused
5. Verify appropriate error message

**Expected Results:**
- Token marked as used after first use
- Cannot reset password twice with same token
- Security against token reuse

### Test 7: Missing Token Parameter

**Steps:**
1. Navigate to `/reset-password` (no token)
2. **Screenshot:** Missing token handling
3. Verify error or redirect
4. Verify user guided to forgot password flow

**Expected Results:**
- Missing token handled gracefully
- User not stuck on broken page
- Clear path forward

### Test 8: Same Password as Current

**Setup:**
- Valid reset token
- Know current password

**Steps:**
1. Navigate to reset password page with valid token
2. Enter the same password as current (if system tracks this)
3. Click "Reset password"
4. **Screenshot:** Response
5. Verify system handles appropriately (may allow or reject)

**Expected Results:**
- System either accepts or rejects with clear message
- If rejected, clear reason given

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/password-reset/confirm` | Confirm password reset with token |

## Request/Response Format

**Reset Confirm Request:**
```json
{
  "token": "reset_token_from_email",
  "new_password": "NewSecurePass123!",
  "organization_slug": "test-org"
}
```

**Success Response:**
```json
{
  "message": "Password has been reset successfully. You can now log in with your new password.",
  "message_code": "auth.password_reset_success"
}
```

**Invalid Token Response (400):**
```json
{
  "detail": "Invalid or expired password reset link",
  "message_code": "auth.invalid_reset_token"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| New password input | `getByLabelText(/new password/i)` |
| Confirm password | `getByLabelText(/confirm.*password/i)` |
| Submit button | `getByRole('button', { name: /reset password|resetting/i })` |
| Request new link | `getByRole('link', { name: /request.*link/i })` |
| Password requirements | Visual indicator component |
| Error message | `role="alert"` or error text |
| Success message | Success text content |

## Success Criteria

- Valid token allows password reset
- Password requirements enforced
- Password confirmation required and validated
- Invalid/expired tokens handled gracefully
- Tokens are single-use
- All existing sessions invalidated after reset
- Clear success/error messaging
- Navigation to login after success

## Security Notes

- Reset tokens should be single-use
- Token expiration typically 1 hour
- All existing refresh tokens invalidated after reset
- JWT cache invalidated for user
- Password complexity requirements enforced
- No information leakage about token validity timing
