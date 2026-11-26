# E2E Test: Logout

## Test Description
Validate the logout functionality including session termination, token cleanup, and proper redirect to login page.

## User Story
As a logged-in user
I want to securely log out of my account
So that my session is terminated and my account is protected

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated test user

## Test Steps

### Test 1: Successful Logout via Header Menu

**Setup:**
- User logged in

**Steps:**
1. Login as test user
2. Verify on dashboard with user authenticated
3. Click user avatar/menu in header
4. **Screenshot:** User dropdown menu open
5. Verify "Sign out" option is visible
6. Click "Sign out"
7. Wait for logout to complete
8. **Screenshot:** Login page after logout
9. Verify redirect to `/login`
10. Verify user menu no longer shows user info

**Expected Results:**
- User menu shows sign out option
- Click triggers logout
- Redirect to login page
- UI reflects logged out state

### Test 2: Token Cleanup After Logout

**Setup:**
- User logged in

**Steps:**
1. Login and note token storage
2. Verify access token in sessionStorage
3. Verify refresh token in localStorage
4. Perform logout (Test 1)
5. Check sessionStorage for access_token
6. Check localStorage for refresh_token
7. **Screenshot:** Browser storage after logout

**Expected Results:**
- Access token removed from sessionStorage
- Refresh token removed from localStorage
- No authentication data persists

### Test 3: API Access Denied After Logout

**Setup:**
- Capture access token before logout

**Steps:**
1. Login and capture access token
2. Perform logout
3. Attempt API call with old token (manual/dev tools)
4. **Screenshot:** API rejection
5. Verify API returns 401 Unauthorized

**Expected Results:**
- Old tokens are invalidated
- API rejects requests with old token
- Proper 401 response

### Test 4: Protected Routes Redirect After Logout

**Setup:**
- User logged out

**Steps:**
1. After logout, navigate to `/dashboard` directly
2. **Screenshot:** Redirect behavior
3. Verify redirect to `/login`
4. Try navigating to `/settings/profile`
5. Verify redirect to `/login`

**Expected Results:**
- Protected routes require authentication
- Automatic redirect to login
- No flash of protected content

### Test 5: Logout with Multiple Tabs

**Steps:**
1. Login and open app in two browser tabs
2. Verify both tabs show authenticated state
3. Perform logout in Tab 1
4. Check Tab 2 behavior
5. **Screenshot:** Tab 2 after logout in Tab 1
6. Verify Tab 2 reflects logged out state (may need refresh)

**Expected Results:**
- Logout affects all tabs
- Other tabs detect logout on next action/refresh
- Consistent state across tabs

### Test 6: Logout Button Loading State

**Steps:**
1. Login as test user
2. Open user menu
3. Click "Sign out"
4. **Screenshot:** Loading state during logout
5. Verify button shows "Signing out..." or loading indicator
6. Wait for logout to complete

**Expected Results:**
- Loading state during logout
- Prevents double-click
- Visual feedback

### Test 7: Logout with Pending Changes (if applicable)

**Setup:**
- User with unsaved form changes

**Steps:**
1. Login and navigate to a form
2. Make changes without saving
3. Click logout
4. **Screenshot:** Unsaved changes warning (if implemented)
5. Verify behavior (warning or immediate logout)

**Expected Results:**
- Graceful handling of unsaved changes
- Warning if implemented
- User data not lost unexpectedly

### Test 8: Logout All Devices

**Setup:**
- User logged in on multiple devices/sessions

**Steps:**
1. Login and navigate to settings/sessions
2. Find "Logout all devices" option
3. **Screenshot:** Logout all option
4. Click logout all devices
5. Verify confirmation prompt
6. Confirm action
7. **Screenshot:** After logout all
8. Verify all sessions terminated
9. Verify current session also terminated (if applicable)

**Expected Results:**
- All sessions terminated
- All refresh tokens invalidated
- User logged out everywhere

### Test 9: Network Error During Logout

**Steps:**
1. Login as test user
2. Simulate network offline (dev tools)
3. Attempt logout
4. **Screenshot:** Error handling
5. Verify graceful error handling
6. Re-enable network
7. Retry logout
8. Verify successful logout

**Expected Results:**
- Network error handled gracefully
- User informed of issue
- Can retry when network available
- Local cleanup still occurs (defensive)

### Test 10: Logout Clears Redux State

**Setup:**
- User logged in with loaded state

**Steps:**
1. Login and navigate app to populate state
2. Perform logout
3. Check Redux state (dev tools)
4. **Screenshot:** Redux state after logout
5. Verify user data cleared
6. Verify auth state cleared
7. Verify sensitive data removed

**Expected Results:**
- Redux auth state cleared
- User object removed
- No sensitive data persists in memory

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/logout` | Logout current session |
| POST | `/auth/logout/all` | Logout all sessions |

## Request/Response Format

**Logout Request:**
```json
{
  "refresh_token": "refresh_token_value"
}
```

**Logout Response:**
```json
{
  "message": "Logged out successfully",
  "message_code": "auth.logout_success"
}
```

**Logout All Response:**
```json
{
  "message": "Logged out from all devices",
  "message_code": "auth.all_sessions_logged_out"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| User menu trigger | Avatar button in header |
| User dropdown | Dropdown menu component |
| Sign out button | `getByRole('button', { name: /sign out/i })` |
| Logout all button | `getByRole('button', { name: /logout.*all|sign out.*all/i })` |
| Loading state | Button with "Signing out..." text |

## Success Criteria

- Logout option easily accessible
- Logout terminates server session
- Tokens removed from browser storage
- Protected routes inaccessible after logout
- Redux state cleared
- Multi-tab logout handled
- Loading state during logout
- Network errors handled gracefully
- Logout all devices works

## Notes

- Logout should be non-blocking (defensive local cleanup)
- Consider localStorage event listener for cross-tab sync
- JWT cache should be invalidated server-side
- Verify WebSocket connections closed on logout
- Test both success and failure scenarios
