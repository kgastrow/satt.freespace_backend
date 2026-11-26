# E2E Test: Maintenance Mode Management

## Test Description
Validate that administrators can enable/disable maintenance mode, schedule maintenance windows, and manage maintenance history.

## User Story
As an administrator
I want to manage maintenance mode
So that I can perform system updates while informing users of downtime

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin/super admin user with maintenance mode permissions

## Test Steps

### Test 1: Access Maintenance Settings Page

**Steps:**
1. Login as admin user
2. Navigate to maintenance settings page (e.g., `/admin/maintenance`)
3. **Screenshot:** Maintenance settings page loaded
4. Verify page title "Maintenance Settings" or similar
5. Verify current status is displayed (enabled/disabled)
6. Verify form fields are present:
   - Enabled toggle
   - Message textarea
   - Scheduled start/end datetime
   - Allow super admin access toggle
7. Verify maintenance history section is present

**Expected Results:**
- Admin can access maintenance settings
- Current config fetched from `GET /maintenance/config`
- All form fields are visible
- History section shows past maintenance windows

### Test 2: Enable Maintenance Mode Immediately

**Steps:**
1. Navigate to maintenance settings page
2. Verify maintenance is currently disabled
3. Enter message: "The system is undergoing scheduled maintenance. Please check back soon."
4. Toggle "Enabled" to ON
5. Leave scheduled times empty (immediate)
6. **Screenshot:** Enabled maintenance form
7. Click "Save" button
8. Wait for confirmation
9. **Screenshot:** Maintenance enabled confirmation
10. Verify success notification
11. Verify status shows "Active"

**Expected Results:**
- Maintenance mode activates immediately
- Message is saved
- API call: `PUT /maintenance`
- Status updates to active
- Non-admin users should see maintenance page

### Test 3: Verify Maintenance Page Display

**Steps:**
1. Enable maintenance mode (from Test 2)
2. Open incognito/private browser window
3. Navigate to application URL
4. **Screenshot:** Maintenance page for regular users
5. Verify maintenance page is displayed
6. Verify custom message is shown
7. Verify no access to regular application pages
8. Back in admin session, verify admin can still access dashboard

**Expected Results:**
- Regular users see maintenance page
- Custom message displayed
- No bypass for regular users
- Admin/super admin can still access (if configured)

### Test 4: Allow Super Admin Access During Maintenance

**Steps:**
1. Navigate to maintenance settings
2. Enable maintenance mode
3. Toggle "Allow Super Admin Access" to ON
4. **Screenshot:** Super admin access enabled
5. Save changes
6. Login as super admin in separate browser
7. Verify super admin can access application
8. Login as regular admin
9. Verify behavior based on configuration

**Expected Results:**
- Super admin bypass works when enabled
- Regular users still blocked
- Setting can be toggled

### Test 5: Disable Maintenance Mode

**Steps:**
1. Navigate to maintenance settings (maintenance active)
2. Toggle "Enabled" to OFF
3. **Screenshot:** Disabling maintenance
4. Click "Save" button
5. Verify success notification
6. Verify status shows "Inactive" or "Disabled"
7. Open incognito browser
8. **Screenshot:** Normal access restored
9. Verify application is accessible to all users

**Expected Results:**
- Maintenance mode deactivates
- All users regain access
- Status updates correctly
- History records the maintenance window

### Test 6: Schedule Future Maintenance

**Steps:**
1. Navigate to maintenance settings
2. Ensure maintenance is currently disabled
3. Enter message: "Scheduled maintenance window"
4. Set scheduled start: 1 hour from now
5. Set scheduled end: 3 hours from now
6. **Screenshot:** Scheduled maintenance form
7. Click "Save" button
8. Verify success notification
9. Verify status shows "Scheduled"
10. **Screenshot:** Scheduled status display
11. Verify countdown or scheduled time displayed

**Expected Results:**
- Scheduled maintenance is saved
- Status shows "Scheduled"
- Start and end times recorded
- Maintenance won't activate until scheduled time

### Test 7: Schedule Validation - End Before Start

**Steps:**
1. Navigate to maintenance settings
2. Set scheduled start: 3 hours from now
3. Set scheduled end: 1 hour from now (before start)
4. **Screenshot:** Invalid schedule
5. Try to save
6. Verify validation error
7. Verify error message indicates end must be after start

**Expected Results:**
- Validation prevents invalid time range
- Clear error message shown
- Form doesn't submit with invalid data

### Test 8: Schedule Validation - Start in Past

**Steps:**
1. Navigate to maintenance settings
2. Set scheduled start: 1 hour ago (past time)
3. Set scheduled end: 2 hours from now
4. Try to save
5. **Screenshot:** Past start time error
6. Verify validation error
7. Verify error message indicates start must be in future

**Expected Results:**
- Validation prevents past start times
- Clear error message shown
- Must use immediate mode or future scheduling

### Test 9: Cancel Scheduled Maintenance

**Steps:**
1. Schedule a future maintenance window (Test 6)
2. Navigate to maintenance settings
3. Verify scheduled maintenance is shown
4. Click "Cancel" or clear scheduled times
5. **Screenshot:** Cancelling scheduled maintenance
6. Save changes
7. Verify status changes to "Inactive"
8. Verify scheduled maintenance is cancelled

**Expected Results:**
- Scheduled maintenance can be cancelled
- Status reverts to inactive
- History may show cancelled entry

### Test 10: View Maintenance History

**Steps:**
1. Navigate to maintenance settings
2. Scroll to maintenance history section
3. **Screenshot:** Maintenance history table
4. Verify history shows past maintenance windows:
   - Status (active/completed/scheduled/cancelled)
   - Scheduled start time
   - Actual start time
   - Actual end time
   - Started by user
   - Ended by user
5. Verify status badges have appropriate colors:
   - Active: red/destructive
   - Completed: default
   - Scheduled: secondary
   - Cancelled: outline

**Expected Results:**
- History fetched from `GET /maintenance/history`
- All past maintenance windows listed
- Status badges color-coded
- Audit information shows who started/ended

### Test 11: Maintenance Auto-End

**Steps:**
1. Schedule maintenance with short duration (if testable)
2. OR manually enable and wait for scheduled end
3. Verify maintenance automatically ends at scheduled time
4. Verify history shows auto-completion
5. Verify users regain access

**Expected Results:**
- Scheduled end time is respected
- Maintenance auto-disables
- History records completion
- No manual intervention needed

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/maintenance/config` | Get current maintenance configuration |
| PUT | `/maintenance` | Update maintenance settings |
| GET | `/maintenance/history` | Get maintenance history |

## Request/Response Format

**Update Maintenance Request:**
```json
{
  "enabled": true,
  "message": "The system is undergoing scheduled maintenance.",
  "scheduled_start": "2024-01-15T22:00:00Z",
  "scheduled_end": "2024-01-16T02:00:00Z",
  "allow_super_admin": true
}
```

**Maintenance Config Response:**
```json
{
  "enabled": true,
  "message": "The system is undergoing scheduled maintenance.",
  "scheduled_start": "2024-01-15T22:00:00Z",
  "scheduled_end": "2024-01-16T02:00:00Z",
  "allow_super_admin": true,
  "status": "scheduled",
  "actual_start": null,
  "started_by": null
}
```

**Maintenance History Response:**
```json
{
  "history": [
    {
      "id": "uuid",
      "status": "completed",
      "scheduled_start": "2024-01-10T22:00:00Z",
      "scheduled_end": "2024-01-11T02:00:00Z",
      "actual_start": "2024-01-10T22:00:00Z",
      "actual_end": "2024-01-11T01:30:00Z",
      "started_by": { "id": "uuid", "email": "admin@example.com" },
      "ended_by": { "id": "uuid", "email": "admin@example.com" },
      "message": "Scheduled database maintenance"
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Enabled toggle | `getByRole('switch', { name: /enabled/i })` |
| Message textarea | `getByLabelText(/message/i)` |
| Scheduled start | `input[type="datetime-local"]` for start |
| Scheduled end | `input[type="datetime-local"]` for end |
| Allow super admin toggle | `getByRole('switch', { name: /super admin/i })` |
| Save button | `getByRole('button', { name: /save/i })` |
| Status badge | Badge showing current status |
| History table | Table with history rows |

## Success Criteria

- Enable/disable maintenance mode works
- Custom message is displayed to users
- Scheduled maintenance saves correctly
- Time validation prevents invalid ranges
- Super admin bypass works when enabled
- History tracks all maintenance windows
- Auto-end at scheduled time works
- Status badges display correctly

## Notes

- Test in separate browser for user experience
- Verify WebSocket notification of maintenance (if implemented)
- Consider grace period before maintenance starts
- Test with different timezones
- Verify maintenance page is styled appropriately
- Test mobile responsive maintenance page
