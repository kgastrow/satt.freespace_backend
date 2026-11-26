# E2E Test: Delete Role

## Test Description
Validate that super admins can delete roles with appropriate confirmation and error handling.

## User Story
As a super admin
I want to delete roles that are no longer needed
So that I can keep the role system clean and manageable

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
  - Organization: test-org
- At least one deletable role exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Delete Confirmation

**Steps:**
1. Navigate to `/admin/roles`
2. Wait for roles to load
3. Find a role to delete
4. Click actions dropdown for that role
5. Click "Delete" option
6. **Screenshot:** Delete confirmation dialog
7. Verify confirmation dialog appears
8. Verify dialog shows role name
9. Verify warning message about consequences

**Expected Results:**
- Confirmation dialog shown
- Role clearly identified
- Warning about deletion impact

### Test 2: Confirm Delete Role

**Steps:**
1. Open delete confirmation for a role
2. Note the role name
3. **Screenshot:** Before confirming delete
4. Click "Confirm" or "Delete" button
5. Wait for API response
6. **Screenshot:** After deletion
7. Verify success toast notification
8. Verify role removed from table
9. Verify table updates (count decreases)

**Expected Results:**
- Role deleted successfully
- Success notification shown
- Role no longer in list

### Test 3: Cancel Delete

**Steps:**
1. Open delete confirmation for a role
2. Note the role in the list
3. **Screenshot:** Confirmation dialog
4. Click "Cancel" button
5. Verify dialog closes
6. Verify role still in list
7. Verify no notification shown

**Expected Results:**
- Cancel closes dialog
- No deletion occurs
- Role preserved

### Test 4: Close Confirmation via X Button

**Steps:**
1. Open delete confirmation for a role
2. Click X button in dialog header
3. Verify dialog closes
4. Verify role still in list

**Expected Results:**
- X button closes dialog
- Same behavior as Cancel

### Test 5: Loading State During Delete

**Steps:**
1. Open delete confirmation for a role
2. Click "Confirm" button
3. **Screenshot:** Loading state
4. Verify button shows loading indicator
5. Verify button is disabled
6. Verify Cancel button may be disabled
7. Wait for completion

**Expected Results:**
- Loading indicator shown
- Prevents double-click
- Operation completes

### Test 6: Delete Error Handling

**Steps:**
1. Attempt to delete a role that cannot be deleted (if exists)
2. Click "Confirm" button
3. **Screenshot:** Error response
4. Verify error toast notification
5. Verify dialog closes or shows error
6. Verify role still in list

**Expected Results:**
- Error message displayed
- Role not deleted on failure
- Can close dialog after error

### Test 7: Cannot Delete Role Assigned to Users

**Steps:**
1. Ensure a role is assigned to at least one user
2. Open delete confirmation for that role
3. **Screenshot:** Delete attempt
4. Click "Confirm" button
5. Verify operation fails or warns
6. **Screenshot:** Error message
7. Verify role preserved

**Expected Results:**
- Roles in use cannot be deleted (or warning shown)
- Clear error message
- Must unassign first

### Test 8: Delete Multiple Roles in Sequence

**Steps:**
1. Create or identify two deletable roles
2. Delete first role
3. Verify first deletion succeeds
4. Delete second role
5. **Screenshot:** Both roles deleted
6. Verify both removed from list
7. Verify no errors

**Expected Results:**
- Can delete multiple roles sequentially
- Each deletion independent
- Table updates correctly

### Test 9: Delete Last Role on Page

**Steps:**
1. Navigate to last page of roles (if paginated)
2. Ensure only one role on that page
3. Delete that role
4. **Screenshot:** After deleting last item
5. Verify navigation to previous page (or empty state)
6. Verify UI handles gracefully

**Expected Results:**
- Pagination adjusts after deletion
- No empty page left
- Smooth transition

### Test 10: Verify Cascade Effects

**Steps:**
1. Note users assigned to a role (if allowed to delete)
2. Delete the role
3. Navigate to user management
4. Check users that had the role
5. **Screenshot:** User without deleted role
6. Verify role badge removed from users

**Expected Results:**
- Role assignments removed on delete
- Users no longer show deleted role
- No orphaned references

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| DELETE | `/roles/{id}` | Delete role |

## Request/Response Format

**Delete Role Response (Success):**
```json
{
  "message": "Role deleted successfully",
  "id": "role-uuid"
}
```

**Delete Role Response (Error - In Use):**
```json
{
  "detail": "Cannot delete role that is assigned to users"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in role row |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Confirmation dialog | ConfirmDialog component |
| Dialog title | `getByRole('heading')` within dialog |
| Role name in dialog | Text showing role being deleted |
| Confirm button | `getByRole('button', { name: /confirm|delete/i })` with destructive variant |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Close (X) button | `getByRole('button', { name: /close/i })` |
| Loading indicator | Spinner within confirm button |

## Success Criteria

- Delete requires confirmation dialog
- Confirmation shows role being deleted
- Role removed from list after deletion
- Cancel preserves the role
- Loading state prevents double-click
- Roles assigned to users handled (blocked or warned)
- Errors displayed appropriately
- Pagination adjusts after deletion

## Notes

- Verify built-in/system roles cannot be deleted
- Check audit log records role deletion
- Test with roles that have associated permissions
- Verify cascade delete or foreign key handling
- Verify i18n for confirmation messages
- Test keyboard accessibility (Escape to cancel)
