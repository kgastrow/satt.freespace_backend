# E2E Test: Change Email

## Test Description
Validate that authenticated users can change their email address through a multi-step verification process including identity verification and OTP confirmation.

## User Story
As an authenticated user
I want to change my email address
So that I can update my account to use a new email for communication and login

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)
- Access to test email inbox for OTP retrieval

## Test Steps

### Test 1: Initiate Email Change with Password Verification

**Steps:**
1. Navigate to `/settings/security/email`
2. Wait for email change page to load
3. **Screenshot:** Email change form with current email displayed
4. Enter new email: "newemail@example.com"
5. Click "Continue" or "Change Email" button
6. Verify identity verification modal appears
7. **Screenshot:** Identity verification modal
8. Select "Password" verification method
9. Enter current password: "TestPassword123!"
10. Click "Verify" button
11. Wait for verification to complete
12. **Screenshot:** OTP entry modal

**Expected Results:**
- Current email is displayed (read-only)
- New email field accepts valid email format
- Identity verification modal shown
- Password verification succeeds
- Proceeds to OTP verification step

### Test 2: Initiate Email Change with 2FA Verification

**Steps:**
1. Navigate to `/settings/security/email` (user with 2FA enabled)
2. Enter new email: "newemail@example.com"
3. Click "Continue" button
4. Verify identity verification modal appears
5. Select "2FA" or "Authenticator" verification tab
6. Enter TOTP code from authenticator app
7. Click "Verify" button
8. **Screenshot:** After 2FA verification
9. Verify OTP entry modal appears

**Expected Results:**
- 2FA option available if user has 2FA enabled
- TOTP code verification works
- Proceeds to OTP verification after 2FA success

### Test 3: Complete Email Change with OTP

**Steps:**
1. Complete identity verification (Test 1 or 2)
2. **Screenshot:** OTP entry modal
3. Check email inbox for OTP code
4. Enter 6-digit OTP code
5. Click "Verify" button
6. Wait for email change to complete
7. **Screenshot:** Success message
8. Verify success notification
9. Verify new email is now displayed on profile

**Expected Results:**
- OTP sent to NEW email address
- OTP entry accepts 6-digit code
- Successful verification changes email
- Success notification displayed
- Profile shows updated email

### Test 4: Email Validation

**Steps:**
1. Navigate to `/settings/security/email`
2. Enter invalid email format: "notanemail"
3. Click continue button
4. **Screenshot:** Email validation error
5. Verify email format validation error
6. Enter email that already exists: "existing@example.com"
7. Submit and verify appropriate error

**Expected Results:**
- Invalid email formats rejected
- Clear validation error messages
- Duplicate email check (if implemented)

### Test 5: OTP Resend Functionality

**Steps:**
1. Initiate email change and reach OTP step
2. **Screenshot:** OTP modal with resend option
3. Verify resend button shows countdown (60 seconds)
4. Wait for countdown to complete
5. Click "Resend Code" button
6. **Screenshot:** After resend
7. Verify new OTP is sent
8. Verify success message for resend

**Expected Results:**
- Resend button disabled during countdown
- Countdown timer visible
- Resend triggers new OTP email
- Confirmation message after resend

### Test 6: Cancel Email Change

**Steps:**
1. Navigate to `/settings/security/email`
2. Enter new email and submit
3. Complete identity verification
4. When OTP modal appears, click "Cancel"
5. **Screenshot:** Cancellation state
6. Verify email change is cancelled
7. Verify original email remains unchanged

**Expected Results:**
- Cancel action available at each step
- Cancellation resets the flow
- Original email preserved
- No partial state left

### Test 7: OTP Expiration

**Steps:**
1. Initiate email change to OTP step
2. Wait for OTP to expire (typically 5-10 minutes)
3. Enter the expired OTP code
4. **Screenshot:** OTP expiration error
5. Verify error message about expired code
6. Verify option to resend new code

**Expected Results:**
- Expired OTP rejected with clear message
- User can request new OTP
- Timer shows remaining validity (if displayed)

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/me/email/change` | Initiate email change |
| POST | `/users/me/email/change/verify` | Verify identity (password/TOTP) |
| POST | `/users/me/email/change/otp` | Verify OTP code |
| POST | `/users/me/email/change/resend` | Resend OTP |
| DELETE | `/users/me/email/change` | Cancel email change |
| GET | `/users/me/email/change/status` | Get email change status |

## Request/Response Format

**Initiate Email Change Request:**
```json
{
  "new_email": "newemail@example.com"
}
```

**Identity Verification Request (Password):**
```json
{
  "method": "password",
  "password": "TestPassword123!"
}
```

**Identity Verification Request (2FA):**
```json
{
  "method": "totp",
  "code": "123456"
}
```

**OTP Verification Request:**
```json
{
  "otp_code": "123456"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| New email input | `input[name="newEmail"]` or `getByLabelText(/new email/i)` |
| Continue button | `getByRole('button', { name: /continue|change email/i })` |
| Password input (modal) | `input[name="password"]` |
| 2FA code input (modal) | `input[name="code"]` |
| OTP input | `input[name="otpCode"]` |
| Verify button | `getByRole('button', { name: /verify/i })` |
| Resend button | `getByRole('button', { name: /resend/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Password tab | Tab element for password verification |
| 2FA tab | Tab element for 2FA verification |

## Success Criteria

- Email change flow completes successfully end-to-end
- Identity verification required before OTP step
- Both password and 2FA verification methods work
- OTP delivery and verification functional
- Resend functionality works with rate limiting
- Cancel action properly cleans up pending state
- Invalid/expired OTPs handled gracefully
- New email must be verified via OTP before change takes effect

## Notes

- After email change, verify old email no longer works for login
- Test with emails from different domains
- Verify email uniqueness validation
- Check that pending email change shows status indicator
- Test timeout handling for modal interactions
- Verify i18n translations for all modal states
