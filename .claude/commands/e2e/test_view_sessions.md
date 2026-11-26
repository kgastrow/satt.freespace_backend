# E2E Test: View Sessions

## Test Description
Validate the session management page that displays all active user sessions with device information, location, and management options.

## User Story
As a security-conscious user
I want to view all my active sessions
So that I can monitor account access and detect unauthorized logins

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated test user
- User has multiple active sessions (login from different devices/browsers)

## Test Steps

### Test 1: Navigate to Sessions Page

**Setup:**
- User logged in

**Steps:**
1. Login as test user
2. Navigate to `/settings/account/sessions`
3. **Screenshot:** Sessions page loaded
4. Verify page title displays "Active Sessions" or similar
5. Verify page description explains session management
6. Verify at least one session is listed (current session)

**Expected Results:**
- Sessions page accessible
- Clear title and description
- Current session displayed

### Test 2: Current Session Identification

**Steps:**
1. On sessions page
2. Locate current session in list
3. **Screenshot:** Current session highlighted
4. Verify current session has "Current session" badge
5. Verify current session shows correct browser info
6. Verify revoke button may be disabled/hidden for current session

**Expected Results:**
- Current session clearly marked
- Badge or visual indicator
- Cannot revoke current session (or special handling)

### Test 3: Session Card Information Display

**Steps:**
1. On sessions page with sessions listed
2. Examine a session card
3. **Screenshot:** Session card details
4. Verify device type icon (Mobile, Tablet, Desktop)
5. Verify browser name displayed
6. Verify operating system displayed
7. Verify location/IP information shown
8. Verify "Last active" timestamp displayed

**Expected Results:**
- Device type shown with icon
- Browser and OS information accurate
- Location/IP displayed
- Last active time shown

### Test 4: Multiple Sessions Display

**Setup:**
- Login from multiple browsers/devices

**Steps:**
1. Create additional sessions (different browsers)
2. Navigate to sessions page
3. **Screenshot:** Multiple sessions listed
4. Verify all sessions appear in list
5. Verify each session has distinct device info
6. Verify sessions ordered by last active (most recent first)

**Expected Results:**
- All active sessions displayed
- Each session has accurate device info
- Proper ordering of sessions

### Test 5: Session Location Display

**Steps:**
1. On sessions page
2. Examine session location information
3. **Screenshot:** Location details
4. Verify country flag emoji displayed (if available)
5. Verify city/region shown (if available)
6. Verify "Unknown location" for VPN/proxy
7. Verify IP address displayed

**Expected Results:**
- Location derived from IP
- Country flag emoji shown
- Graceful handling of unknown locations
- IP address visible

### Test 6: Device Type Icons

**Steps:**
1. Create sessions from different device types
2. Navigate to sessions page
3. **Screenshot:** Different device type icons
4. Verify mobile device shows phone icon
5. Verify tablet shows tablet icon
6. Verify desktop shows computer icon

**Expected Results:**
- Appropriate icons for each device type
- Visual distinction between device types

### Test 7: Last Active Timestamp

**Steps:**
1. On sessions page
2. Note last active time for a session
3. Perform action in that session
4. Refresh sessions page
5. **Screenshot:** Updated last active time
6. Verify timestamp updated
7. Verify relative time format (e.g., "2 minutes ago")

**Expected Results:**
- Last active time reflects real usage
- Human-readable relative format
- Updates on activity

### Test 8: Empty Sessions State

**Setup:**
- This is a theoretical scenario (user always has current session)

**Steps:**
1. Note expected behavior for no sessions (shouldn't happen)
2. Verify graceful handling if API returns empty

**Expected Results:**
- At minimum, current session always shown
- Empty state message if somehow no sessions

### Test 9: Sessions Page Loading State

**Steps:**
1. Navigate to sessions page
2. Observe loading state
3. **Screenshot:** Loading skeleton/spinner
4. Verify loading indicator shown
5. Verify content appears after load

**Expected Results:**
- Loading state during data fetch
- Smooth transition to loaded content
- No layout shift

### Test 10: Sessions Page Error State

**Setup:**
- Simulate API error (network issue)

**Steps:**
1. Simulate network failure
2. Navigate to sessions page
3. **Screenshot:** Error state
4. Verify error message displayed
5. Verify retry option available
6. Re-enable network and retry
7. Verify sessions load correctly

**Expected Results:**
- Graceful error handling
- Clear error message
- Retry functionality

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/sessions` | Fetch all active sessions |

## Response Format

**Sessions List Response:**
```json
{
  "items": [
    {
      "id": "session_uuid",
      "device_type": "Desktop",
      "browser": "Chrome",
      "os": "Windows 10",
      "ip_address": "192.168.1.100",
      "location": {
        "city": "New York",
        "region": "NY",
        "country": "US",
        "country_code": "US"
      },
      "last_active": "2024-01-15T10:30:00Z",
      "created_at": "2024-01-10T08:00:00Z",
      "is_current": true
    }
  ],
  "total": 1
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page title | Heading with "Sessions" text |
| Session card | Card component for each session |
| Current badge | Badge with "Current session" text |
| Device icon | Icon based on device_type |
| Browser info | Text showing browser name |
| Location info | Text with city/country |
| IP address | Text with IP format |
| Last active | Timestamp or relative time |
| Loading state | Skeleton or spinner component |

## Success Criteria

- Sessions page loads successfully
- Current session clearly identified
- All session details displayed accurately
- Device type icons correct
- Location information shown when available
- Last active timestamps accurate
- Multiple sessions handled correctly
- Loading and error states work properly

## Notes

- Device detection uses User-Agent parsing
- Location lookup uses IP geolocation service
- Sessions may be grouped by device
- Consider pagination for users with many sessions
- Verify i18n for all labels and relative times
