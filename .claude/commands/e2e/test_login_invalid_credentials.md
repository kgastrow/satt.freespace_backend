# E2E Test: Login Invalid Credentials

## Test Description
Validate that the login form properly handles invalid credentials, displaying appropriate error messages without revealing sensitive information about user existence.

## User Story
As a user attempting to log in
I want to see clear error messages when my credentials are wrong
So that I understand why login failed without security risks

## Prerequisites
- Backend server running
- Frontend dev server running
- Test organization exists: `test-org`
- Valid test user exists (for comparison testing)

## Test Steps

### Test 1: Wrong Password for Existing User

**Steps:**
1. Navigate to `/login`
2. Enter email: `test@example.com` (existing user)
3. Enter password: `WrongPassword123!`
4. Click "Login" button
5. Wait for error response
6. **Screenshot:** Error message displayed
7. Verify error message is generic (does not confirm user exists)
8. Verify error toast/message appears
9. Verify form remains on login page
10. Verify password field is cleared (security best practice)

**Expected Results:**
- Generic error message: "Invalid email or password" or similar
- Does NOT say "wrong password" (prevents user enumeration)
- User remains on login page
- Form is ready for retry

### Test 2: Non-Existent Email

**Steps:**
1. Navigate to `/login`
2. Enter email: `nonexistent.user.12345@example.com`
3. Enter password: `AnyPassword123!`
4. Click "Login" button
5. Wait for error response
6. **Screenshot:** Error message displayed
7. Verify error message is identical to Test 1 (prevents enumeration)
8. Verify no indication that email doesn't exist

**Expected Results:**
- Same generic error message as Test 1
- No user enumeration vulnerability
- Consistent error response timing

### Test 3: Invalid Organization Slug

**Steps:**
1. Navigate to `/login?org=nonexistent-org` (or equivalent)
2. Enter email: `test@example.com`
3. Enter password: `TestPassword123!`
4. Click "Login" button
5. Wait for error response
6. **Screenshot:** Organization error
7. Verify appropriate error about organization

**Expected Results:**
- Error indicates organization issue
- Does not reveal if user exists in other orgs

### Test 4: Empty Password

**Steps:**
1. Navigate to `/login`
2. Enter email: `test@example.com`
3. Leave password field empty
4. Click "Login" button
5. **Screenshot:** Validation error
6. Verify client-side validation prevents submission
7. Verify password required message displays

**Expected Results:**
- Form validation prevents submission
- Password field shows required error
- No API call made

### Test 5: Suspended User Login Attempt

**Setup:**
- User with suspended account exists

**Steps:**
1. Navigate to `/login`
2. Enter suspended user credentials
3. Click "Login" button
4. Wait for error response
5. **Screenshot:** Suspended account error
6. Verify appropriate error message about account status

**Expected Results:**
- Error indicates account is suspended
- Contact admin message may be shown
- User cannot proceed to login

### Test 6: Multiple Failed Attempts (Rate Limiting)

**Steps:**
1. Navigate to `/login`
2. Attempt login with wrong password 5 times rapidly
3. **Screenshot:** After multiple attempts
4. Verify rate limiting kicks in (if configured)
5. Check for rate limit error message or temporary lockout
6. Wait for cooldown period
7. Verify can attempt login again after cooldown

**Expected Results:**
- Rate limiting protects against brute force
- Clear message about too many attempts
- Temporary lockout if configured
- Recovery possible after cooldown

### Test 7: SQL Injection Prevention

**Steps:**
1. Navigate to `/login`
2. Enter email: `' OR '1'='1' --`
3. Enter password: `' OR '1'='1' --`
4. Click "Login" button
5. **Screenshot:** Response to injection attempt
6. Verify no SQL error exposed
7. Verify normal validation/error response

**Expected Results:**
- Input is properly sanitized
- No SQL errors exposed to user
- Normal invalid credentials response

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/login` | Authentication attempt |

## Error Response Format

**Invalid Credentials Response (400/401):**
```json
{
  "detail": "Invalid email or password",
  "message_code": "auth.invalid_credentials"
}
```

**Rate Limited Response (429):**
```json
{
  "detail": "Too many login attempts. Please try again later.",
  "message_code": "auth.rate_limited"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Email input | `getByLabelText(/email/i)` |
| Password input | `getByLabelText(/password/i)` |
| Submit button | `getByRole('button', { name: /login/i })` |
| Error toast | Toast component or `role="alert"` |
| Error message | Text content matching error |

## Success Criteria

- Invalid credentials show generic error message
- No user enumeration through different error messages
- No timing attacks (consistent response time)
- Rate limiting prevents brute force
- SQL injection attempts are safely handled
- Suspended accounts cannot log in
- Form remains usable after errors

## Security Notes

- Error messages must be identical for "wrong password" vs "user doesn't exist"
- Response timing should be consistent to prevent timing attacks
- Rate limiting should be enforced at API level
- No stack traces or internal errors exposed to users
- Password field should be cleared after failed attempt
