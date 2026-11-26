# E2E Test: Session Expiry

## Test Description
Validate the automatic logout behavior when user sessions expire, including appropriate messaging and redirect handling.

## User Story
As a user with an expired session
I want to be gracefully logged out with a clear message
So that I understand why I need to re-authenticate

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated test user
- Ability to simulate/accelerate token expiration

## Test Steps

### Test 1: Access Token Expiry with Valid Refresh

**Setup:**
- User logged in with valid refresh token

**Steps:**
1. Login as test user
2. Note access token expiration
3. Wait for access token to expire (or simulate)
4. Perform action requiring API call
5. **Screenshot:** Seamless refresh
6. Verify automatic token refresh
7. Verify action completes successfully
8. Verify no user-visible interruption

**Expected Results:**
- Access token expiry handled transparently
- Automatic refresh occurs
- User continues without interruption
- No logout when refresh succeeds

### Test 2: Full Session Expiry (Refresh Token Expired)

**Setup:**
- Both tokens expired (simulate 7+ days)

**Steps:**
1. Login as test user
2. Simulate refresh token expiration
3. Return to application
4. Attempt any action
5. **Screenshot:** Session expired handling
6. Verify logout occurs
7. Verify redirect to login page
8. Verify session expired message displayed

**Expected Results:**
- Expired session detected
- User logged out gracefully
- Clear "session expired" message
- Redirect to login page

### Test 3: Idle Session Timeout

**Setup:**
- Application configured with idle timeout

**Steps:**
1. Login as test user
2. Leave application idle (no activity)
3. Wait for idle timeout period
4. Move mouse or interact
5. **Screenshot:** Idle timeout handling
6. Verify timeout warning (if implemented)
7. Verify logout after timeout
8. Verify appropriate message

**Expected Results:**
- Idle timeout enforced (if configured)
- Warning before auto-logout (if implemented)
- Graceful logout on timeout
- Clear messaging

### Test 4: Session Expiry During Form Entry

**Steps:**
1. Login and navigate to a form
2. Begin entering data
3. Wait for session to expire
4. Attempt to submit form
5. **Screenshot:** Form submission with expired session
6. Verify session expiry detected
7. Verify user data handling (preserved or warned)
8. Verify redirect to login

**Expected Results:**
- Session expiry detected on form submit
- User informed about expiry
- Consideration for unsaved data
- Clear path to re-authenticate

### Test 5: Session Expiry Message Content

**Steps:**
1. Trigger session expiry
2. **Screenshot:** Expiry message displayed
3. Verify message text is user-friendly
4. Verify message explains session expired
5. Verify login link/button provided
6. Verify i18n if applicable

**Expected Results:**
- Clear, friendly error message
- Explains session timeout
- Provides action to re-login
- Properly translated

### Test 6: Session Expiry Clears Sensitive Data

**Steps:**
1. Login and use application (load data)
2. Trigger session expiry
3. After logout, check browser storage
4. **Screenshot:** Storage after expiry
5. Verify access token removed
6. Verify refresh token removed
7. Verify sensitive data cleared from state

**Expected Results:**
- All tokens removed
- Redux/state cleared
- No sensitive data persists
- Clean slate for next login

### Test 7: Session Expiry with Unsaved Changes Warning

**Setup:**
- Application implements unsaved changes detection

**Steps:**
1. Login and navigate to editable content
2. Make changes without saving
3. Wait for session to expire
4. Attempt action or refresh
5. **Screenshot:** Unsaved changes handling
6. Verify warning about unsaved data (if implemented)
7. Verify user can copy/save data before logout

**Expected Results:**
- Unsaved changes detected
- Warning provided if implemented
- User data protection considered

### Test 8: Multiple Tab Session Expiry

**Steps:**
1. Login and open multiple tabs
2. In Tab 1, wait for session expiry
3. Check Tab 2 behavior
4. **Screenshot:** Multi-tab expiry handling
5. Attempt action in Tab 2
6. Verify session expiry detected
7. Verify redirect to login in Tab 2

**Expected Results:**
- All tabs detect expired session
- Consistent behavior across tabs
- No orphaned authenticated state

### Test 9: Return to App After Session Expiry

**Steps:**
1. Login and close browser (don't logout)
2. Wait for session to expire
3. Reopen browser and navigate to app
4. **Screenshot:** Return after expiry
5. Verify session state checked on load
6. Verify redirect to login if expired
7. Verify no flash of authenticated content

**Expected Results:**
- Session validated on app load
- Expired session detected immediately
- No protected content shown
- Direct to login

### Test 10: Session Expiry Error Recovery

**Steps:**
1. On login page after session expiry
2. Login with valid credentials
3. **Screenshot:** Successful re-login
4. Verify full access restored
5. Verify can use all features
6. Verify new valid session created

**Expected Results:**
- Can re-login after expiry
- Full access restored
- New tokens issued
- Normal operation resumes

### Test 11: Session Expiry vs Server-Side Invalidation

**Setup:**
- Admin invalidates user's sessions

**Steps:**
1. User logged in
2. Admin revokes all user sessions (server-side)
3. User attempts action
4. **Screenshot:** Server invalidation handled
5. Verify similar handling to expiry
6. Verify user logged out
7. Verify appropriate message

**Expected Results:**
- Server-side invalidation detected
- User logged out gracefully
- Appropriate messaging
- Can re-login

## API Behavior

When session expires, API returns:
```json
{
  "status": 401,
  "detail": "Token has expired",
  "message_code": "auth.token_expired"
}
```

When refresh fails:
```json
{
  "status": 401,
  "detail": "Invalid or expired refresh token",
  "message_code": "auth.invalid_refresh_token"
}
```

## Session Timing Reference

| Event | Typical Timing |
|-------|---------------|
| Access token expiry | 30 minutes |
| Refresh token expiry | 7 days |
| Idle timeout (if configured) | 15-30 minutes |
| Absolute session limit (if configured) | 24-72 hours |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Session expired message | Toast or alert with expiry text |
| Login redirect | URL matches `/login` |
| Re-login button | `getByRole('button', { name: /login|sign in/i })` |
| Warning modal | Dialog component |

## Success Criteria

- Access token expiry triggers transparent refresh
- Full session expiry logs user out
- Clear messaging about session expiration
- Sensitive data cleared on expiry
- Multi-tab handling consistent
- Return to app validates session
- Can successfully re-login
- Server-side invalidation handled

## Notes

- Consider implementing "remember me" for longer sessions
- Idle timeout may require activity tracking (mouse, keyboard)
- Consider showing countdown before timeout
- Test with various token expiration configurations
- WebSocket connections should also handle expiry
- Consider offline scenarios (queue actions, handle on reconnect)
