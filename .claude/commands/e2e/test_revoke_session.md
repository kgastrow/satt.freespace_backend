# E2E Test: Revoke Session

## Test Description
Validate the ability to revoke individual sessions and revoke all other sessions for security purposes.

## User Story
As a user concerned about account security
I want to revoke active sessions
So that I can terminate unauthorized access or clean up old sessions

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated test user
- Multiple active sessions (login from different browsers)

## Test Steps

### Test 1: Revoke Single Session

**Setup:**
- User has at least 2 active sessions

**Steps:**
1. Login from Browser A
2. Login from Browser B (creates second session)
3. In Browser A, navigate to `/settings/account/sessions`
4. Locate the session from Browser B
5. **Screenshot:** Session with revoke button
6. Click "Revoke" button for Browser B session
7. Wait for confirmation
8. **Screenshot:** Session revoked confirmation
9. Verify session removed from list
10. Verify success message displayed

**Expected Results:**
- Revoke button visible on non-current sessions
- Click triggers revocation
- Session removed from list
- Success feedback shown

### Test 2: Verify Revoked Session is Terminated

**Setup:**
- Complete Test 1 (revoke session from Browser B)

**Steps:**
1. In Browser B (the revoked session)
2. Attempt to navigate or refresh
3. **Screenshot:** Access denied in Browser B
4. Verify redirect to login page
5. Verify cannot access protected routes
6. Verify tokens no longer valid

**Expected Results:**
- Revoked session immediately terminated
- User in Browser B logged out
- Must re-authenticate to continue

### Test 3: Cannot Revoke Current Session

**Steps:**
1. On sessions page
2. Locate current session (marked with badge)
3. **Screenshot:** Current session without revoke option
4. Verify revoke button is disabled or hidden
5. Verify tooltip explains why (if applicable)

**Expected Results:**
- Cannot revoke current session
- Clear indication of restriction
- Must use logout for current session

### Test 4: Revoke All Other Sessions

**Setup:**
- User has 3+ active sessions

**Steps:**
1. Create multiple sessions (3+ browsers)
2. Navigate to sessions page
3. Locate "Revoke all other sessions" button
4. **Screenshot:** Revoke all button visible
5. Click "Revoke all other sessions"
6. Verify confirmation dialog appears
7. **Screenshot:** Confirmation dialog
8. Confirm action
9. Wait for completion
10. **Screenshot:** Only current session remains
11. Verify only current session in list

**Expected Results:**
- Revoke all button available
- Confirmation required before action
- All other sessions terminated
- Current session preserved

### Test 5: Verify All Other Sessions Terminated

**Setup:**
- Complete Test 4

**Steps:**
1. In other browsers (revoked sessions)
2. Attempt to navigate or refresh
3. Verify all browsers are logged out
4. Verify must re-authenticate in each

**Expected Results:**
- All revoked sessions terminated
- All other browsers logged out
- Current browser still authenticated

### Test 6: Revoke Session Loading State

**Steps:**
1. On sessions page
2. Click revoke on a session
3. **Screenshot:** Loading state during revocation
4. Verify button shows "Revoking..." or spinner
5. Verify button disabled during operation
6. Wait for completion

**Expected Results:**
- Loading state during revocation
- Prevents double-click
- Clear visual feedback

### Test 7: Revoke Session Error Handling

**Setup:**
- Simulate network error during revoke

**Steps:**
1. On sessions page
2. Simulate network failure
3. Click revoke on a session
4. **Screenshot:** Error message
5. Verify error message displayed
6. Verify session still in list
7. Re-enable network and retry
8. Verify revocation succeeds

**Expected Results:**
- Error handled gracefully
- Clear error message
- Session not incorrectly removed
- Retry works

### Test 8: Revoke Session Confirmation

**Steps:**
1. On sessions page
2. Click revoke on a session
3. If confirmation dialog appears:
4. **Screenshot:** Confirmation dialog
5. Click cancel
6. Verify session not revoked
7. Click revoke again
8. Confirm action
9. Verify session revoked

**Expected Results:**
- Confirmation prevents accidental revocation
- Cancel preserves session
- Confirm completes revocation

### Test 9: Session Count Update After Revoke

**Steps:**
1. On sessions page with 3 sessions
2. Note session count displayed (if shown)
3. Revoke one session
4. **Screenshot:** Updated session count
5. Verify count decremented
6. Verify list reflects correct number

**Expected Results:**
- Session count updates immediately
- UI reflects accurate session count

### Test 10: Revoke Recently Active Session

**Steps:**
1. Create new session in Browser B
2. Actively use Browser B (navigate, click)
3. In Browser A, immediately revoke Browser B session
4. **Screenshot:** Revoked active session
5. Verify revocation successful
6. Verify Browser B terminated despite activity

**Expected Results:**
- Can revoke active sessions
- Activity doesn't prevent revocation
- Session terminated immediately

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/sessions` | Fetch sessions list |
| POST | `/sessions/{sessionId}/revoke` | Revoke single session |
| POST | `/sessions/revoke-others` | Revoke all other sessions |

## Request/Response Format

**Revoke Single Session:**
```
POST /sessions/{session_id}/revoke
```

**Response:**
```json
{
  "message": "Session revoked successfully",
  "message_code": "sessions.revoke_success"
}
```

**Revoke All Others:**
```
POST /sessions/revoke-others
```

**Response:**
```json
{
  "message": "All other sessions have been revoked",
  "message_code": "sessions.revoke_others_success",
  "revoked_count": 2
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Revoke button | `getByRole('button', { name: /revoke/i })` |
| Revoke all button | `getByRole('button', { name: /revoke.*other/i })` |
| Confirmation dialog | `role="dialog"` or modal component |
| Confirm button | `getByRole('button', { name: /confirm/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Success message | Toast or alert with success |
| Loading state | Button with "Revoking..." text |

## Success Criteria

- Can revoke individual sessions
- Cannot revoke current session
- Can revoke all other sessions
- Revoked sessions immediately terminated
- Confirmation prevents accidents
- Loading states provide feedback
- Errors handled gracefully
- UI updates after revocation

## Security Notes

- Revocation should immediately invalidate tokens
- Consider rate limiting revocation requests
- Log all session revocations for audit
- Consider notification email for revoked sessions
- Revoke all should be protected with re-auth (optional)
