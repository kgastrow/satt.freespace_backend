# E2E Test: List Roles

## Test Description
Validate that super admins can view the roles list with pagination and see role details.

## User Story
As a super admin
I want to view all roles in the system
So that I can manage role-based access control

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
  - Organization: test-org
- At least one role exists in the system
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Roles Page

**Steps:**
1. Log in as super admin
2. Navigate to `/admin/roles`
3. Wait for page to load
4. **Screenshot:** Roles page initial view
5. Verify page header shows "Roles"
6. Verify DataTable component is displayed
7. Verify "Add Role" button is visible

**Expected Results:**
- Roles page loads successfully
- Page has appropriate header
- Table is displayed
- Create button visible for super admins

### Test 2: View Roles Table

**Steps:**
1. Navigate to `/admin/roles`
2. Wait for roles to load
3. **Screenshot:** Roles table with data
4. Verify table columns:
   - Name
   - Description
   - Created date
   - Actions
5. Verify at least one role is displayed
6. Verify role data is populated correctly

**Expected Results:**
- Table displays all required columns
- Role data is shown correctly
- Each row has action dropdown

### Test 3: Roles Table Loading State

**Steps:**
1. Navigate to `/admin/roles`
2. **Screenshot:** Loading state (skeleton)
3. Observe loading indicator
4. Wait for data to load
5. Verify loading state transitions to data

**Expected Results:**
- Loading skeleton shown during fetch
- Smooth transition to data
- No flash of empty content

### Test 4: Pagination

**Steps:**
1. Navigate to `/admin/roles`
2. Ensure more than 10 roles exist
3. **Screenshot:** First page of roles
4. Verify 10 roles per page (default)
5. Click "Next" pagination button
6. **Screenshot:** Second page of roles
7. Verify different roles shown
8. Click "Previous" pagination button
9. Verify returned to first page

**Expected Results:**
- 10 items per page
- Pagination controls work
- Page changes show different data
- Can navigate back and forth

### Test 5: Empty State

**Steps:**
1. Set up scenario with no roles
2. Navigate to `/admin/roles`
3. **Screenshot:** Empty state
4. Verify empty state message displayed
5. Verify "Add Role" button still visible

**Expected Results:**
- Empty state clearly shown
- Message indicates no roles
- Create option still available

### Test 6: Actions Dropdown

**Steps:**
1. Navigate to `/admin/roles`
2. Find a role in the list
3. Click actions dropdown (three dots button)
4. **Screenshot:** Actions dropdown expanded
5. Verify options shown:
   - Edit
   - Delete
6. Close dropdown by clicking outside

**Expected Results:**
- Dropdown opens on click
- Edit option visible
- Delete option visible
- Dropdown closes properly

### Test 7: Non-Super Admin Access Restriction

**Steps:**
1. Log in as regular admin (not super admin)
2. Attempt to navigate to `/admin/roles`
3. **Screenshot:** Access denied or redirect
4. Verify user cannot access roles page
5. Verify redirect or error message shown

**Expected Results:**
- Regular admins cannot access roles page
- Appropriate restriction message
- Redirect to allowed page

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/roles?limit=10&offset=0` | Fetch paginated roles |

## Request/Response Format

**List Roles Response:**
```json
{
  "items": [
    {
      "id": "role-uuid",
      "name": "Admin",
      "description": "Administrator role with full access",
      "created_time": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 25,
  "limit": 10,
  "offset": 0
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading', { name: /roles/i })` |
| Add Role button | `getByRole('button', { name: /add role/i })` |
| Roles table | DataTable component |
| Table rows | `getByRole('row')` within table body |
| Actions dropdown trigger | DropdownMenu trigger in role row |
| Edit option | `getByRole('menuitem', { name: /edit/i })` |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Pagination next | `getByRole('button', { name: /next/i })` |
| Pagination previous | `getByRole('button', { name: /previous/i })` |
| Loading skeleton | Skeleton component in table |

## Success Criteria

- Roles page accessible to super admins only
- Table displays role data correctly
- Pagination works with 10 items per page
- Loading state shown during fetch
- Empty state handled gracefully
- Actions dropdown shows edit/delete options
- Regular admins cannot access page

## Notes

- Roles are system-wide (not organization-scoped in frontend view)
- Only super admins (is_admin: true) can manage roles
- Verify i18n translations for page title and table headers
- Check responsive behavior on mobile
- Verify audit log records role list access
