# E2E Test: SSO Login

## Test Description
Validate the Single Sign-On (SSO) login flow using Google OAuth, including authorization redirect, callback handling, and account linking.

## User Story
As a user
I want to log in using my Google account
So that I don't need to remember another password

## Prerequisites
- Backend server running
- Frontend dev server running
- Google OAuth configured for organization
- Test Google account available
- SSO enabled for test organization

## Test Steps

### Test 1: SSO Button Visibility

**Setup:**
- Organization has Google SSO enabled

**Steps:**
1. Navigate to `/login`
2. **Screenshot:** Login page with SSO options
3. Verify "Continue with Google" button is visible
4. Verify button has Google logo/branding
5. Verify SSO option appears in appropriate section

**Expected Results:**
- Google login button visible
- Proper branding displayed
- Clear separation between SSO and email/password

### Test 2: Initiate Google SSO Flow

**Steps:**
1. On login page with SSO enabled
2. Click "Continue with Google" button
3. **Screenshot:** Button click (loading state if any)
4. Verify redirect to Google OAuth URL
5. Verify URL contains correct client_id
6. Verify redirect_uri points to app callback
7. Verify state parameter is included (CSRF protection)

**Expected Results:**
- Click initiates OAuth flow
- Redirect to Google authorization page
- Correct OAuth parameters included
- State parameter for security

### Test 3: Google Authorization (Manual Step)

**Note:** This step requires manual interaction with Google.

**Steps:**
1. On Google login/consent page
2. **Screenshot:** Google authorization page
3. Select or enter Google account
4. Approve requested permissions
5. Wait for redirect back to application

**Expected Results:**
- Google consent screen shows app name
- Requested scopes are reasonable
- Redirect happens after approval

### Test 4: Successful OAuth Callback - New User

**Setup:**
- Google account not previously linked

**Steps:**
1. Complete Google authorization (Test 3)
2. Observe redirect to `/oauth/callback`
3. **Screenshot:** Callback processing
4. Wait for callback handling
5. Verify redirect to dashboard
6. Verify new user account created
7. Verify user profile shows Google email
8. Verify tokens stored in browser

**Expected Results:**
- Callback processed successfully
- New user account created automatically
- Email verified automatically (SSO users)
- Logged in and redirected to dashboard

### Test 5: Successful OAuth Callback - Existing User

**Setup:**
- User already exists with same email

**Steps:**
1. Logout existing user
2. Click "Continue with Google"
3. Complete Google authorization
4. **Screenshot:** Callback processing
5. Verify redirect to dashboard
6. Verify logged in as existing user
7. Verify account linked to Google

**Expected Results:**
- Existing account recognized
- SSO linked to existing account
- Login successful
- No duplicate account created

### Test 6: OAuth Callback Error - Invalid State

**Setup:**
- Manually manipulate state parameter

**Steps:**
1. Start SSO flow
2. Modify state parameter in callback URL
3. Submit modified callback
4. **Screenshot:** Error handling
5. Verify error about invalid state
6. Verify user directed to login page

**Expected Results:**
- Invalid state detected (CSRF protection)
- Clear error message
- User can retry login

### Test 7: OAuth Callback Error - Denied Access

**Steps:**
1. Start SSO flow
2. On Google page, click "Cancel" or deny access
3. **Screenshot:** Access denied callback
4. Verify appropriate error handling
5. Verify user can retry or use password login

**Expected Results:**
- Denied access handled gracefully
- Clear message about cancelled authorization
- Option to try again or use alternative login

### Test 8: SSO Not Enabled for Organization

**Setup:**
- Organization with SSO disabled

**Steps:**
1. Navigate to `/login` for org without SSO
2. **Screenshot:** Login page without SSO
3. Verify Google button is NOT visible
4. Verify only email/password login available

**Expected Results:**
- SSO button hidden when not configured
- Only standard login available
- No error or broken UI

### Test 9: SSO Login Persists Session

**Setup:**
- Completed SSO login

**Steps:**
1. After successful SSO login
2. Refresh browser page
3. **Screenshot:** Page after refresh
4. Verify user remains logged in
5. Close and reopen browser (if possible)
6. Navigate to app
7. Verify session persists

**Expected Results:**
- SSO session persists like password login
- Refresh doesn't log out
- Tokens properly stored

### Test 10: SSO with 2FA Enabled

**Setup:**
- User has 2FA enabled and uses SSO

**Steps:**
1. User with 2FA completes Google SSO
2. **Screenshot:** Post-SSO 2FA prompt (if applicable)
3. Verify 2FA is still required after SSO
4. Enter TOTP code
5. Verify login completes

**Expected Results:**
- SSO doesn't bypass 2FA
- 2FA verification required after SSO
- Complete login after both factors

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organization-sso-settings/enabled-providers` | Get enabled SSO providers |
| GET | `/sso/google/authorize` | Initiate Google OAuth |
| GET | `/sso/google/callback` | Handle OAuth callback |

## OAuth Flow

```
1. User clicks "Continue with Google"
2. Frontend stores provider in sessionStorage
3. Redirect to /sso/google/authorize?org_slug={slug}
4. Backend generates state (JWT + Redis), returns authorization_url
5. Frontend redirects to Google
6. User authorizes on Google
7. Google redirects to /sso/google/callback?code={code}&state={state}
8. Backend validates state (single-use via Redis)
9. Backend exchanges code for Google tokens
10. Backend gets user info from Google
11. Backend creates/links user account
12. Backend returns JWT tokens
13. Frontend stores tokens, redirects to dashboard
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Google button | `getByRole('button', { name: /continue with google/i })` |
| Loading state | Button with "Connecting..." text |
| Error message | Toast or alert with error |

## Success Criteria

- SSO button appears when configured
- OAuth flow initiates correctly
- State parameter provides CSRF protection
- Successful authorization logs user in
- New users created automatically
- Existing users linked to SSO
- Denied/cancelled authorization handled
- Sessions persist like password login
- 2FA still enforced for SSO users

## Security Notes

- State parameter must be validated (prevents CSRF)
- State is single-use (stored in Redis with GETDEL)
- SSO users get email_verified=true automatically
- SSO doesn't bypass 2FA requirements
- Provider tokens should not be exposed to frontend
- Consider additional verification for account linking

## Limitations

- Actual Google OAuth requires manual interaction
- Automated testing may need mocked OAuth provider
- Consider using test/sandbox Google credentials
- Callback URL must be registered in Google Console
