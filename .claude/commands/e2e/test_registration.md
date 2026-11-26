# E2E Test: User Registration

## Test Description
Validate the complete user registration flow including form submission, email verification via OTP, and automatic login after verification.

## User Story
As a new user
I want to register for an account and verify my email
So that I can access the application securely

## Prerequisites
- Backend server running
- Frontend dev server running
- Test organization exists: `test-org`
- Email service configured (or mocked for testing)
- Unique test email for each test run (e.g., `test+{timestamp}@example.com`)

## Test Steps

### Test 1: Successful Registration with All Fields

**Steps:**
1. Navigate to `/register`
2. **Screenshot:** Registration page loaded
3. Enter first name: `Test`
4. Enter last name: `User`
5. Enter email: `newuser+{timestamp}@example.com`
6. Enter password: `SecurePass123!`
7. Enter confirm password: `SecurePass123!`
8. Observe password requirements indicator updates
9. **Screenshot:** Filled registration form
10. Click "Create account" button
11. Wait for redirect to email verification page
12. **Screenshot:** Email verification page
13. Verify URL is `/verify-email`
14. Verify email address is displayed on verification page

**Expected Results:**
- Form accepts all valid inputs
- Password requirements indicator shows all criteria met
- Button shows "Creating account..." during submission
- Redirect to `/verify-email` with email in state
- Verification page shows email address

### Test 2: Email Verification with OTP

**Setup:**
- Complete registration (Test 1)
- Retrieve OTP from email or backend logs

**Steps:**
1. On verification page after registration
2. **Screenshot:** OTP input form
3. Enter 6-digit OTP code in input slots
4. Click "Verify" button (or auto-submit on complete)
5. Wait for verification to complete
6. **Screenshot:** Successful verification
7. Verify redirect to dashboard
8. Verify user is logged in (tokens stored)
9. Verify user name shows in header

**Expected Results:**
- OTP input accepts 6 digits
- Successful verification logs user in automatically
- Redirect to dashboard after verification
- User session is established

### Test 3: Password Requirements Validation

**Steps:**
1. Navigate to `/register`
2. Enter password without lowercase: `TESTPASS123!`
3. Observe requirements indicator
4. **Screenshot:** Requirements showing missing lowercase
5. Enter password without uppercase: `testpass123!`
6. Observe requirements indicator
7. **Screenshot:** Requirements showing missing uppercase
8. Enter password without number: `TestPassWord!`
9. Observe requirements indicator
10. Enter password without special char: `TestPass123`
11. Observe requirements indicator
12. Enter password too short: `Te1!`
13. Observe requirements indicator
14. **Screenshot:** Requirements showing length requirement
15. Enter valid password: `SecurePass123!`
16. Verify all requirements show as met

**Expected Results:**
- Real-time password requirement feedback
- Clear indication of which requirements are met/unmet
- All requirements: 8+ chars, lowercase, uppercase, number, special char

### Test 4: Password Confirmation Mismatch

**Steps:**
1. Navigate to `/register`
2. Fill in name and email fields
3. Enter password: `SecurePass123!`
4. Enter confirm password: `DifferentPass123!`
5. Click "Create account" button
6. **Screenshot:** Password mismatch error
7. Verify error message about passwords not matching
8. Verify form does not submit

**Expected Results:**
- Client-side validation catches mismatch
- Clear error message displayed
- Form submission blocked

### Test 5: Duplicate Email Registration

**Setup:**
- User already exists with email `existing@example.com`

**Steps:**
1. Navigate to `/register`
2. Fill all fields with existing email
3. Click "Create account"
4. Wait for response
5. **Screenshot:** Duplicate email error
6. Verify error about email already registered
7. Verify link to login page is provided

**Expected Results:**
- Server rejects duplicate email
- User-friendly error message
- Option to go to login if already registered

### Test 6: Resend Verification Email

**Setup:**
- Complete registration but don't verify

**Steps:**
1. On email verification page
2. Wait for resend button cooldown (if applicable)
3. **Screenshot:** Resend button available
4. Click "Resend" button
5. Verify button shows "Sending..." state
6. Wait for confirmation
7. **Screenshot:** Resend confirmation
8. Verify cooldown timer starts (20 seconds)
9. Verify resend button is disabled during cooldown

**Expected Results:**
- Resend button triggers new OTP email
- Cooldown prevents spam
- Success feedback shown

### Test 7: Invalid OTP Code

**Setup:**
- Complete registration

**Steps:**
1. On email verification page
2. Enter incorrect OTP: `000000`
3. Click "Verify" button
4. Wait for error response
5. **Screenshot:** Invalid OTP error
6. Verify error message about invalid code
7. Verify can retry with correct code

**Expected Results:**
- Invalid code rejected
- Clear error message
- User can retry

### Test 8: Registration with Existing Unverified Email

**Setup:**
- Previous registration started but email not verified

**Steps:**
1. Navigate to `/register`
2. Enter same email as unverified account
3. Fill other fields
4. Click "Create account"
5. **Screenshot:** Response for unverified email
6. Verify behavior (resend verification or allow re-registration)

**Expected Results:**
- System handles gracefully
- Either resends verification or allows new registration
- User informed of next steps

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/user/register` | Create new user account |
| POST | `/user-otp/verify-email` | Verify email with OTP |
| POST | `/user-otp/send-verification-email` | Resend verification OTP |

## Request/Response Format

**Registration Request:**
```json
{
  "email": "newuser@example.com",
  "password": "SecurePass123!",
  "organization_slug": "test-org",
  "first_name": "Test",
  "last_name": "User"
}
```

**Registration Response:**
```json
{
  "message": "Registration successful",
  "message_code": "user.registration_success",
  "user": {
    "id": "uuid",
    "email": "newuser@example.com",
    "first_name": "Test",
    "last_name": "User"
  },
  "requires_verification": true
}
```

**Verify Email Request:**
```json
{
  "email": "newuser@example.com",
  "otp_code": "123456",
  "organization_id": "org-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| First name input | `getByLabelText(/first name/i)` |
| Last name input | `getByLabelText(/last name/i)` |
| Email input | `getByLabelText(/email/i)` |
| Password input | `getByLabelText(/^password$/i)` (exact match) |
| Confirm password | `getByLabelText(/confirm password/i)` |
| Submit button | `getByRole('button', { name: /create account/i })` |
| OTP input | InputOTP component with 6 slots |
| Verify button | `getByRole('button', { name: /verify/i })` |
| Resend button | `getByRole('button', { name: /resend/i })` |
| Password requirements | Visual indicator component |

## Success Criteria

- Complete registration flow works end-to-end
- Password requirements enforced with real-time feedback
- Email verification with OTP works correctly
- Auto-login after verification
- Proper error handling for all edge cases
- Resend functionality with appropriate cooldown
- Duplicate email handling

## Notes

- Generate unique emails per test run to avoid conflicts
- OTP retrieval may need backend access or email mock
- Consider testing with different organization configurations
- Verify i18n for all text content
