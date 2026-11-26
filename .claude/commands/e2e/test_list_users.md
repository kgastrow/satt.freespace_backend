# E2E Test: List Users

## Test Description
Validate that organization admins can view a paginated list of users within their organization with search functionality.

## User Story
As an organization admin
I want to view all users in my organization
So that I can manage and monitor user accounts

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with `users:read` permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- Multiple test users exist in the organization
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View User List Page

**Steps:**
1. Navigate to `/admin/users`
2. Wait for page to load
3. **Screenshot:** Users list page
4. Verify page title "Manage Users" or "Users" displayed
5. Verify DataTable component is rendered
6. Verify users are displayed in table rows

**Expected Results:**
- Users page loads without errors
- Table displays user data
- No loading spinners stuck on screen

### Test 2: Verify User Table Columns

**Steps:**
1. Navigate to `/admin/users`
2. Wait for data to load
3. **Screenshot:** Table header columns
4. Verify table has columns:
   - Name (first + last name)
   - Email
   - Status (Active/Suspended)
   - Roles
   - Actions dropdown
5. Verify column headers are translated

**Expected Results:**
- All expected columns present
- Column headers correctly labeled
- Data aligned properly in columns

### Test 3: Pagination Functionality

**Steps:**
1. Navigate to `/admin/users` (with >10 users in org)
2. Wait for first page to load
3. **Screenshot:** First page with pagination
4. Verify pagination controls visible
5. Verify showing "1-10 of X" or similar indicator
6. Click "Next" page button
7. Wait for page 2 to load
8. **Screenshot:** Second page
9. Verify different users displayed
10. Click "Previous" page button
11. Verify returns to first page

**Expected Results:**
- Pagination shows total count
- Navigation between pages works
- Page size is 10 users per page
- Current page indicator accurate

### Test 4: User Status Display

**Steps:**
1. Navigate to `/admin/users`
2. Find a user with "Active" status
3. **Screenshot:** Active status badge
4. Find a user with "Suspended" status (if exists)
5. **Screenshot:** Suspended status badge
6. Verify status badges are color-coded:
   - Active: Green or default
   - Suspended: Red or warning

**Expected Results:**
- Status clearly indicated per user
- Color coding distinguishes statuses
- Badge styling consistent

### Test 5: User Roles Display

**Steps:**
1. Navigate to `/admin/users`
2. Find a user with assigned roles
3. **Screenshot:** Roles column
4. Verify roles displayed as badges
5. Verify multiple roles shown if user has several

**Expected Results:**
- Roles displayed as badge components
- Multiple roles visible per user
- Role names truncated appropriately if too long

### Test 6: Actions Dropdown Menu

**Steps:**
1. Navigate to `/admin/users`
2. Locate actions dropdown for a user row
3. Click actions dropdown trigger (three dots or "Actions")
4. **Screenshot:** Actions dropdown expanded
5. Verify dropdown contains:
   - Edit user option
   - Manage roles option
   - Suspend/Unsuspend option
   - Delete option
   - Impersonate option (if super admin)
6. Click outside dropdown to close

**Expected Results:**
- Dropdown opens on click
- All expected actions present
- Actions respect user permissions
- Dropdown closes on outside click

### Test 7: Empty State

**Steps:**
1. Navigate to `/admin/users` (with empty organization or filtered)
2. **Screenshot:** Empty state
3. Verify empty state message displayed
4. Verify "No users found" or similar message
5. Verify create user option may be shown

**Expected Results:**
- Graceful empty state handling
- Clear message when no users
- Option to add users if permitted

### Test 8: Permission-Based Access

**Steps:**
1. Log in as user WITHOUT `users:read` permission
2. Navigate to `/admin/users`
3. **Screenshot:** Access denied or redirect
4. Verify access is denied or page not accessible
5. Log in as user WITH `users:read` permission
6. Navigate to `/admin/users`
7. Verify page loads successfully

**Expected Results:**
- Unauthorized users cannot access page
- Permission gate enforces access
- Appropriate error or redirect for unauthorized

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/users?limit=10&offset=0` | List users with pagination |

## Request/Response Format

**List Users Response:**
```json
{
  "users": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "first_name": "Test",
      "last_name": "User",
      "phone": "+1234567890",
      "is_active": true,
      "suspension_status": null,
      "roles": [
        {"id": "role-uuid", "name": "Admin"}
      ],
      "created_time": "2024-01-01T00:00:00Z"
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
| Users table | DataTable component |
| Table rows | `tr` within table body |
| User name cell | Cell containing user full name |
| Email cell | Cell containing email |
| Status badge | Badge component in status column |
| Role badges | Badge components in roles column |
| Actions dropdown | DropdownMenu trigger button |
| Pagination | Pagination component |
| Page indicator | Text showing "Page X of Y" |
| Next button | `getByRole('button', { name: /next/i })` |
| Previous button | `getByRole('button', { name: /previous/i })` |

## Success Criteria

- User list loads and displays correctly
- All table columns show appropriate data
- Pagination works for navigating users
- Status badges clearly indicate user status
- Roles are visible per user
- Actions dropdown accessible per row
- Permission-based access enforced

## Notes

- Test with various numbers of users (1, 10, 50, 100+)
- Verify performance with large user counts
- Check responsive layout on mobile
- Verify i18n translations for column headers
- Test sorting if implemented
- Verify search/filter integration
