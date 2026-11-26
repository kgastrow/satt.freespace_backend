# E2E Test: Cancel Deletion

## Test Description
Validate that users with a pending account deletion request can cancel the deletion and restore their account to normal status.

## User Story
As a user who requested account deletion
I want to cancel my deletion request
So that I can continue using my account if I change my mind

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)
- User has a pending deletion request

## Test Steps

### Test 1: Cancel Deletion from Settings Page

**Steps:**
1. Ensure user has pending deletion (request deletion first if needed)
2. Navigate to `/settings/danger/delete`
3. Wait for page to load
4. **Screenshot:** Deletion status showing pending
5. Verify "Cancel Deletion" button is visible
6. Click "Cancel Deletion" button
7. Verify confirmation dialog appears
8. **Screenshot:** Cancel confirmation dialog
9. Click "Confirm" or "Yes, Cancel Deletion"
10. Wait for operation to complete
11. **Screenshot:** Account restored state
12. Verify success toast notification
13. Verify page shows normal delete option (not pending status)

**Expected Results:**
- Cancel button visible when deletion pending
- Confirmation required before cancellation
- Account status returns to normal
- Success feedback provided
- Delete option available again

### Test 2: Cancel Deletion from Recovery Prompt

**Steps:**
1. Ensure user has pending deletion
2. Log out of the application
3. Log in with test credentials
4. **Screenshot:** Login page or dashboard with recovery prompt
5. Verify recovery/warning prompt appears about pending deletion
6. Locate "Cancel Deletion" or "Recover Account" option in prompt
7. Click the cancel/recover option
8. **Screenshot:** After clicking cancel from prompt
9. Verify cancellation dialog or direct cancellation
10. Complete cancellation flow
11. Verify account restored

**Expected Results:**
- Recovery prompt shown on login
- Easy access to cancel from prompt
- Same cancellation flow as settings page
- Account fully restored after cancellation

### Test 3: Verify Account Functionality After Cancellation

**Steps:**
1. Cancel deletion request (Test 1)
2. Navigate to `/settings/account/profile`
3. **Screenshot:** Profile page after cancellation
4. Verify all profile features work normally
5. Navigate to `/settings/security/password`
6. Verify security settings accessible
7. Navigate to `/files`
8. Verify files are accessible
9. Navigate to dashboard
10. Verify full application access

**Expected Results:**
- All account features functional after cancellation
- No restrictions or warnings
- Data remains intact
- Normal user experience restored

### Test 4: Re-request Deletion After Cancellation

**Steps:**
1. Cancel deletion request if pending
2. Navigate to `/settings/danger/delete`
3. **Screenshot:** Delete option available after previous cancellation
4. Click "Request Deletion" button
5. Complete deletion request flow
6. **Screenshot:** New deletion request pending
7. Verify new deletion is scheduled
8. Verify scheduled date is 30 days from now (not from original request)

**Expected Results:**
- Can re-request deletion after cancellation
- New 30-day grace period starts fresh
- Previous request has no effect on new request
- Normal deletion flow works

### Test 5: Cancel Deletion - Confirmation Dialog Details

**Steps:**
1. Ensure user has pending deletion
2. Navigate to `/settings/danger/delete`
3. Click "Cancel Deletion" button
4. **Screenshot:** Full confirmation dialog
5. Verify dialog shows:
   - Clear title about cancelling deletion
   - Explanation of what cancellation means
   - Confirm and Cancel buttons
6. Click "Cancel" button in dialog (not confirm)
7. Verify dialog closes, deletion still pending
8. Click "Cancel Deletion" again
9. Click "Confirm" this time
10. Verify deletion cancelled

**Expected Results:**
- Dialog provides clear information
- Can dismiss dialog without cancelling
- Confirm action actually cancels deletion
- Cancel (dismiss) leaves status unchanged

### Test 6: API Error Handling During Cancellation

**Steps:**
1. Ensure user has pending deletion
2. Navigate to `/settings/danger/delete`
3. Simulate network error (disconnect network or mock API error)
4. Click "Cancel Deletion" button
5. Confirm in dialog
6. **Screenshot:** Error state
7. Verify error message displayed
8. Verify deletion status unchanged
9. Restore network connection
10. Retry cancellation
11. Verify success

**Expected Results:**
- Network errors handled gracefully
- Clear error message shown
- Status not corrupted by failed request
- Can retry after error

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/users/me/delete` | Get current deletion status |
| POST | `/users/me/delete/cancel` | Cancel deletion request |

## Request/Response Format

**Get Deletion Status Response (Pending):**
```json
{
  "deletion_requested": true,
  "deletion_requested_time": "2024-01-01T00:00:00Z",
  "deletion_scheduled_date": "2024-02-01T00:00:00Z",
  "days_remaining": 25
}
```

**Cancel Deletion Response:**
```json
{
  "message": "Account deletion cancelled successfully",
  "deletion_requested": false
}
```

**Get Deletion Status Response (After Cancel):**
```json
{
  "deletion_requested": false,
  "deletion_requested_time": null,
  "deletion_scheduled_date": null
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Cancel deletion button | `getByRole('button', { name: /cancel deletion/i })` |
| Confirm button (dialog) | `getByRole('button', { name: /confirm|yes/i })` within dialog |
| Dismiss button (dialog) | `getByRole('button', { name: /cancel|no|close/i })` within dialog |
| Status indicator | Badge or text showing deletion status |
| Recovery prompt | Alert or banner with recovery option |
| Success toast | Toast notification component |
| Error message | Error alert or toast |

## Success Criteria

- Cancellation requires confirmation
- Account status returns to normal after cancel
- All account features work normally after cancellation
- Can re-request deletion with fresh 30-day period
- Error handling prevents data corruption
- Clear feedback throughout the process

## Notes

- Verify cancellation email notification sent to user
- Test cancellation at various points in grace period (day 1, day 15, day 29)
- Verify audit log records cancellation
- Check that organization admin can see status change
- Test cancellation with slow network conditions
- Verify i18n translations for all dialog text
