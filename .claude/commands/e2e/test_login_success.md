# E2E Test: Login Success

## Test Description
Validate that users can successfully log in with valid email and password credentials, receive authentication tokens, and are redirected to the dashboard.

## User Story
As a registered user
I want to log in with my email and password
So that I can access my account and use the application

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org

## Test Steps

### Test 1: Successful Login with Valid Credentials

**Steps:**
1. Navigate to `/login`
2. **Screenshot:** Login page loaded
3. Enter email: `test@example.com` in email input field
4. Enter password: `TestPassword123!` in password input field
5. Click the "Login" submit button
6. Wait for redirect to dashboard
7. **Screenshot:** Dashboard page after successful login
8. Verify URL is `/dashboard`
9. Verify user menu shows user's name in header
10. Verify access token is stored in sessionStorage
11. Verify refresh token is stored in localStorage

**Expected Results:**
- Login form accepts valid credentials
- Button shows "Signing in..." during submission
- User is redirected to `/dashboard` on success
- Access token stored in sessionStorage as `access_token`
- Refresh token stored in localStorage as `refresh_token`
- User avatar/name visible in header

### Test 2: Login Form Validation

**Steps:**
1. Navigate to `/login`
2. Click "Login" button without entering any data
3. **Screenshot:** Form validation errors
4. Verify email field shows required/invalid error
5. Verify password field shows required error
6. Enter invalid email format (e.g., `notanemail`)
7. Click "Login" button
8. **Screenshot:** Email format validation error
9. Verify email format validation error is displayed

**Expected Results:**
- Empty form submission shows validation errors
- Invalid email format shows appropriate error message
- Form does not submit with invalid data

### Test 3: Login Persists Authentication State

**Steps:**
1. Complete successful login (Test 1)
2. Refresh the browser page
3. Wait for page to fully load
4. **Screenshot:** Page after refresh
5. Verify user remains logged in
6. Verify still on dashboard (not redirected to login)
7. Verify user menu still shows user's name

**Expected Results:**
- Authentication persists across page refresh
- User is not redirected to login
- Session remains valid

### Test 4: Login Page Redirects Authenticated Users

**Steps:**
1. Complete successful login (Test 1)
2. Navigate directly to `/login` via URL
3. **Screenshot:** Redirect behavior
4. Verify automatic redirect to `/dashboard`
5. Verify no flash of login page

**Expected Results:**
- Already authenticated users cannot access login page
- Automatic redirect to dashboard
- Smooth redirect without login page flash

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/login` | Authenticate user credentials |
| GET | `/user/me` | Fetch current user after login |
| GET | `/user/permissions` | Fetch user permissions |

## Request/Response Format

**Login Request:**
```json
{
  "email": "test@example.com",
  "password": "TestPassword123!",
  "organization_slug": "test-org"
}
```

**Login Response (Success):**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "refresh_token_uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Email input | `getByLabelText(/email/i)` or `input[id="email"]` |
| Password input | `getByLabelText(/password/i)` or `input[id="password"]` |
| Submit button | `getByRole('button', { name: /login|signing in/i })` |
| User menu | Header dropdown with user avatar/name |

## Success Criteria

- Valid credentials result in successful authentication
- Tokens are properly stored in browser storage
- User is redirected to dashboard after login
- Form validation prevents invalid submissions
- Authentication state persists across page refresh
- Authenticated users are redirected away from login page

## Notes

- Test with organization slug in URL if applicable (`/login?org=test-org`)
- Verify i18n translations display correctly (login button text, labels)
- Check that loading spinner shows during authentication
- Rate limiting may affect rapid test execution
