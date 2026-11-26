# E2E Test: Delete User

## Test Description
Validate that organization admins can soft-delete user accounts from their organization.

## User Story
As an organization admin
I want to delete user accounts
So that I can remove users who should no longer have access

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with `users:delete` permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- At least one deletable test user exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Delete User via Actions Dropdown

**Steps:**
1. Navigate to `/admin/users`
2. Wait for user list to load
3. Find a test user to delete (not self, not super admin)
4. Click actions dropdown for that user
5. **Screenshot:** Actions dropdown with delete option
6. Click "Delete" option
7. Verify confirmation dialog appears
8. **Screenshot:** Delete confirmation dialog
9. Verify dialog shows user name/email
10. Click "Confirm" or "Delete" button
11. Wait for deletion to complete
12. **Screenshot:** After deletion
13. Verify success notification
14. Verify user no longer in list

**Expected Results:**
- Delete option available in dropdown
- Confirmation required before deletion
- User removed from list after deletion
- Success notification displayed

### Test 2: Confirm Dialog Shows User Details

**Steps:**
1. Navigate to `/admin/users`
2. Open delete confirmation for a user
3. **Screenshot:** Confirmation dialog content
4. Verify dialog displays:
   - Warning about deletion
   - User's name or email
   - Consequences of deletion
   - Confirm and Cancel buttons
5. Close dialog by clicking Cancel

**Expected Results:**
- Clear identification of user being deleted
- Warning message about consequences
- Both confirm and cancel options

### Test 3: Cancel Delete Operation

**Steps:**
1. Navigate to `/admin/users`
2. Note total user count
3. Open delete confirmation for a user
4. **Screenshot:** Dialog open
5. Click "Cancel" button
6. Verify dialog closes
7. Verify user still in list
8. Verify user count unchanged

**Expected Results:**
- Cancel closes dialog
- No deletion occurs
- User remains in system

### Test 4: Cannot Delete Self

**Steps:**
1. Navigate to `/admin/users`
2. Find current logged-in admin in list
3. Click actions dropdown for self
4. **Screenshot:** Self user actions
5. Verify "Delete" option is:
   - Not present, OR
   - Disabled, OR
   - Shows error when clicked

**Expected Results:**
- Cannot delete own account
- UI prevents or warns about self-deletion

### Test 5: Cannot Delete Super Admin (Non-Super Admin)

**Steps:**
1. Log in as regular admin (not super admin)
2. Navigate to `/admin/users`
3. Find a super admin user in list
4. Click actions dropdown
5. **Screenshot:** Actions for super admin
6. Verify Delete option not available or disabled

**Expected Results:**
- Regular admins cannot delete super admins
- Appropriate restriction in UI

### Test 6: Verify Soft Delete (Not Hard Delete)

**Steps:**
1. Note a user's email before deletion
2. Delete the user (Test 1)
3. **Screenshot:** User removed from active list
4. Check database or admin API for soft-delete flag
5. Verify user record still exists with deleted flag
6. Verify deleted user cannot log in

**Expected Results:**
- User marked as deleted, not removed
- User record preserved for audit
- Deleted user cannot access system

### Test 7: Delete Button Disabled During Operation

**Steps:**
1. Navigate to `/admin/users`
2. Open delete confirmation for a user
3. Click "Confirm" button
4. **Screenshot:** Loading state
5. Verify button shows loading state
6. Verify button is disabled during deletion
7. Wait for completion

**Expected Results:**
- Button shows loading indicator
- Prevents double-click/submission
- Completes with single request

### Test 8: Error Handling - Delete Failure

**Steps:**
1. Navigate to `/admin/users`
2. Simulate network error or API failure
3. Attempt to delete a user
4. Confirm deletion
5. **Screenshot:** Error state
6. Verify error message displayed
7. Verify user still in list

**Expected Results:**
- Error message shown on failure
- User not removed on failure
- Can retry after error

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| DELETE | `/users/{id}` | Soft delete user |

## Request/Response Format

**Delete User Response (Success):**
```json
{
  "message": "User deleted successfully",
  "id": "user-uuid"
}
```

**Delete User Response (Error):**
```json
{
  "detail": "Cannot delete this user"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Confirmation dialog | ConfirmDialog component |
| Dialog title | Dialog header text |
| User identifier | Text showing user email/name in dialog |
| Confirm button | `getByRole('button', { name: /confirm|delete/i })` with destructive variant |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Loading indicator | Spinner or loading text on button |

## Success Criteria

- Delete requires confirmation dialog
- User removed from list after deletion
- Cannot delete self
- Cannot delete super admin (if not super admin)
- Soft delete preserves user record
- Loading state prevents double-submission
- Errors handled gracefully

## Notes

- Verify audit log records deletion
- Test impact on user's files and data
- Check if deleted user appears in any reports
- Verify email notification to deleted user (if applicable)
- Test restoration capability (if implemented)
- Verify i18n for confirmation messages
