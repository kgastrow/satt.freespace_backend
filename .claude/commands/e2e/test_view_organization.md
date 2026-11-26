# E2E Test: View Organization

## Test Description
Validate that organization admins and owners can view their organization details and settings.

## User Story
As an organization admin
I want to view my organization's details
So that I can see current settings and status

## Prerequisites
- Backend server running
- Frontend dev server running
- Organization admin user:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Organization Settings

**Steps:**
1. Log in as organization admin
2. Navigate to `/admin/organization`
3. Wait for page to load
4. **Screenshot:** Organization settings page
5. Verify page header shows organization name
6. Verify organization details are displayed

**Expected Results:**
- Page loads successfully
- Organization name displayed
- Settings section visible

### Test 2: View Basic Organization Info

**Steps:**
1. Navigate to `/admin/organization`
2. Wait for organization data to load
3. **Screenshot:** Basic info section
4. Verify displayed fields:
   - Organization name
   - Organization slug
   - Active status
   - Created date
5. Verify data matches current organization

**Expected Results:**
- All basic fields displayed
- Data is accurate
- Status badges show correctly

### Test 3: View Organization Details

**Steps:**
1. Navigate to organization settings
2. Locate OrganizationDetailsForm section
3. **Screenshot:** Details form
4. Verify additional fields if present:
   - Display name
   - Physical address (line 1, line 2)
   - City, State/Province
   - Postal code, Country
   - Contact email
   - Contact phone
5. Verify fields show current values

**Expected Results:**
- Details form displays all fields
- Current values shown
- Fields are editable for authorized users

### Test 4: View Deletion Status (Not Requested)

**Steps:**
1. Navigate to organization settings
2. Scroll to Danger Zone section
3. **Screenshot:** Danger zone - no deletion
4. Verify "Request Deletion" button visible
5. Verify no pending deletion notice

**Expected Results:**
- Request Deletion option available
- No deletion pending message
- Owner-only access indicated

### Test 5: View Deletion Status (Pending)

**Steps:**
1. Set up organization with pending deletion request
2. Navigate to organization settings
3. Scroll to Danger Zone section
4. **Screenshot:** Danger zone - deletion pending
5. Verify deletion pending notice with:
   - Deletion request date
   - Retention period notice
   - Cancel deletion button

**Expected Results:**
- Pending deletion clearly indicated
- Retention period shown
- Cancel option available

### Test 6: Loading State

**Steps:**
1. Navigate to organization settings
2. **Screenshot:** Loading state
3. Observe loading indicator
4. Wait for data to load
5. Verify loading transitions to content

**Expected Results:**
- Loading state shown during fetch
- Smooth transition to content
- No flash of empty data

### Test 7: Non-Owner Access Restrictions

**Steps:**
1. Log in as organization admin (not owner)
2. Navigate to `/admin/organization`
3. **Screenshot:** Admin view with restrictions
4. Verify "Request Deletion" button:
   - Hidden, OR
   - Disabled with tooltip
5. Verify edit restrictions where applicable

**Expected Results:**
- Non-owners cannot request deletion
- Clear indication of permission level
- Read access still granted

### Test 8: Super Admin Access

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find a specific organization
4. Click to view details (or select from dropdown)
5. **Screenshot:** Super admin org view
6. Verify full details visible
7. Verify additional admin actions available

**Expected Results:**
- Super admin can view any organization
- Full details accessible
- Admin actions visible

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organizations/{id}` | Get organization basic info |
| GET | `/organizations/{id}/details` | Get detailed organization info |

## Request/Response Format

**Get Organization Response:**
```json
{
  "id": "org-uuid",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "is_active": true,
  "created_time": "2024-01-15T10:30:00Z",
  "updated_time": "2024-01-20T14:00:00Z",
  "deletion_requested": false,
  "deletion_requested_time": null
}
```

**Get Organization Details Response:**
```json
{
  "id": "org-uuid",
  "name": "Acme Corp",
  "slug": "acme-corp",
  "display_name": "Acme Corporation",
  "physical_address_line1": "123 Main St",
  "physical_address_line2": "Suite 100",
  "city": "New York",
  "state_province": "NY",
  "postal_code": "10001",
  "country": "USA",
  "contact_email": "admin@acme.com",
  "contact_phone": "+1-555-0123",
  "logo_file_id": null
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading')` with org name |
| Org name | Text content or data-testid |
| Org slug | `getByText()` with slug value |
| Active status | Badge component showing Active/Inactive |
| Details form | OrganizationDetailsForm component |
| Address fields | Form input fields |
| Danger zone | Section with deletion options |
| Request deletion button | `getByRole('button', { name: /request deletion/i })` |
| Cancel deletion button | `getByRole('button', { name: /cancel deletion/i })` |
| Loading indicator | Skeleton or spinner component |

## Success Criteria

- Organization settings page loads for admins
- Basic organization info displayed correctly
- Detailed info shown in form
- Deletion status clearly indicated
- Loading states handled properly
- Permission-based access enforced
- Super admins can view all organizations

## Notes

- Verify i18n translations for all displayed text
- Test with organizations in various states
- Check responsive layout on mobile
- Verify audit log records organization view
- Test with organizations having missing optional fields
