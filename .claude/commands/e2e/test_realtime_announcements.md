# E2E Test: Real-Time Announcements

## Test Description
Validate that users receive system announcements in real-time via WebSocket without page refresh.

## User Story
As a user
I want to receive announcements in real-time
So that I can stay informed about important updates without refreshing the page

## Prerequisites
- Backend server running with WebSocket support
- Frontend dev server running
- Authenticated user session with WebSocket connected
- Admin user to create announcements

## Test Steps

### Test 1: Receive New Announcement via WebSocket

**Steps:**
1. Login as regular user (User A) in Browser 1
2. Verify WebSocket is connected
3. Login as admin (Admin) in Browser 2
4. In Admin browser, create a new announcement:
   - Title: "Real-time Test Announcement"
   - Body: "This is a test of real-time delivery"
   - Priority: "High"
5. **Screenshot:** User A's screen before announcement
6. Save the announcement (Admin)
7. **Screenshot:** User A's screen immediately after
8. Verify announcement appears in User A's browser without refresh
9. Verify announcement displays correctly (title, body, styling)

**Expected Results:**
- Announcement delivered via WebSocket
- No page refresh required
- Announcement displays within seconds
- Content matches what admin created

### Test 2: Announcement Banner Display

**Steps:**
1. Login as user
2. Create a new announcement (as admin in separate session)
3. Wait for announcement to appear
4. **Screenshot:** Announcement banner/card
5. Verify announcement shows:
   - Title prominently displayed
   - Body text visible
   - Priority indicator (color/badge)
   - Dismiss button (if dismissible)
6. Verify styling matches priority level

**Expected Results:**
- Announcement banner appears at top or designated location
- All content elements visible
- Priority styling applied correctly

### Test 3: High Priority Announcement Styling

**Steps:**
1. Login as user
2. Create high priority announcement (admin):
   - Priority: "Critical" or "High"
3. Wait for delivery
4. **Screenshot:** High priority announcement
5. Verify distinct styling:
   - Red/urgent color scheme
   - Possibly larger or more prominent
   - May have icon indicator
6. Verify it stands out from normal announcements

**Expected Results:**
- High priority has urgent styling
- Visually distinct from normal announcements
- Grabs user attention

### Test 4: Dismissible Announcement

**Steps:**
1. Login as user
2. Create dismissible announcement (admin):
   - Dismissible: Yes
3. Wait for delivery
4. **Screenshot:** Dismissible announcement with X button
5. Verify dismiss/close button is present
6. Click dismiss button
7. **Screenshot:** After dismissal
8. Verify announcement is hidden
9. Refresh page
10. Verify announcement stays dismissed

**Expected Results:**
- Dismiss button visible on dismissible announcements
- Click hides the announcement
- Dismissed state persists (localStorage or API)

### Test 5: Non-Dismissible Announcement

**Steps:**
1. Login as user
2. Create non-dismissible announcement (admin):
   - Dismissible: No
3. Wait for delivery
4. **Screenshot:** Non-dismissible announcement
5. Verify no dismiss/close button present
6. Verify user cannot hide the announcement
7. Announcement persists until removed by admin

**Expected Results:**
- No dismiss button on non-dismissible announcements
- Announcement remains visible
- Only admin can remove it

### Test 6: Announcement with CTA Button

**Steps:**
1. Login as user
2. Create announcement with CTA (admin):
   - CTA Text: "Learn More"
   - CTA URL: "https://example.com/info"
3. Wait for delivery
4. **Screenshot:** Announcement with CTA button
5. Verify CTA button is visible
6. Click CTA button
7. Verify navigation to CTA URL
8. Verify link opens correctly (same tab or new tab)

**Expected Results:**
- CTA button displayed with correct text
- Click navigates to configured URL
- Link behavior matches configuration

### Test 7: Announcement with Custom Colors

**Steps:**
1. Login as user
2. Create announcement with custom colors (admin):
   - Background: #E8F5E9 (light green)
   - Text: #1B5E20 (dark green)
3. Wait for delivery
4. **Screenshot:** Custom colored announcement
5. Verify background color is applied
6. Verify text color is applied
7. Verify text is readable (contrast)

**Expected Results:**
- Custom colors applied correctly
- Text remains readable
- Styling consistent with preview

### Test 8: Announcement with Featured Image

**Steps:**
1. Login as user
2. Create announcement with image (admin):
   - Featured Image URL: valid image URL
3. Wait for delivery
4. **Screenshot:** Announcement with image
5. Verify image is displayed
6. Verify image is properly sized/formatted
7. Verify image doesn't break layout

**Expected Results:**
- Featured image displayed
- Image properly sized
- Layout remains intact

### Test 9: Multiple Announcements Stacking

**Steps:**
1. Login as user
2. Create first announcement (admin)
3. Wait for delivery
4. Create second announcement (admin)
5. Wait for delivery
6. **Screenshot:** Multiple announcements
7. Verify both announcements visible
8. Verify ordering (newest first or by priority)
9. Dismiss first announcement (if dismissible)
10. Verify second remains visible

**Expected Results:**
- Multiple announcements can display
- Proper ordering (priority or time-based)
- Dismissing one doesn't affect others

### Test 10: Scheduled Announcement Activation

**Steps:**
1. Login as user
2. Create scheduled announcement (admin):
   - Start time: 1-2 minutes from now
3. Verify announcement not visible yet
4. **Screenshot:** Before scheduled time
5. Wait for scheduled start time
6. **Screenshot:** After scheduled time
7. Verify announcement appears at scheduled time
8. Verify no manual trigger needed

**Expected Results:**
- Scheduled announcements activate at start time
- Real-time delivery at activation
- No user action required

### Test 11: Announcement Removal

**Steps:**
1. Login as user
2. Create an announcement (admin)
3. Wait for delivery to user
4. **Screenshot:** Announcement visible
5. Delete the announcement (admin)
6. **Screenshot:** User's screen after deletion
7. Verify announcement is removed from user's view
8. Verify removal is immediate (via WebSocket)

**Expected Results:**
- Deletion triggers WebSocket update
- Announcement removed without refresh
- Clean removal from UI

### Test 12: Organization-Scoped Announcement

**Steps:**
1. Login as User A (Org 1)
2. Login as User B (Org 2) in separate browser
3. Create org-scoped announcement for Org 1 (admin)
4. **Screenshot:** User A sees announcement
5. **Screenshot:** User B does not see announcement
6. Verify User A receives announcement
7. Verify User B does NOT receive announcement

**Expected Results:**
- Org-scoped announcements reach only target org
- Other orgs don't receive the announcement
- Proper filtering by organization

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| WS | `/ws` | WebSocket for real-time delivery |
| POST | `/announcements` | Create announcement (admin) |
| DELETE | `/announcements/{id}` | Delete announcement (admin) |

## WebSocket Message Format

**Announcement Message:**
```json
{
  "type": "announcement",
  "payload": {
    "action": "create",
    "announcement": {
      "id": "uuid",
      "title": "Real-time Test",
      "body": "This is a test announcement",
      "priority": "high",
      "dismissible": true,
      "background_color": "#FFF3CD",
      "text_color": "#856404",
      "featured_image_url": "https://...",
      "cta_button": {
        "text": "Learn More",
        "url": "https://..."
      }
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Announcement Removal Message:**
```json
{
  "type": "announcement",
  "payload": {
    "action": "delete",
    "announcement_id": "uuid"
  },
  "timestamp": "2024-01-15T10:35:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Announcement banner | Banner/card component at top of page |
| Announcement title | Heading within announcement |
| Announcement body | Text content within announcement |
| Dismiss button | Close/X button on dismissible announcements |
| CTA button | Button with CTA text |
| Priority badge | Badge/indicator showing priority |

## Success Criteria

- Announcements delivered in real-time via WebSocket
- All announcement types display correctly
- Priority styling is applied
- Dismissible behavior works correctly
- CTA buttons navigate correctly
- Custom colors are applied
- Featured images display properly
- Multiple announcements stack correctly
- Scheduled activation works
- Deletion removes announcement in real-time
- Organization scoping works

## Notes

- Test with WebSocket disconnected (fallback behavior)
- Verify announcement persistence on page refresh
- Test with multiple users simultaneously
- Monitor for duplicate announcements
- Verify i18n for announcement UI elements
- Test mobile responsive display
