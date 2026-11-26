# E2E Test: Notification Bell

## Test Description
Validate that the notification bell displays unread count badge and provides access to notifications.

## User Story
As a user
I want to see my unread notification count
So that I know when I have new notifications

## Prerequisites
- Backend server running with WebSocket support
- Frontend dev server running
- Test user with notifications:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Notification Bell Icon

**Steps:**
1. Log in as test user
2. Navigate to any authenticated page (dashboard)
3. **Screenshot:** Header with notification bell
4. Locate notification bell icon in header
5. Verify bell icon is visible
6. Verify icon is interactive (hover state)

**Expected Results:**
- Bell icon visible in header
- Icon has hover state
- Clickable element

### Test 2: Unread Count Badge

**Steps:**
1. Ensure user has unread notifications
2. **Screenshot:** Bell with unread badge
3. Verify badge shows unread count
4. Verify badge is styled (red/colored)
5. Verify count is accurate

**Expected Results:**
- Badge appears when unread > 0
- Count matches actual unread
- Distinct visual styling

### Test 3: Badge Shows 99+ for Large Count

**Steps:**
1. Set up user with 100+ unread notifications
2. View notification bell
3. **Screenshot:** Badge showing 99+
4. Verify badge displays "99+" not actual count

**Expected Results:**
- Large counts display as "99+"
- Badge doesn't overflow

### Test 4: Badge Updates on New Notification

**Steps:**
1. Note current unread count
2. Send new notification via API
3. **Screenshot:** Badge updates
4. Verify count increments
5. Verify update happens without refresh

**Expected Results:**
- WebSocket delivers notification
- Badge updates in real-time
- Count increases by 1

### Test 5: Badge Disappears When All Read

**Steps:**
1. Ensure user has unread notifications
2. Mark all notifications as read
3. **Screenshot:** Bell without badge
4. Verify badge disappears
5. Verify bell icon still present

**Expected Results:**
- Badge hidden when count = 0
- Bell icon remains visible

### Test 6: Click Bell Opens Panel

**Steps:**
1. Click on notification bell icon
2. **Screenshot:** Notification panel opened
3. Verify dropdown/panel appears
4. Verify notifications list visible
5. Click outside to close
6. Verify panel closes

**Expected Results:**
- Click opens notification panel
- Panel displays notifications
- Can close panel

### Test 7: Bell on Mobile

**Steps:**
1. View page on mobile viewport
2. **Screenshot:** Mobile notification bell
3. Verify bell visible (may be in mobile menu)
4. Click/tap bell
5. Verify panel opens appropriately

**Expected Results:**
- Bell accessible on mobile
- Panel displays correctly
- Touch-friendly interaction

### Test 8: WebSocket Connection for Real-Time

**Steps:**
1. Log in as user
2. Verify WebSocket connection established
3. **Screenshot:** Connection status (if visible)
4. Send notification via admin
5. Verify notification received without refresh
6. Verify badge updates

**Expected Results:**
- WebSocket connects on login
- Real-time notifications work
- No polling required

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/in-app/unread-count` | Get unread count |
| WebSocket | `/ws` | Real-time notification delivery |

## Request/Response Format

**Unread Count Response:**
```json
{
  "unread_count": 5
}
```

**WebSocket Notification Message:**
```json
{
  "type": "notification",
  "payload": {
    "notification": {
      "id": "notif-uuid",
      "title": "New Message",
      "body": "You have a new message",
      "read_time": null,
      "created_time": "2024-01-21T10:00:00Z"
    }
  },
  "timestamp": "2024-01-21T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Notification bell | Bell icon in header |
| Unread badge | Badge component on bell |
| Badge count | Text within badge |
| Bell button | `getByRole('button')` with bell icon |
| Notification panel | Dropdown content when open |

## Success Criteria

- Bell icon visible in header
- Unread badge shows accurate count
- 99+ displayed for large counts
- Badge updates in real-time via WebSocket
- Badge disappears when all read
- Click opens notification panel
- Works on mobile devices

## Notes

- Test WebSocket reconnection handling
- Verify badge animation on new notification
- Check badge positioning and styling
- Test with various notification counts
- Verify i18n for badge text (if any)
