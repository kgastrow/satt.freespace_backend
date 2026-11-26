# E2E Test: Forgot Password

## Test Description
Validate the forgot password flow including password reset request submission and appropriate feedback messaging.

## User Story
As a user who forgot my password
I want to request a password reset link
So that I can regain access to my account

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email
- Test organization exists: `test-org`

## Test Steps

### Test 1: Successful Password Reset Request

**Steps:**
1. Navigate to `/login`
2. Click "Forgot password?" link
3. **Screenshot:** Forgot password page loaded
4. Verify URL is `/forgot-password`
5. Enter email: `test@example.com`
6. Click "Send reset link" button
7. Verify button shows "Sending..." state
8. Wait for response
9. **Screenshot:** Success confirmation screen
10. Verify "Check your email" message displays
11. Verify instructions to check inbox
12. Verify "Back to sign in" link is visible

**Expected Results:**
- Forgot password page loads correctly
- Form accepts valid email
- Success message shows regardless of email existence (security)
- Clear instructions provided
- Link to return to login

### Test 2: Reset Request with Non-Existent Email

**Steps:**
1. Navigate to `/forgot-password`
2. Enter email: `nonexistent.user.99999@example.com`
3. Click "Send reset link" button
4. Wait for response
5. **Screenshot:** Response message
6. Verify same success message as Test 1 (security)
7. Verify no indication that email doesn't exist

**Expected Results:**
- Same UI response as valid email (prevents enumeration)
- Consistent timing (no timing attack vulnerability)
- User sees "check your email" message

### Test 3: Form Validation

**Steps:**
1. Navigate to `/forgot-password`
2. Click "Send reset link" without entering email
3. **Screenshot:** Validation error
4. Verify email required error shows
5. Enter invalid email format: `notanemail`
6. Click "Send reset link"
7. **Screenshot:** Email format error
8. Verify email format validation error

**Expected Results:**
- Empty email shows required error
- Invalid format shows format error
- Form doesn't submit with invalid data

### Test 4: Navigation from Login Page

**Steps:**
1. Navigate to `/login`
2. Verify "Forgot password?" link is visible
3. **Screenshot:** Login page with forgot password link
4. Click "Forgot password?" link
5. Verify navigation to `/forgot-password`
6. Verify back link returns to login

**Expected Results:**
- Forgot password link visible on login
- Proper navigation between pages
- Easy return to login

### Test 5: Multiple Reset Requests (Rate Limiting)

**Steps:**
1. Navigate to `/forgot-password`
2. Submit password reset request for same email 4 times rapidly
3. **Screenshot:** After multiple requests
4. Verify rate limiting kicks in (if configured)
5. Check for rate limit error message
6. Verify system prevents abuse

**Expected Results:**
- Rate limiting prevents spam
- Clear feedback when rate limited
- Security against enumeration attacks

### Test 6: Already Authenticated User

**Setup:**
- User is logged in

**Steps:**
1. While logged in, navigate to `/forgot-password`
2. **Screenshot:** Behavior for authenticated user
3. Verify redirect to dashboard or appropriate handling

**Expected Results:**
- Authenticated users redirected away
- Or form works but notifies about existing session

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/password-reset/request` | Request password reset email |

## Request/Response Format

**Password Reset Request:**
```json
{
  "email": "test@example.com",
  "organization_slug": "test-org"
}
```

**Response (Always Success):**
```json
{
  "message": "If an account exists with this email, a password reset link has been sent."
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Email input | `getByLabelText(/email/i)` or `input[type="email"]` |
| Submit button | `getByRole('button', { name: /send reset link|sending/i })` |
| Back to login | `getByRole('link', { name: /back.*sign in|login/i })` |
| Forgot password link | `getByRole('link', { name: /forgot password/i })` |
| Success message | Text containing "check your email" |

## Success Criteria

- Reset request form works correctly
- Same response for valid and invalid emails (security)
- Clear success messaging
- Easy navigation back to login
- Rate limiting prevents abuse
- No user enumeration vulnerability

## Security Notes

- Response message must be identical for existing vs non-existing emails
- Response timing should be consistent
- Rate limiting: typically 3 requests per minute
- Reset links should expire (typically 1 hour)
- Email should be sent asynchronously (consistent response time)
