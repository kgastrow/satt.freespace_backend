# E2E Test: Mark Notification Read

## Test Description
Validate that users can mark individual and all notifications as read.

## User Story
As a user
I want to mark notifications as read
So that I can track which notifications I've seen

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with unread notifications:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Mark Single Notification as Read via Click

**Steps:**
1. Open notification panel
2. Find an unread notification
3. **Screenshot:** Unread notification
4. Click on the notification
5. **Screenshot:** Notification now read
6. Verify unread indicator removed
7. Verify unread badge count decreased

**Expected Results:**
- Click marks as read
- Unread indicator removed
- Badge count updates

### Test 2: Mark as Read via API (Background)

**Steps:**
1. Open notification panel
2. Note an unread notification ID
3. Trigger mark-as-read API call
4. **Screenshot:** After API call
5. Verify UI updates to show read
6. Verify optimistic update occurred

**Expected Results:**
- API marks notification read
- UI updates immediately
- Optimistic update works

### Test 3: Mark All as Read

**Steps:**
1. Ensure multiple unread notifications exist
2. Note the unread count
3. Open notification panel
4. **Screenshot:** Multiple unread notifications
5. Click "Mark All Read" button
6. Wait for update
7. **Screenshot:** All notifications read
8. Verify all unread indicators removed
9. Verify badge shows 0 or disappears

**Expected Results:**
- All notifications marked read
- All indicators removed
- Badge updates to 0

### Test 4: Mark All Read - Empty After

**Steps:**
1. Mark all as read
2. Verify "Mark All Read" button:
   - Disappears, OR
   - Becomes disabled
3. **Screenshot:** Button state after

**Expected Results:**
- Button hidden/disabled when all read
- Prevents unnecessary clicks

### Test 5: Mark Read Persistence

**Steps:**
1. Mark a notification as read
2. Refresh the page
3. Open notification panel
4. **Screenshot:** After refresh
5. Verify notification still shows as read

**Expected Results:**
- Read status persists
- Survives page refresh

### Test 6: Optimistic Update

**Steps:**
1. Open notification panel
2. Click to mark notification read
3. **Screenshot:** Immediate UI update
4. Verify UI updates before API response
5. Verify smooth experience

**Expected Results:**
- UI updates immediately
- No waiting for API
- Smooth user experience

### Test 7: Mark Read Error Handling

**Steps:**
1. Simulate API failure
2. Attempt to mark notification read
3. **Screenshot:** Error state
4. Verify error feedback
5. Verify notification reverts to unread

**Expected Results:**
- Error message shown
- State reverts on failure
- Can retry

### Test 8: Mark Read Updates Badge Count

**Steps:**
1. Note current badge count: X
2. Mark one notification as read
3. **Screenshot:** Badge updated
4. Verify badge now shows X-1
5. Repeat for another notification
6. Verify badge updates again

**Expected Results:**
- Badge decrements on each mark
- Count always accurate

### Test 9: Mark Read via Dismiss

**Steps:**
1. Find an unread notification
2. Hover to show dismiss button
3. Click dismiss/X button
4. **Screenshot:** Notification dismissed
5. Verify notification removed
6. Verify counts updated

**Expected Results:**
- Dismiss also marks as read
- Notification removed from list
- Counts update

### Test 10: Concurrent Mark Read

**Steps:**
1. Rapidly mark multiple notifications as read
2. **Screenshot:** During rapid clicks
3. Verify all updates process
4. Verify no race conditions
5. Verify final count accurate

**Expected Results:**
- Handles rapid actions
- No duplicate requests
- Final state correct

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/notifications/in-app/{id}/read` | Mark single as read |
| POST | `/notifications/in-app/mark-all-read` | Mark all as read |
| GET | `/notifications/in-app/unread-count` | Get updated count |

## Request/Response Format

**Mark as Read Response:**
```json
{
  "message": "Notification marked as read",
  "id": "notif-uuid",
  "read_time": "2024-01-21T10:05:00Z"
}
```

**Mark All Read Response:**
```json
{
  "message": "All notifications marked as read",
  "count": 5
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Notification item | Clickable notification row |
| Unread indicator | Dot element showing unread |
| Mark All Read button | `getByRole('button', { name: /mark all/i })` |
| Unread badge | Badge on notification bell |
| Dismiss button | X button on notification hover |

## Success Criteria

- Click marks individual notification read
- Mark All Read clears all unread
- UI updates optimistically
- Badge count decrements correctly
- Read status persists after refresh
- Error handling reverts state
- Dismiss also marks as read
- Handles concurrent operations

## Notes

- Verify Redux state updates
- Check optimistic vs server state sync
- Test with WebSocket race conditions
- Verify i18n for any messages
- Test keyboard accessibility
