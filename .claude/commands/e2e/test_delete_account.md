# E2E Test: Delete Account

## Test Description
Validate that authenticated users can request account deletion with a 30-day recovery grace period, and can cancel the deletion request before permanent deletion.

## User Story
As an authenticated user
I want to request deletion of my account
So that I can remove my data from the platform while having a grace period to recover if needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Request Account Deletion

**Steps:**
1. Navigate to `/settings/danger/delete`
2. Wait for delete account page to load
3. **Screenshot:** Delete account page (danger zone)
4. Verify warning message about deletion consequences
5. Verify 30-day recovery period information displayed
6. Locate "Request Deletion" or "Delete Account" button
7. Click the delete button
8. Verify confirmation dialog appears
9. **Screenshot:** Deletion confirmation dialog
10. Verify dialog requires typing "DELETE" to confirm
11. Type "DELETE" in confirmation input
12. Click "Confirm" button
13. Wait for deletion request to process
14. **Screenshot:** Deletion requested state
15. Verify success message about deletion scheduled

**Expected Results:**
- Danger zone styling indicates destructive action
- Clear warning about consequences
- Recovery period explained
- Confirmation requires explicit action (typing "DELETE")
- Deletion request is scheduled, not immediate

### Test 2: View Deletion Request Status

**Steps:**
1. Navigate to `/settings/danger/delete` (after deletion requested)
2. Wait for page to load
3. **Screenshot:** Deletion status display
4. Verify status shows "Deletion Requested" or similar
5. Verify scheduled deletion date is displayed
6. Verify remaining days until permanent deletion shown
7. Verify "Cancel Deletion" button is visible

**Expected Results:**
- Clear status indicator for pending deletion
- Exact date of permanent deletion shown
- Days remaining countdown displayed
- Cancel option prominently available

### Test 3: Cancel Deletion Request

**Steps:**
1. Navigate to `/settings/danger/delete` (with pending deletion)
2. **Screenshot:** Page with cancel option
3. Click "Cancel Deletion" button
4. Verify confirmation dialog appears
5. **Screenshot:** Cancel confirmation dialog
6. Confirm cancellation
7. Wait for operation to complete
8. **Screenshot:** After cancellation
9. Verify success message
10. Verify account is no longer scheduled for deletion
11. Verify normal delete option is restored

**Expected Results:**
- Cancellation requires confirmation
- Account status returns to normal
- User can continue using account normally
- Can re-request deletion after cancellation

### Test 4: Login During Deletion Grace Period

**Steps:**
1. Request account deletion (Test 1)
2. Log out of the application
3. Log back in with same credentials
4. **Screenshot:** Login with pending deletion
5. Verify login succeeds
6. Verify warning banner about pending deletion
7. Verify option to cancel deletion from banner/prompt

**Expected Results:**
- Account remains accessible during grace period
- Clear notification about pending deletion
- Easy access to cancel deletion

### Test 5: Deletion Confirmation Text Validation

**Steps:**
1. Navigate to `/settings/danger/delete`
2. Click delete button to open dialog
3. **Screenshot:** Empty confirmation input
4. Verify confirm button is disabled
5. Type incorrect text: "delete" (lowercase)
6. Verify button still disabled
7. Type partial text: "DELET"
8. Verify button still disabled
9. Type correct text: "DELETE"
10. Verify button becomes enabled
11. **Screenshot:** Enabled confirm button

**Expected Results:**
- Exact text match required (case-sensitive)
- Button disabled until exact match
- Prevents accidental deletion

### Test 6: Account Access After Deletion Period (Edge Case)

**Steps:**
1. Set up a test account with deletion requested
2. Simulate time passage past 30-day period (backend test)
3. Attempt to log in
4. **Screenshot:** Access denied state
5. Verify account is no longer accessible
6. Verify appropriate error message

**Expected Results:**
- Account becomes inaccessible after grace period
- Clear message that account was deleted
- No data accessible

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/me/delete` | Request account deletion |
| GET | `/users/me/delete` | Get deletion status |
| POST | `/users/me/delete/cancel` | Cancel deletion request |

## Request/Response Format

**Request Deletion Response:**
```json
{
  "message": "Account deletion scheduled",
  "deletion_requested": true,
  "deletion_scheduled_date": "2024-02-01T00:00:00Z",
  "recovery_deadline": "2024-02-01T00:00:00Z"
}
```

**Get Deletion Status Response:**
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
  "message": "Account deletion cancelled",
  "deletion_requested": false
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Delete account button | `getByRole('button', { name: /delete account|request deletion/i })` |
| Confirmation input | `input[id="confirm-text"]` or `getByPlaceholderText(/DELETE/i)` |
| Confirm button | `getByRole('button', { name: /confirm/i })` within dialog |
| Cancel deletion button | `getByRole('button', { name: /cancel deletion/i })` |
| Status badge | Badge component showing deletion status |
| Scheduled date | Text showing deletion scheduled date |
| Days remaining | Text showing countdown |
| Warning banner | Alert component with deletion warning |

## Success Criteria

- Deletion request creates 30-day grace period
- Clear status display of pending deletion
- Cancellation reverses deletion request
- Account accessible during grace period
- Confirmation requires exact "DELETE" text
- Cannot accidentally delete account
- User receives appropriate warnings and information

## Notes

- Verify email notification sent when deletion requested
- Verify email notification sent before deletion executed
- Test with users who have various data (files, settings, etc.)
- Verify data retention policies are followed
- Check that deletion affects all user data appropriately
- Test organization admin's view of user with pending deletion
- Verify i18n for danger zone messaging
