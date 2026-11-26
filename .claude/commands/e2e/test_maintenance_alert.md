# E2E Test: Maintenance Alert

## Test Description
Validate that users receive real-time maintenance mode notifications via WebSocket and are properly informed when the system enters or exits maintenance mode.

## User Story
As a user
I want to be notified when maintenance mode is activated
So that I can save my work and understand why the system may become unavailable

## Prerequisites
- Backend server running with WebSocket support
- Frontend dev server running
- Authenticated user session with WebSocket connected
- Admin user to enable/disable maintenance mode

## Test Steps

### Test 1: Receive Maintenance Mode Activation Alert

**Steps:**
1. Login as regular user (User A) in Browser 1
2. Verify WebSocket is connected
3. Login as admin in Browser 2
4. **Screenshot:** User A's normal working state
5. Enable maintenance mode (Admin):
   - Message: "System maintenance in progress. Please save your work."
   - Immediate activation
6. **Screenshot:** User A receives maintenance alert
7. Verify alert appears without page refresh
8. Verify maintenance message is displayed

**Expected Results:**
- Maintenance alert delivered via WebSocket
- Alert appears immediately
- Custom message is shown
- No page refresh required

### Test 2: Maintenance Alert Display

**Steps:**
1. Trigger maintenance mode (from Test 1)
2. Observe maintenance alert in user's browser
3. **Screenshot:** Maintenance alert/banner
4. Verify alert shows:
   - Maintenance icon or indicator
   - Custom message from admin
   - Estimated end time (if provided)
5. Verify alert is prominent and noticeable
6. Verify alert styling is distinct (warning colors)

**Expected Results:**
- Alert is visually prominent
- All information displayed clearly
- Warning styling (yellow/orange)
- Cannot be easily overlooked

### Test 3: Scheduled Maintenance Warning

**Steps:**
1. Login as user
2. Schedule maintenance for 5 minutes from now (Admin):
   - Start time: 5 minutes from now
   - End time: 1 hour later
   - Message: "Scheduled maintenance starting soon"
3. Wait for WebSocket notification
4. **Screenshot:** Scheduled maintenance warning
5. Verify warning shows:
   - Scheduled start time
   - How long until maintenance begins
   - Option to save work
6. Wait until maintenance starts
7. Verify transition to full maintenance mode

**Expected Results:**
- Pre-maintenance warning delivered
- Countdown or time until maintenance
- Smooth transition when maintenance begins

### Test 4: Maintenance Mode Redirect

**Steps:**
1. Login as regular user
2. Enable maintenance mode (Admin)
3. Wait for maintenance alert
4. **Screenshot:** Alert with redirect warning
5. Verify user is eventually redirected to maintenance page
6. **Screenshot:** Maintenance page
7. Verify user cannot access normal application pages
8. Try to navigate to other routes
9. Verify all routes redirect to maintenance page

**Expected Results:**
- Graceful redirect to maintenance page
- Grace period before redirect (if implemented)
- All routes blocked during maintenance
- Maintenance page is displayed

### Test 5: Super Admin Bypass During Maintenance

**Steps:**
1. Enable maintenance mode (Admin)
2. Login as super admin in new browser
3. **Screenshot:** Super admin access during maintenance
4. Verify super admin can access application (if configured)
5. Verify maintenance indicator visible to super admin
6. Login as regular admin
7. Verify behavior based on configuration

**Expected Results:**
- Super admin bypass works when enabled
- Indicator shows maintenance is active
- Regular users still blocked

### Test 6: Maintenance Mode Deactivation Alert

**Steps:**
1. Have user on maintenance page
2. Disable maintenance mode (Admin)
3. **Screenshot:** Maintenance ended notification
4. Verify user receives notification that maintenance is over
5. Verify automatic redirect to application
6. **Screenshot:** Normal application access restored
7. Verify all functionality works

**Expected Results:**
- End of maintenance announced via WebSocket
- Automatic or prompted return to application
- Full functionality restored
- No stale maintenance state

### Test 7: Maintenance Alert Auto-Refresh Notice

**Steps:**
1. Navigate to maintenance page (during maintenance)
2. **Screenshot:** Auto-refresh notice
3. Verify page mentions auto-refresh behavior
4. Verify page periodically checks maintenance status
5. Wait for maintenance to end
6. Verify page automatically updates

**Expected Results:**
- Maintenance page indicates auto-refresh
- Periodic status checks occur
- Automatic recovery when maintenance ends

### Test 8: Maintenance with Estimated End Time

**Steps:**
1. Enable maintenance with end time (Admin):
   - Scheduled end: 2 hours from now
2. Check maintenance page/alert
3. **Screenshot:** Estimated end time display
4. Verify end time is shown in user's timezone
5. Verify formatting is user-friendly
6. Verify countdown updates (if implemented)

**Expected Results:**
- Estimated end time displayed
- Time formatted in user's locale
- Countdown provides real-time updates

### Test 9: Save Work Warning

**Steps:**
1. User has unsaved work (e.g., form in progress)
2. Enable maintenance mode (Admin)
3. **Screenshot:** Save work warning
4. Verify warning emphasizes saving work
5. Verify grace period allows saving
6. User saves work before redirect
7. Verify work is successfully saved

**Expected Results:**
- Clear warning to save work
- Grace period before full lockout
- User can complete save operations

### Test 10: WebSocket Reconnection During Maintenance

**Steps:**
1. User connected via WebSocket
2. Enable maintenance mode
3. User receives alert
4. Simulate WebSocket disconnect
5. **Screenshot:** Reconnection behavior during maintenance
6. Verify WebSocket reconnects
7. Verify maintenance state is still correct

**Expected Results:**
- WebSocket reconnects even during maintenance
- Maintenance state persists after reconnect
- No confusion about current state

### Test 11: Multiple Users Receive Alert Simultaneously

**Steps:**
1. Login as User A, User B, User C in separate browsers
2. Verify all have WebSocket connections
3. Enable maintenance mode (Admin)
4. **Screenshot:** All users receive alert
5. Verify all users receive alert at same time
6. Verify all users see same message
7. Disable maintenance
8. Verify all users notified of end

**Expected Results:**
- Broadcast to all connected users
- Consistent message across all users
- Synchronized notifications

### Test 12: Maintenance Alert Persistence

**Steps:**
1. Enable maintenance mode
2. User receives alert
3. User refreshes page
4. **Screenshot:** Alert persists after refresh
5. Verify maintenance state persists
6. Verify user still sees maintenance page/alert
7. Verify state is fetched from server

**Expected Results:**
- Maintenance state persists across refresh
- State fetched from server on load
- No escape from maintenance via refresh

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| WS | `/ws` | WebSocket for real-time alerts |
| PUT | `/maintenance` | Enable/disable maintenance (admin) |
| GET | `/maintenance/status` | Check current maintenance status |

## WebSocket Message Format

**Maintenance Activation Message:**
```json
{
  "type": "maintenance",
  "payload": {
    "action": "activate",
    "message": "System maintenance in progress",
    "scheduled_end": "2024-01-15T14:00:00Z",
    "allow_super_admin": true
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Maintenance Deactivation Message:**
```json
{
  "type": "maintenance",
  "payload": {
    "action": "deactivate"
  },
  "timestamp": "2024-01-15T12:30:00Z"
}
```

**Scheduled Maintenance Warning:**
```json
{
  "type": "maintenance",
  "payload": {
    "action": "scheduled",
    "message": "Maintenance scheduled",
    "scheduled_start": "2024-01-15T14:00:00Z",
    "scheduled_end": "2024-01-15T16:00:00Z"
  },
  "timestamp": "2024-01-15T13:55:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Maintenance alert | Alert/banner component |
| Alert message | Text content in alert |
| Estimated end time | Time display in alert |
| Save work button | `getByRole('button', { name: /save/i })` |
| Maintenance page | Full-page maintenance component |
| Go Home button | `getByRole('button', { name: /home/i })` |

## Success Criteria

- Maintenance alerts delivered in real-time
- All users notified simultaneously
- Clear messaging about maintenance
- Estimated end time displayed
- Super admin bypass works (if configured)
- Graceful transition to/from maintenance
- Save work warning provided
- Auto-refresh on maintenance end
- State persists across page refresh

## Notes

- Test with different timezones for end time display
- Verify grace period behavior
- Test with large number of concurrent users
- Monitor WebSocket performance during broadcast
- Verify maintenance page is styled appropriately
- Test mobile responsive maintenance page
- Consider offline behavior
