# E2E Test: Notification Panel

## Test Description
Validate that users can view their notifications in a dropdown panel with pagination and actions.

## User Story
As a user
I want to view my notifications in a panel
So that I can see recent activity and messages

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with notifications:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Multiple notifications exist (read and unread)
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Notification Panel

**Steps:**
1. Log in as test user
2. Click notification bell in header
3. **Screenshot:** Notification panel opened
4. Verify panel dropdown appears
5. Verify panel header with "Notifications" title
6. Verify notification list visible

**Expected Results:**
- Panel opens on bell click
- Header shows title
- Notifications displayed

### Test 2: View Notification List

**Steps:**
1. Open notification panel
2. **Screenshot:** Notification list
3. Verify notifications displayed:
   - Title text
   - Body text (truncated)
   - Relative time
   - Unread indicator
4. Verify scrollable area for many notifications

**Expected Results:**
- Notifications show title and body
- Times displayed relatively
- Unread indicated visually
- Scrollable list

### Test 3: Notification Item Details

**Steps:**
1. Open notification panel
2. Find an unread notification
3. **Screenshot:** Unread notification item
4. Verify unread indicator (dot)
5. Verify title is prominent
6. Verify body truncated (2 lines)
7. Verify relative time shown

**Expected Results:**
- Unread dot visible
- Title clearly shown
- Body truncated properly
- Time relative format

### Test 4: Mark All as Read Button

**Steps:**
1. Ensure unread notifications exist
2. Open notification panel
3. **Screenshot:** Mark All Read button
4. Verify "Mark All Read" button visible
5. Click "Mark All Read"
6. Wait for update
7. **Screenshot:** All marked as read
8. Verify all unread indicators removed
9. Verify button disappears or disables

**Expected Results:**
- Mark All Read button present
- All notifications marked read
- UI updates immediately

### Test 5: Load More Pagination

**Steps:**
1. Ensure many notifications exist (20+)
2. Open notification panel
3. **Screenshot:** Initial notifications
4. Scroll to bottom
5. Click "Load More" button
6. **Screenshot:** More notifications loaded
7. Verify additional notifications appear
8. Verify previous notifications still visible

**Expected Results:**
- Load More button at bottom
- More notifications load on click
- Pagination works correctly

### Test 6: Empty State

**Steps:**
1. Use user with no notifications
2. Open notification panel
3. **Screenshot:** Empty state
4. Verify empty state message
5. Verify bell icon in empty state
6. Verify helpful text

**Expected Results:**
- Empty state displayed
- Clear message shown
- Icon/illustration present

### Test 7: Click Notification with Link

**Steps:**
1. Open notification panel
2. Find notification with link (if exists)
3. Click on the notification
4. **Screenshot:** Navigation occurred
5. Verify navigated to linked page
6. Verify notification marked as read

**Expected Results:**
- Clicking navigates to link
- Auto-marks as read
- Panel may close

### Test 8: Dismiss Notification

**Steps:**
1. Open notification panel
2. Hover over a notification
3. **Screenshot:** Dismiss button visible
4. Click X/dismiss button
5. Wait for removal
6. **Screenshot:** Notification removed
7. Verify notification no longer in list

**Expected Results:**
- Dismiss button appears on hover
- Notification removed from list
- Smooth removal animation

### Test 9: Close Panel

**Steps:**
1. Open notification panel
2. Click close button in footer
3. **Screenshot:** Panel closed
4. Verify panel closes
5. Alternative: click outside panel
6. Verify panel also closes

**Expected Results:**
- Close button works
- Click outside closes
- Panel dismisses cleanly

### Test 10: Panel Loading State

**Steps:**
1. Click notification bell (fresh open)
2. **Screenshot:** Loading state
3. Observe skeleton loaders
4. Wait for data to load
5. Verify smooth transition to content

**Expected Results:**
- Loading skeletons shown
- Smooth transition to data
- No empty flash

### Test 11: Real-Time Update in Panel

**Steps:**
1. Open notification panel
2. Keep panel open
3. Send new notification via API/admin
4. **Screenshot:** New notification appears
5. Verify notification added to top of list
6. Verify unread indicator

**Expected Results:**
- New notification appears at top
- No refresh required
- WebSocket delivery works

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/in-app?limit=10&offset=0` | List notifications |
| POST | `/notifications/in-app/mark-all-read` | Mark all as read |
| POST | `/notifications/in-app/dismiss` | Dismiss notification |

## Request/Response Format

**List Notifications Response:**
```json
{
  "items": [
    {
      "id": "notif-uuid",
      "title": "New Message",
      "body": "You have a new message from...",
      "link": "/messages/123",
      "category_id": "cat-uuid",
      "read_time": null,
      "created_time": "2024-01-21T10:00:00Z"
    }
  ],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Notification panel | Dropdown content component |
| Panel header | Header section with title |
| Mark All Read button | `getByRole('button', { name: /mark all/i })` |
| Notification items | Notification item components |
| Unread indicator | Dot element on unread items |
| Notification title | Title text in item |
| Notification body | Body text (truncated) |
| Time display | Relative time text |
| Dismiss button | X button on hover |
| Load More button | `getByRole('button', { name: /load more/i })` |
| Close button | Close button in footer |
| Empty state | Empty state message component |
| Loading skeleton | Skeleton loader components |

## Success Criteria

- Panel opens and displays notifications
- Notification items show title, body, time
- Unread indicator visible for unread items
- Mark All Read clears unread status
- Load More pagination works
- Empty state displays when no notifications
- Click with link navigates
- Dismiss removes notification
- Panel can be closed
- Real-time updates work in open panel

## Notes

- Test with various notification types
- Verify body truncation at 2 lines
- Check relative time accuracy
- Test scrolling behavior
- Verify i18n for panel text
- Check keyboard navigation
