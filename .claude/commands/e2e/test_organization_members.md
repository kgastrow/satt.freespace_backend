# E2E Test: Organization Members

## Test Description
Validate that super admins can view and manage organization members.

## User Story
As a super admin
I want to view and manage organization members
So that I can monitor user access and remove members when needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
- Organization with multiple members exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Organization Members Page

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find an organization with members
4. Click actions dropdown
5. Click "View Members" option
6. **Screenshot:** Organization members page
7. Verify page loads at `/platform-admin/organizations/{id}/members`
8. Verify breadcrumb navigation shows organization name

**Expected Results:**
- Members page loads successfully
- Breadcrumb shows navigation path
- Organization name displayed

### Test 2: View Members List

**Steps:**
1. Navigate to organization members page
2. Wait for members to load
3. **Screenshot:** Members table
4. Verify table columns:
   - Email
   - Roles (if applicable)
   - Joined Date
   - Actions
5. Verify members are displayed with data

**Expected Results:**
- All columns present
- Member data shown correctly
- Each row has member info

### Test 3: Member Admin Badge

**Steps:**
1. Navigate to organization members page
2. Find a member who is an admin
3. **Screenshot:** Admin member row
4. Verify admin badge or indicator shown
5. Find a non-admin member
6. Verify no admin badge

**Expected Results:**
- Admin members clearly identified
- Badge distinguishes admin from regular user
- Visual indicator is clear

### Test 4: Pagination

**Steps:**
1. Navigate to organization with many members
2. **Screenshot:** First page of members
3. Verify pagination controls
4. Click "Next" button
5. **Screenshot:** Second page
6. Verify different members shown
7. Click "Previous" button
8. Verify returned to first page

**Expected Results:**
- Pagination works correctly
- Different members per page
- Navigation works both ways

### Test 5: Remove Member

**Steps:**
1. Navigate to organization members page
2. Find a member to remove
3. Click actions dropdown for that member
4. **Screenshot:** Remove option
5. Click "Remove" option
6. Verify confirmation dialog
7. **Screenshot:** Remove confirmation
8. Click "Confirm"
9. Wait for API response
10. **Screenshot:** After removal
11. Verify success notification
12. Verify member removed from list

**Expected Results:**
- Remove option available
- Confirmation required
- Member removed successfully
- List updates automatically

### Test 6: Cancel Remove Member

**Steps:**
1. Navigate to organization members page
2. Open remove dialog for a member
3. **Screenshot:** Confirmation dialog
4. Click "Cancel" button
5. Verify dialog closes
6. Verify member still in list

**Expected Results:**
- Cancel closes dialog
- No removal occurs
- Member preserved

### Test 7: Cannot Remove Last Admin

**Steps:**
1. Navigate to organization with only one admin member
2. Find the admin member
3. Attempt to remove (if option available)
4. **Screenshot:** Removal attempt
5. Verify operation blocked or warned
6. Verify message about last admin restriction

**Expected Results:**
- Cannot remove sole admin
- Clear error/warning message
- Organization must have at least one admin

### Test 8: Loading State

**Steps:**
1. Navigate to organization members page
2. **Screenshot:** Loading state
3. Observe loading indicator
4. Wait for data to load
5. Verify smooth transition to content

**Expected Results:**
- Loading indicator shown
- Smooth transition to data
- No empty flash

### Test 9: Empty Members State

**Steps:**
1. Navigate to organization with no members (if possible)
2. **Screenshot:** Empty state
3. Verify empty state message
4. Verify appropriate guidance shown

**Expected Results:**
- Empty state handled gracefully
- Clear message shown
- No broken UI

### Test 10: Breadcrumb Navigation

**Steps:**
1. Navigate to organization members page
2. **Screenshot:** Breadcrumb trail
3. Verify breadcrumb shows:
   - Platform Admin / Organizations
   - Organization Name
   - Members
4. Click on "Organizations" in breadcrumb
5. Verify navigation back to organizations list

**Expected Results:**
- Breadcrumb trail visible
- Click navigation works
- Context preserved

### Test 11: Member Count Display

**Steps:**
1. Navigate to organization members page
2. Note the displayed member count
3. **Screenshot:** Member count
4. Verify count matches actual members
5. Remove a member
6. Verify count updates

**Expected Results:**
- Member count displayed
- Count is accurate
- Updates on changes

### Test 12: View Member Details (If Available)

**Steps:**
1. Navigate to organization members page
2. Click on a member row or view action
3. **Screenshot:** Member details
4. Verify member information displayed:
   - Email
   - Admin status
   - Joined date
   - Any additional details

**Expected Results:**
- Member details viewable
- All relevant info shown
- Clear presentation

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organizations/{id}/members?limit=10&offset=0` | List organization members |
| GET | `/organizations/{id}/members/count` | Get member count |
| DELETE | `/organizations/{id}/members/{userId}` | Remove member from organization |

## Request/Response Format

**List Members Response:**
```json
{
  "members": [
    {
      "id": "user-uuid-1",
      "email": "user1@acme.com",
      "is_admin": true,
      "created_time": "2024-01-15T10:30:00Z"
    },
    {
      "id": "user-uuid-2",
      "email": "user2@acme.com",
      "is_admin": false,
      "created_time": "2024-01-16T14:00:00Z"
    }
  ],
  "total": 2
}
```

**Remove Member Response:**
```json
{
  "message": "Member removed successfully"
}
```

**Remove Member Error (Last Admin):**
```json
{
  "detail": "Cannot remove the last admin from the organization"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading')` with members title |
| Breadcrumb | Breadcrumb component |
| Breadcrumb org link | `getByRole('link', { name: /organizations/i })` |
| Members table | DataTable component |
| Table rows | `getByRole('row')` within table body |
| Member email | Text in email column |
| Admin badge | Badge component showing admin status |
| Joined date | Date in joined column |
| Actions dropdown | DropdownMenu trigger |
| Remove option | `getByRole('menuitem', { name: /remove/i })` |
| Confirmation dialog | ConfirmDialog component |
| Confirm button | `getByRole('button', { name: /confirm|remove/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Pagination | Pagination component |
| Member count | Text showing total members |
| Loading skeleton | Skeleton component |
| Empty state | Empty state message |

## Success Criteria

- Members page accessible via organizations list
- All organization members displayed
- Admin members clearly identified
- Pagination works correctly
- Members can be removed with confirmation
- Cannot remove last admin
- Breadcrumb navigation works
- Member count displays and updates
- Loading states handled properly
- Empty state handled gracefully

## Notes

- Verify audit log records member removals
- Test with organizations having many members
- Check if roles are displayed for members
- Verify removed member loses org access immediately
- Test notification to removed member (if implemented)
- Verify i18n for all text
- Check responsive layout on mobile
