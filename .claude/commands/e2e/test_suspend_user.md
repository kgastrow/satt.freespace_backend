# E2E Test: Suspend User

## Test Description
Validate that organization admins can suspend and unsuspend user accounts, temporarily revoking their access.

## User Story
As an organization admin
I want to suspend user accounts
So that I can temporarily disable access without deleting the account

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with `users:suspend` permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- At least one active test user exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Suspend Active User

**Steps:**
1. Navigate to `/admin/users`
2. Wait for user list to load
3. Find an active user (status: Active)
4. Click actions dropdown for that user
5. **Screenshot:** Actions dropdown with suspend option
6. Click "Suspend" option
7. Verify suspension dialog appears
8. **Screenshot:** Suspension dialog
9. Enter suspension reason (optional): "Policy violation"
10. Toggle "Notify user" checkbox if available
11. Click "Confirm" or "Suspend" button
12. Wait for operation to complete
13. **Screenshot:** After suspension
14. Verify success notification
15. Verify user status changed to "Suspended"

**Expected Results:**
- Suspend option available for active users
- Dialog allows reason entry
- User status changes to suspended
- Success notification displayed

### Test 2: Suspension Dialog Options

**Steps:**
1. Navigate to `/admin/users`
2. Open suspend dialog for an active user
3. **Screenshot:** Full suspension dialog
4. Verify dialog contains:
   - Suspension reason textarea
   - Send notification checkbox
   - Confirm and Cancel buttons
5. Verify reason is optional
6. Close dialog without confirming

**Expected Results:**
- Dialog provides reason field
- Notification option available
- Cancel closes without action

### Test 3: Unsuspend Suspended User

**Steps:**
1. Navigate to `/admin/users`
2. Find a suspended user (status: Suspended)
3. Click actions dropdown for that user
4. **Screenshot:** Actions showing unsuspend option
5. Click "Unsuspend" option
6. Verify confirmation dialog appears
7. **Screenshot:** Unsuspend confirmation
8. Click "Confirm" button
9. Wait for operation to complete
10. **Screenshot:** After unsuspend
11. Verify success notification
12. Verify user status changed to "Active"

**Expected Results:**
- Unsuspend option shown for suspended users
- Confirmation required
- User status returns to active
- Success notification displayed

### Test 4: Suspended User Status Display

**Steps:**
1. Suspend a user (Test 1)
2. Navigate to `/admin/users`
3. Find the suspended user in list
4. **Screenshot:** Suspended user row
5. Verify status badge shows "Suspended"
6. Verify badge has warning/red styling
7. Verify other user info still visible

**Expected Results:**
- Suspended status clearly visible
- Distinct styling for suspended badge
- All user info still displayed

### Test 5: Suspended User Cannot Login

**Steps:**
1. Note credentials of suspended user
2. Log out of admin account
3. Attempt to log in as suspended user
4. **Screenshot:** Login attempt with suspended account
5. Verify login fails
6. Verify appropriate error message (account suspended)

**Expected Results:**
- Suspended users cannot authenticate
- Clear error message about suspension
- No access to application

### Test 6: Cannot Suspend Self

**Steps:**
1. Navigate to `/admin/users`
2. Find current logged-in admin in list
3. Click actions dropdown for self
4. **Screenshot:** Self user actions
5. Verify "Suspend" option is:
   - Not present, OR
   - Disabled

**Expected Results:**
- Cannot suspend own account
- UI prevents self-suspension

### Test 7: Cannot Suspend Super Admin (Non-Super Admin)

**Steps:**
1. Log in as regular admin (not super admin)
2. Navigate to `/admin/users`
3. Find a super admin user in list
4. Click actions dropdown
5. **Screenshot:** Actions for super admin
6. Verify Suspend option not available or disabled

**Expected Results:**
- Regular admins cannot suspend super admins
- Appropriate restriction in UI

### Test 8: Suspend Without Reason

**Steps:**
1. Navigate to `/admin/users`
2. Open suspend dialog for active user
3. Leave reason field empty
4. Click "Suspend" button
5. **Screenshot:** Suspension without reason
6. Verify suspension succeeds (reason is optional)
7. Verify user is suspended

**Expected Results:**
- Reason field is optional
- Suspension works without reason
- System handles empty reason gracefully

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/{id}/suspend` | Suspend user |
| POST | `/users/{id}/unsuspend` | Unsuspend user |

## Request/Response Format

**Suspend User Request:**
```json
{
  "reason": "Policy violation",
  "notify_user": true
}
```

**Suspend User Response:**
```json
{
  "message": "User suspended successfully",
  "message_code": "user.suspended",
  "user_id": "uuid"
}
```

**Unsuspend User Response:**
```json
{
  "message": "User unsuspended successfully",
  "message_code": "user.unsuspended",
  "user_id": "uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Suspend option | `getByRole('menuitem', { name: /suspend/i })` |
| Unsuspend option | `getByRole('menuitem', { name: /unsuspend/i })` |
| Suspension dialog | Dialog component |
| Reason textarea | `textarea` or `getByLabelText(/reason/i)` |
| Notify checkbox | `checkbox` for notification option |
| Confirm button | `getByRole('button', { name: /confirm|suspend/i })` |
| Status badge | Badge showing "Suspended" or "Active" |

## Success Criteria

- Active users can be suspended
- Suspended users can be unsuspended
- Suspension reason can be provided
- Suspended users cannot login
- Cannot suspend self or super admin
- Status change reflected immediately
- Proper notifications sent

## Notes

- Verify email notification sent to suspended user
- Test suspension impact on active sessions
- Check audit log for suspension events
- Verify suspension reason stored and viewable
- Test with users who have active file shares
- Verify i18n for suspension messages
