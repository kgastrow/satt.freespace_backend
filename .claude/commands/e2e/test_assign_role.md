# E2E Test: Assign Role

## Test Description
Validate that organization admins can assign roles to users, granting them specific permissions.

## User Story
As an organization admin
I want to assign roles to users
So that I can grant appropriate permissions based on their responsibilities

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with role assignment permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- At least one user without all roles exists
- Multiple roles exist in the system
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Role Assignment Dialog

**Steps:**
1. Navigate to `/admin/users`
2. Wait for user list to load
3. Find a user to manage roles for
4. Click actions dropdown for that user
5. **Screenshot:** Actions dropdown with roles option
6. Click "Manage Roles" or "Roles" option
7. Wait for role dialog to open
8. **Screenshot:** Role management dialog
9. Verify current roles displayed
10. Verify available roles shown for assignment

**Expected Results:**
- Manage roles option in dropdown
- Dialog shows current user roles
- Available roles listed for selection

### Test 2: Assign New Role to User

**Steps:**
1. Open role dialog for a user (Test 1)
2. **Screenshot:** Initial roles state
3. Verify available roles not yet assigned
4. Select a role from the dropdown/selector
5. Click "Add" or assign button
6. Wait for assignment to complete
7. **Screenshot:** After role assignment
8. Verify success notification
9. Verify new role appears in user's current roles
10. Close dialog
11. Verify role badge appears in user list

**Expected Results:**
- Role can be selected from available list
- Assignment completes successfully
- New role visible in dialog
- Role badge shown in user table

### Test 3: Assign Multiple Roles

**Steps:**
1. Open role dialog for a user
2. Note current roles (may be empty or few)
3. Assign first role
4. **Screenshot:** First role added
5. Assign second role
6. **Screenshot:** Second role added
7. Verify both roles shown in current roles
8. Close and reopen dialog
9. Verify both roles persisted

**Expected Results:**
- Multiple roles can be assigned
- All assigned roles displayed
- Roles persist after dialog close

### Test 4: Role Dropdown Shows Available Roles

**Steps:**
1. Open role dialog for a user
2. Click role selector/dropdown
3. **Screenshot:** Role dropdown expanded
4. Verify all available roles listed
5. Verify roles already assigned are:
   - Not shown in dropdown, OR
   - Shown as disabled/selected
6. Verify role names and descriptions visible

**Expected Results:**
- Dropdown shows assignable roles
- Already assigned roles handled appropriately
- Role information clear

### Test 5: Prevent Self-Role Assignment (Non-Super Admin)

**Steps:**
1. Log in as non-super admin
2. Navigate to `/admin/users`
3. Find own user in list
4. Open role dialog for self
5. **Screenshot:** Self role management
6. Attempt to assign a higher-privilege role
7. Verify operation fails or is prevented
8. Verify error message about hierarchy violation

**Expected Results:**
- Cannot elevate own permissions
- Hierarchy violation message shown
- Self-assignment may be restricted

### Test 6: Role Assignment Loading State

**Steps:**
1. Open role dialog for a user
2. Select a role to assign
3. Click "Add" button
4. **Screenshot:** Loading state during assignment
5. Verify button shows loading indicator
6. Verify button disabled during operation
7. Wait for completion

**Expected Results:**
- Loading indicator shown
- Button disabled during API call
- Prevents double-assignment

### Test 7: Cancel Role Assignment

**Steps:**
1. Open role dialog for a user
2. Note current roles
3. Select a role (but don't click Add yet)
4. Click "Cancel" or close dialog
5. Reopen dialog
6. Verify no new roles were assigned

**Expected Results:**
- Cancel/close doesn't save changes
- Original roles preserved
- No partial state

### Test 8: Role Assignment Error Handling

**Steps:**
1. Open role dialog for a user
2. Simulate network error or permission failure
3. Attempt to assign a role
4. **Screenshot:** Error state
5. Verify error message displayed
6. Verify can retry or close dialog
7. Verify user roles unchanged on error

**Expected Results:**
- Error message shown on failure
- Roles not changed on error
- Recovery possible

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/user-roles/users/{userId}/roles` | Get user's current roles |
| GET | `/roles?limit=50&offset=0` | Get all available roles |
| POST | `/user-roles/assign` | Assign role to user |

## Request/Response Format

**Assign Role Request:**
```json
{
  "user_id": "user-uuid",
  "role_id": "role-uuid"
}
```

**Assign Role Response:**
```json
{
  "message": "Role assigned successfully",
  "user_id": "user-uuid",
  "role_id": "role-uuid"
}
```

**Get User Roles Response:**
```json
{
  "roles": [
    {
      "id": "role-uuid",
      "name": "Admin",
      "description": "Administrator role"
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Manage roles option | `getByRole('menuitem', { name: /roles|manage roles/i })` |
| Role dialog | Dialog component |
| Current roles list | Container showing assigned roles |
| Role badge (remove) | Badge with X button for each role |
| Role selector | Select component for available roles |
| Add button | `getByRole('button', { name: /add/i })` |
| Close/Cancel button | `getByRole('button', { name: /close|cancel|done/i })` |

## Success Criteria

- Role dialog shows current and available roles
- Roles can be assigned via selection
- Multiple roles can be assigned to same user
- Assignment reflected immediately
- Self-role assignment properly restricted
- Loading states and error handling work
- Changes persist after dialog close

## Notes

- Verify permission grants take effect immediately
- Test with users having various existing roles
- Check role hierarchy enforcement
- Verify audit logging for role changes
- Test with system-defined vs custom roles
- Verify i18n for role names and messages
