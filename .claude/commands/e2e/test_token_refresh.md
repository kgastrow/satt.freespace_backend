# E2E Test: Token Refresh

## Test Description
Validate the automatic token refresh mechanism that maintains user sessions without requiring re-login.

## User Story
As an authenticated user
I want my session to automatically refresh
So that I can continue working without being unexpectedly logged out

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated test user
- Understanding of token expiration times (access: ~30 min, refresh: ~7 days)

## Test Steps

### Test 1: Verify Initial Token Storage

**Setup:**
- Fresh login

**Steps:**
1. Login as test user
2. Open browser dev tools
3. Check sessionStorage for `access_token`
4. Check localStorage for `refresh_token`
5. **Screenshot:** Token storage
6. Verify both tokens are present
7. Decode access token JWT (jwt.io or similar)
8. Note expiration time (exp claim)

**Expected Results:**
- Access token in sessionStorage
- Refresh token in localStorage
- Access token has ~30 minute expiration
- Both tokens are valid JWTs

### Test 2: Automatic Token Refresh Before Expiry

**Setup:**
- Logged in with known token expiration

**Steps:**
1. Login and note access token
2. Wait for token to approach expiration (or simulate with short-lived token)
3. Perform API action (navigate, fetch data)
4. **Screenshot:** Network tab showing refresh
5. Verify POST to `/auth/refresh` was made
6. Verify new access token received
7. Verify sessionStorage updated with new token

**Expected Results:**
- Refresh happens automatically before expiry
- New access token issued
- Token storage updated
- User experience uninterrupted

### Test 3: Token Refresh on API Error 401

**Setup:**
- Access token expired (or manually invalidated)

**Steps:**
1. Logged in with valid refresh token
2. Manually expire/invalidate access token
3. Attempt API call
4. **Screenshot:** 401 response handled
5. Verify automatic refresh attempt
6. Verify retry of original request
7. Verify request succeeds with new token

**Expected Results:**
- 401 triggers refresh attempt
- Refresh succeeds with valid refresh token
- Original request retried
- User doesn't see error

### Test 4: Token Refresh Failure - Invalid Refresh Token

**Setup:**
- Invalid or expired refresh token

**Steps:**
1. Manually corrupt refresh token in localStorage
2. Perform action triggering API call
3. **Screenshot:** Logout triggered
4. Verify refresh attempt fails
5. Verify user is logged out
6. Verify redirect to login page
7. Verify error message about session expiration

**Expected Results:**
- Failed refresh logs user out
- Clear session expired message
- Redirect to login
- User can re-authenticate

### Test 5: Token Refresh During Multiple Concurrent Requests

**Steps:**
1. Logged in with token near expiration
2. Trigger multiple API calls simultaneously
3. **Screenshot:** Network requests
4. Verify only one refresh request made (not per API call)
5. Verify all requests completed successfully

**Expected Results:**
- Single refresh for concurrent requests
- No race conditions
- All requests succeed
- Efficient token refresh

### Test 6: Token Refresh Preserves User State

**Steps:**
1. Login and navigate to form page
2. Enter some data in form
3. Wait for token refresh to occur
4. **Screenshot:** Form state preserved
5. Verify form data still present
6. Verify user not redirected
7. Verify can continue working

**Expected Results:**
- Token refresh is transparent
- No page reload
- User state preserved
- Work not interrupted

### Test 7: Refresh Token Expiration (Long-term)

**Setup:**
- Refresh token expired (typically 7 days)

**Steps:**
1. Simulate expired refresh token (wait or manipulate)
2. Return to application
3. Attempt any action
4. **Screenshot:** Session expired handling
5. Verify user logged out
6. Verify appropriate message
7. Verify redirect to login

**Expected Results:**
- Expired refresh token detected
- User logged out gracefully
- Clear message about session
- Must re-login

### Test 8: Token Refresh Updates Last Active

**Steps:**
1. Login and check initial session
2. Wait and trigger token refresh
3. Navigate to sessions page
4. **Screenshot:** Updated last active
5. Verify session last_active updated

**Expected Results:**
- Token refresh updates session activity
- Keeps session marked as active
- Accurate activity tracking

### Test 9: Token Refresh with Suspended User

**Setup:**
- Admin suspends user account

**Steps:**
1. User logged in with valid tokens
2. Admin suspends user account
3. User's access token expires
4. Refresh attempt made
5. **Screenshot:** Suspension handled
6. Verify refresh fails due to suspension
7. Verify user logged out
8. Verify appropriate error message

**Expected Results:**
- Suspended users cannot refresh
- Logged out on next refresh
- Clear message about account status

### Test 10: Token Refresh with Deactivated Organization

**Setup:**
- Admin deactivates organization

**Steps:**
1. User logged in from organization
2. Organization deactivated
3. Access token expires
4. Refresh attempt made
5. **Screenshot:** Organization deactivated handling
6. Verify refresh fails
7. Verify user logged out

**Expected Results:**
- Organization status checked on refresh
- Deactivated org users cannot refresh
- Appropriate error handling

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/refresh` | Refresh access token |

## Request/Response Format

**Refresh Request:**
```json
{
  "refresh_token": "refresh_token_value"
}
```

**Refresh Response (Success):**
```json
{
  "access_token": "new_jwt_access_token"
}
```

**Refresh Response (Failure):**
```json
{
  "detail": "Invalid or expired refresh token",
  "message_code": "auth.invalid_refresh_token"
}
```

## Token Timing

| Token Type | Typical Expiration |
|------------|-------------------|
| Access Token | 30 minutes |
| Refresh Token | 7 days |
| 2FA Token | 5 minutes |

## Test Selectors

This test primarily observes automatic behavior:

| Observable | Method |
|------------|--------|
| Token storage | Browser dev tools → Application → Storage |
| Network requests | Browser dev tools → Network tab |
| Token expiration | JWT decode (jwt.io) |
| Logout redirect | URL change to `/login` |

## Success Criteria

- Automatic refresh before token expiry
- 401 responses trigger refresh
- Single refresh for concurrent requests
- User state preserved during refresh
- Failed refresh logs user out gracefully
- Suspended/deactivated status enforced
- Session activity updated on refresh

## Notes

- Consider testing with shortened token times for faster tests
- Watch for race conditions with concurrent requests
- Verify refresh token rotation if implemented
- Consider offline handling (queue refresh on reconnect)
- Monitor for token storage security (sessionStorage vs localStorage)
