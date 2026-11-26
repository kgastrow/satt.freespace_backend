# E2E Test: Remove Role

## Test Description
Validate that organization admins can remove roles from users, revoking specific permissions.

## User Story
As an organization admin
I want to remove roles from users
So that I can revoke permissions when they are no longer needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with role management permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- At least one user with assigned roles exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Remove Role from User

**Steps:**
1. Navigate to `/admin/users`
2. Wait for user list to load
3. Find a user with at least one role assigned
4. Click actions dropdown for that user
5. Click "Manage Roles" option
6. Wait for role dialog to open
7. **Screenshot:** User with roles displayed
8. Find the role to remove in current roles list
9. Click "X" or remove button on that role badge
10. Wait for removal to complete
11. **Screenshot:** After role removal
12. Verify success notification
13. Verify role no longer in user's current roles

**Expected Results:**
- Remove button visible on role badges
- Role removed successfully
- Success notification displayed
- Role badge removed from list

### Test 2: Remove All Roles from User

**Steps:**
1. Find a user with multiple roles
2. Open role management dialog
3. **Screenshot:** Multiple roles assigned
4. Remove first role
5. Verify first role removed
6. Remove second role
7. Verify second role removed
8. Continue until all roles removed
9. **Screenshot:** User with no roles
10. Verify empty state or "No roles" message

**Expected Results:**
- All roles can be removed
- Empty state handled gracefully
- User has no role badges in list

### Test 3: Role Removal Confirmation (If Applicable)

**Steps:**
1. Open role dialog for user with roles
2. Click remove button on a role
3. **Screenshot:** Confirmation if shown
4. If confirmation dialog appears:
   - Verify role name shown in confirmation
   - Click Cancel to abort
   - Verify role still present
   - Click remove again and confirm
5. Verify role removed after confirmation

**Expected Results:**
- Confirmation may be required for removal
- Cancel preserves the role
- Confirm completes removal

### Test 4: Cannot Remove Role from Self (Permission Check)

**Steps:**
1. Navigate to `/admin/users`
2. Find current admin user in list
3. Open role dialog for self
4. **Screenshot:** Self role management
5. Attempt to remove an admin role from self
6. Verify operation fails or warns
7. Verify message about cannot remove own role

**Expected Results:**
- Cannot demote self by removing roles
- Appropriate warning or prevention
- Own permissions preserved

### Test 5: Role Removal Updates User Table

**Steps:**
1. Open role dialog for a user
2. Note roles shown in user list row
3. **Screenshot:** User row before removal
4. Remove a role in dialog
5. Close dialog
6. **Screenshot:** User row after removal
7. Verify removed role no longer shown in table
8. Verify other roles still displayed

**Expected Results:**
- User table reflects role changes
- Removed role disappears from badges
- Other roles unaffected

### Test 6: Verify Permission Revocation

**Steps:**
1. Find user with specific role (e.g., "Files Admin")
2. Log in as that user in another browser
3. Verify they can access files admin features
4. Return to admin browser
5. Remove the "Files Admin" role
6. In user's browser, refresh page
7. **Screenshot:** Access denied after role removal
8. Verify user can no longer access admin features

**Expected Results:**
- Permission revocation takes effect
- User loses access immediately
- Appropriate access denied message

### Test 7: Role Removal Loading State

**Steps:**
1. Open role dialog for a user
2. Click remove on a role
3. **Screenshot:** Loading state during removal
4. Verify remove button shows loading
5. Verify other remove buttons may be disabled
6. Wait for completion

**Expected Results:**
- Loading indicator during removal
- Prevents rapid multiple removals
- Completes cleanly

### Test 8: Role Removal Error Handling

**Steps:**
1. Open role dialog for a user
2. Simulate network error
3. Attempt to remove a role
4. **Screenshot:** Error state
5. Verify error message displayed
6. Verify role still present (not removed on error)
7. Restore network
8. Retry removal successfully

**Expected Results:**
- Error message on failure
- Role preserved on error
- Can retry after error

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/user-roles/users/{userId}/roles` | Get user's current roles |
| POST | `/user-roles/revoke` | Revoke role from user |

## Request/Response Format

**Revoke Role Request:**
```json
{
  "user_id": "user-uuid",
  "role_id": "role-uuid"
}
```

**Revoke Role Response:**
```json
{
  "message": "Role revoked successfully",
  "user_id": "user-uuid",
  "role_id": "role-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Manage roles option | `getByRole('menuitem', { name: /roles|manage roles/i })` |
| Role dialog | Dialog component |
| Current roles container | Container with role badges |
| Role badge | Badge component showing role name |
| Remove button (X) | Button within role badge |
| Confirmation dialog | ConfirmDialog if removal confirms |
| Empty state | Text showing "No roles" or empty container |

## Success Criteria

- Roles can be removed via X button on badges
- All roles can be removed (empty state works)
- Self role removal properly restricted
- User table updates after removal
- Permissions actually revoked
- Loading and error states work correctly
- Changes persist after dialog close

## Notes

- Verify audit log records role removal
- Test removing built-in vs custom roles
- Check cascade effects on related permissions
- Verify removal affects active user sessions
- Test with users having single role vs many
- Verify i18n for removal confirmations
