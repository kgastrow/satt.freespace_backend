# E2E Test: List Organizations

## Test Description
Validate that super admins can view a paginated list of all organizations in the platform.

## User Story
As a super admin
I want to view all organizations in the system
So that I can monitor and manage them

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
- Multiple organizations exist in the system
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Organizations Page

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Wait for page to load
4. **Screenshot:** Organizations list page
5. Verify page header shows "Organizations"
6. Verify DataTable component is displayed
7. Verify "Create Organization" button visible

**Expected Results:**
- Page loads successfully
- Header shows correct title
- Table displayed with data
- Create button visible

### Test 2: View Organizations Table

**Steps:**
1. Navigate to `/platform-admin/organizations`
2. Wait for data to load
3. **Screenshot:** Organizations table with data
4. Verify table columns:
   - Name
   - Slug
   - Status (Active/Inactive)
   - SSO Allowed
   - 2FA Allowed
   - Created Date
   - Actions
5. Verify organizations are displayed

**Expected Results:**
- All columns present
- Organization data shown correctly
- Status badges displayed

### Test 3: Organization Status Badges

**Steps:**
1. Navigate to organizations list
2. Ensure organizations exist with various statuses
3. **Screenshot:** Status badges
4. Verify Active organizations show "Active" badge
5. Verify Inactive organizations show "Inactive" badge
6. Verify deletion pending shows appropriate indicator
7. Verify badge colors distinguish statuses

**Expected Results:**
- Active status: Green/positive badge
- Inactive status: Gray/neutral badge
- Deletion requested: Red/warning badge

### Test 4: SSO and 2FA Indicators

**Steps:**
1. Navigate to organizations list
2. Locate SSO Allowed column
3. Locate 2FA Allowed column
4. **Screenshot:** Security feature columns
5. Verify checkmark/icon for enabled
6. Verify X/empty for disabled
7. Hover over icons for tooltip (if present)

**Expected Results:**
- SSO status clearly shown
- 2FA status clearly shown
- Tooltips explain settings

### Test 5: Pagination

**Steps:**
1. Navigate to organizations list
2. Ensure more than 10 organizations exist
3. **Screenshot:** First page
4. Verify 10 items per page
5. Click "Next" button
6. **Screenshot:** Second page
7. Verify different organizations shown
8. Click "Previous" button
9. Verify returned to first page

**Expected Results:**
- 10 items per page default
- Pagination controls work
- Different data per page
- Navigation works both ways

### Test 6: Actions Dropdown

**Steps:**
1. Navigate to organizations list
2. Find an organization row
3. Click actions dropdown (three dots)
4. **Screenshot:** Actions dropdown expanded
5. Verify available options:
   - Edit
   - View Members
   - Soft Delete / Request Deletion
   - Hard Delete (if retention passed)
   - Cancel Deletion (if pending)
6. Close dropdown

**Expected Results:**
- Dropdown shows all actions
- Context-appropriate actions shown
- Dropdown closes properly

### Test 7: Loading State

**Steps:**
1. Navigate to organizations list
2. **Screenshot:** Loading state
3. Observe skeleton/spinner
4. Wait for data to load
5. Verify smooth transition to data

**Expected Results:**
- Loading indicator shown
- Smooth transition
- No empty flash

### Test 8: Empty State

**Steps:**
1. Set up scenario with no organizations
2. Navigate to organizations list
3. **Screenshot:** Empty state
4. Verify empty state message
5. Verify Create button still available

**Expected Results:**
- Empty state clearly shown
- Message indicates no organizations
- Can still create new

### Test 9: Regular Admin Cannot Access

**Steps:**
1. Log in as regular admin (not super admin)
2. Attempt to navigate to `/platform-admin/organizations`
3. **Screenshot:** Access denied or redirect
4. Verify redirect to allowed page
5. Verify error message if shown

**Expected Results:**
- Regular admins cannot access
- Redirect or access denied
- Super admin only feature

### Test 10: Table Sorting (If Implemented)

**Steps:**
1. Navigate to organizations list
2. Click on "Name" column header
3. **Screenshot:** Sorted by name
4. Verify alphabetical sorting
5. Click again to reverse
6. Verify reverse alphabetical
7. Try sorting other columns

**Expected Results:**
- Columns sortable (if implemented)
- Visual indicator of sort direction
- Data reorders correctly

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organizations?limit=10&offset=0` | Fetch paginated organizations |

## Request/Response Format

**List Organizations Response:**
```json
{
  "organizations": [
    {
      "id": "org-uuid-1",
      "name": "Acme Corp",
      "slug": "acme-corp",
      "is_active": true,
      "sso_allowed": true,
      "two_factor_allowed": false,
      "created_time": "2024-01-15T10:30:00Z",
      "deletion_requested": false,
      "deletion_requested_time": null
    },
    {
      "id": "org-uuid-2",
      "name": "Test Corp",
      "slug": "test-corp",
      "is_active": false,
      "sso_allowed": false,
      "two_factor_allowed": true,
      "created_time": "2024-01-10T08:00:00Z",
      "deletion_requested": true,
      "deletion_requested_time": "2024-01-20T12:00:00Z"
    }
  ],
  "total": 25
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading', { name: /organizations/i })` |
| Create button | `getByRole('button', { name: /create organization/i })` |
| Organizations table | DataTable component |
| Table rows | `getByRole('row')` within table body |
| Organization name | Text content in name column |
| Org slug | Text in slug column |
| Status badge | Badge component with Active/Inactive |
| SSO indicator | Icon/text in SSO column |
| 2FA indicator | Icon/text in 2FA column |
| Actions dropdown | DropdownMenu trigger |
| Edit option | `getByRole('menuitem', { name: /edit/i })` |
| View Members option | `getByRole('menuitem', { name: /members/i })` |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Pagination next | `getByRole('button', { name: /next/i })` |
| Pagination previous | `getByRole('button', { name: /previous/i })` |
| Loading skeleton | Skeleton component |
| Empty state | Empty state message |

## Success Criteria

- Organizations list accessible to super admins only
- Table displays all required columns
- Organization data shown correctly
- Status badges indicate active/inactive/pending deletion
- SSO and 2FA status visible
- Pagination works correctly
- Actions dropdown provides management options
- Loading state shown during fetch
- Empty state handled gracefully

## Notes

- Verify i18n translations for all text
- Check responsive behavior on mobile
- Test with organizations in various states
- Verify audit log records list access
- Test search/filter if implemented
- Platform admin layout should have distinct styling (red border)
