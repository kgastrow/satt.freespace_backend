# E2E Test: Permission Gate

## Test Description
Validate that the PermissionGate component correctly controls access to UI elements based on user permissions.

## User Story
As a user with specific permissions
I want to see only the features I have access to
So that the interface is relevant and secure

## Prerequisites
- Backend server running
- Frontend dev server running
- Multiple test users with different permission levels:
  - Super admin (is_admin: true): superadmin@example.com
  - User with users:read permission: reader@example.com
  - User with users:write permission: writer@example.com
  - User with no special permissions: basic@example.com
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Super Admin Sees All Protected Content

**Steps:**
1. Log in as super admin
2. Navigate to `/admin/users`
3. **Screenshot:** Admin page with all actions
4. Verify "Create User" button visible
5. Verify Edit actions visible
6. Verify Delete actions visible
7. Navigate to `/admin/roles`
8. Verify full access to roles management

**Expected Results:**
- Super admin bypasses all permission checks
- All protected content visible
- All actions available

### Test 2: Single Permission Check - Read Only

**Steps:**
1. Log in as user with only users:read permission
2. Navigate to `/admin/users`
3. **Screenshot:** Read-only view
4. Verify user list is visible (users:read)
5. Verify "Create User" button NOT visible or disabled
6. Verify Edit option NOT visible or disabled
7. Verify Delete option NOT visible or disabled

**Expected Results:**
- Read permission grants list view
- Write-protected actions hidden/disabled
- Delete-protected actions hidden/disabled

### Test 3: Single Permission Check - Write Access

**Steps:**
1. Log in as user with users:write permission
2. Navigate to `/admin/users`
3. **Screenshot:** Write access view
4. Verify "Create User" button IS visible
5. Verify Edit option IS visible
6. Click "Create User" button
7. Verify create dialog opens

**Expected Results:**
- Write permission enables create/edit
- Create button functional
- Edit actions available

### Test 4: Multiple Permissions - requireAll: true

**Steps:**
1. Set up user with only users:read (not users:write)
2. Log in as that user
3. Navigate to feature requiring BOTH read AND write
4. **Screenshot:** Access denied or partial
5. Verify content hidden when requireAll=true and missing permission
6. Log in as user with BOTH permissions
7. Verify content now visible

**Expected Results:**
- requireAll=true requires ALL permissions
- Missing any permission hides content
- Having all permissions shows content

### Test 5: Multiple Permissions - requireAll: false (ANY)

**Steps:**
1. Log in as user with users:read only
2. Navigate to area gated by [users:read, users:write] with requireAll=false
3. **Screenshot:** Access granted with partial permissions
4. Verify content visible (has at least one)
5. Log in as user with neither permission
6. Verify content hidden

**Expected Results:**
- Default ANY mode requires at least one permission
- Having any listed permission shows content
- Having none hides content

### Test 6: Permission Gate with Fallback Content

**Steps:**
1. Log in as user without specific permission
2. Navigate to page with gated content that has fallback
3. **Screenshot:** Fallback content shown
4. Verify fallback message or alternative UI displayed
5. Verify no error or blank space
6. Log in as permitted user
7. Verify actual content replaces fallback

**Expected Results:**
- Fallback content renders for unauthorized
- No empty space or errors
- Proper content for authorized users

### Test 7: Route-Level Permission Gate

**Steps:**
1. Log in as user without admin permissions
2. Attempt to navigate directly to `/admin/roles`
3. **Screenshot:** Redirect or access denied
4. Verify redirect to allowed page (e.g., home)
5. Verify appropriate message (if shown)
6. Log in as super admin
7. Navigate to `/admin/roles`
8. Verify access granted

**Expected Results:**
- Route-level protection redirects unauthorized
- No access to protected routes
- Proper access for authorized users

### Test 8: Permission Gate During Loading

**Steps:**
1. Clear auth state
2. Trigger page load that checks permissions
3. **Screenshot:** Loading state
4. Verify loading indicator while checking auth
5. Verify no flash of protected content
6. Wait for auth to resolve
7. Verify correct content shown based on permissions

**Expected Results:**
- Loading state during auth check
- No unauthorized content flash
- Correct final state

### Test 9: Permission Change After Login

**Steps:**
1. Log in as user with limited permissions
2. Note visible/hidden elements
3. Admin assigns additional permission to user (via API)
4. Refresh the page
5. **Screenshot:** Updated permissions
6. Verify newly permitted content now visible

**Expected Results:**
- Permission changes reflect on refresh
- New permissions grant access
- UI updates accordingly

### Test 10: Impersonation Mode Permissions

**Steps:**
1. Log in as super admin
2. Start impersonating a regular user
3. **Screenshot:** Impersonation with user permissions
4. Verify UI shows impersonated user's permissions
5. Verify super admin override NOT active during impersonation
6. Verify protected content hidden if user lacks permission
7. End impersonation
8. Verify super admin access restored

**Expected Results:**
- Impersonation shows target user's permissions
- Super admin bypass disabled during impersonation
- Ending impersonation restores admin access

### Test 11: usePermission Hook - canRead/canWrite/canDelete

**Steps:**
1. Log in as user with users:read, users:write (no delete)
2. Navigate to `/admin/users`
3. **Screenshot:** Partial permissions
4. Verify list visible (canRead: true)
5. Verify Create/Edit buttons visible (canWrite: true)
6. Verify Delete button/option hidden (canDelete: false)

**Expected Results:**
- usePermission hook correctly evaluates
- canRead enables list view
- canWrite enables create/edit
- canDelete enables delete (when granted)

### Test 12: hasPermission Function for Custom Codes

**Steps:**
1. Log in as user with custom permission (e.g., reports:generate)
2. Navigate to page using hasPermission('reports:generate')
3. **Screenshot:** Custom permission check
4. Verify content visible for custom permission
5. Log in as user without that permission
6. Verify content hidden

**Expected Results:**
- Custom permission codes work
- hasPermission function evaluates correctly
- Arbitrary permission strings supported

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/user/me` | Get current user with permissions |
| GET | `/user/me/permissions` | Get user's effective permissions |

## Request/Response Format

**User Permissions Response:**
```json
{
  "permissions": [
    "users:read",
    "users:write",
    "files:read",
    "files:write",
    "files:delete"
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Permission-gated content | Various based on feature |
| Create button (gated) | `getByRole('button', { name: /create/i })` |
| Edit option (gated) | `getByRole('menuitem', { name: /edit/i })` |
| Delete option (gated) | `getByRole('menuitem', { name: /delete/i })` |
| Fallback content | Text or component shown when not permitted |
| Loading state | Skeleton or spinner during auth check |
| Redirect target | Check current URL after redirect |

## Success Criteria

- Super admin bypasses all permission checks
- Single permission checks work correctly
- Multiple permission checks with requireAll work
- Multiple permission checks with ANY (default) work
- Fallback content renders for unauthorized
- Route-level protection redirects properly
- Loading states prevent content flash
- Impersonation uses target user's permissions
- usePermission hook evaluates correctly
- Custom permission codes supported

## Notes

- Test with permissions assigned via roles vs direct
- Verify permission caching behavior
- Check performance with many permission checks
- Verify console doesn't log permission errors
- Test nested PermissionGate components
- Verify i18n for fallback messages
- Check accessibility of hidden vs disabled states
