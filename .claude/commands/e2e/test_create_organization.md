# E2E Test: Create Organization

## Test Description
Validate that super admins can create new organizations with all required and optional fields.

## User Story
As a super admin
I want to create new organizations
So that I can onboard new tenants to the platform

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Create Organization Dialog

**Steps:**
1. Navigate to `/platform-admin/organizations`
2. Wait for page to load
3. Click "Create Organization" button
4. **Screenshot:** Create dialog open
5. Verify dialog appears with title "Create Organization"
6. Verify form has tabs:
   - Basic Info tab
   - Details tab
7. Verify required fields visible

**Expected Results:**
- Dialog opens on button click
- Tabbed interface displayed
- Form fields empty

### Test 2: Create with Required Fields Only

**Steps:**
1. Open create organization dialog
2. Enter name: "New Test Organization"
3. Enter slug: "new-test-org"
4. Leave is_active checked (default)
5. **Screenshot:** Basic info filled
6. Click "Create" button
7. Wait for API response
8. **Screenshot:** Success state
9. Verify success notification
10. Verify organization appears in list

**Expected Results:**
- Org created with minimal fields
- Success notification shown
- Dialog closes
- New org in list

### Test 3: Create with All Fields

**Steps:**
1. Open create organization dialog
2. Fill Basic Info tab:
   - Name: "Full Test Organization"
   - Slug: "full-test-org"
   - Active: checked
3. Switch to Details tab
4. Fill Details fields:
   - Display name: "Full Test Organization Inc."
   - Address line 1: "123 Main St"
   - Address line 2: "Suite 100"
   - City: "New York"
   - State: "NY"
   - Postal code: "10001"
   - Country: "USA"
   - Contact email: "contact@fulltest.com"
   - Contact phone: "+1-555-0123"
5. **Screenshot:** All fields filled
6. Click "Create" button
7. Verify success notification
8. View new org to verify all fields saved

**Expected Results:**
- All fields can be filled
- All data saved correctly
- Details accessible after creation

### Test 4: Validation - Empty Required Fields

**Steps:**
1. Open create organization dialog
2. Leave name empty
3. Leave slug empty
4. Click "Create" button
5. **Screenshot:** Validation errors
6. Verify error: "Name is required"
7. Verify error: slug required
8. Verify form not submitted

**Expected Results:**
- Validation errors shown
- Both required fields flagged
- Form prevented from submitting

### Test 5: Validation - Invalid Slug Format

**Steps:**
1. Open create organization dialog
2. Enter name: "Test Org"
3. Enter invalid slug: "Test Org Spaces"
4. Click "Create" button
5. **Screenshot:** Slug validation error
6. Verify error about slug format
7. Enter valid slug: "test-org-valid"
8. Verify can now submit

**Expected Results:**
- Slug format validated
- Only lowercase, alphanumeric, hyphens
- Error message explains format

### Test 6: Validation - Duplicate Slug

**Steps:**
1. Note an existing organization's slug
2. Open create organization dialog
3. Enter unique name
4. Enter duplicate slug
5. Click "Create" button
6. **Screenshot:** Duplicate slug error
7. Verify error about slug already taken
8. Enter unique slug
9. Verify can now create

**Expected Results:**
- Duplicate slug rejected
- Clear error message
- Can correct and retry

### Test 7: Cancel Create Dialog

**Steps:**
1. Open create organization dialog
2. Fill in some fields
3. **Screenshot:** Partially filled form
4. Click "Cancel" button
5. Verify dialog closes
6. Verify no organization created
7. Reopen dialog
8. Verify form is empty (reset)

**Expected Results:**
- Cancel closes dialog
- No data saved
- Form resets on reopen

### Test 8: Close Dialog via X Button

**Steps:**
1. Open create organization dialog
2. Fill in some data
3. Click X button in dialog header
4. Verify dialog closes
5. Verify no organization created

**Expected Results:**
- X button closes dialog
- Same behavior as Cancel

### Test 9: Loading State During Create

**Steps:**
1. Open create organization dialog
2. Fill required fields
3. Click "Create" button
4. **Screenshot:** Loading state
5. Verify button shows loading indicator
6. Verify button disabled
7. Verify form inputs disabled
8. Wait for completion

**Expected Results:**
- Loading indicator shown
- Prevents double submission
- Form disabled during save

### Test 10: Create Organization with Inactive Status

**Steps:**
1. Open create organization dialog
2. Enter name and slug
3. Uncheck "Active" checkbox
4. **Screenshot:** Inactive organization settings
5. Click "Create" button
6. Verify organization created
7. Find org in list
8. Verify status shows "Inactive"

**Expected Results:**
- Can create inactive organization
- Status correctly saved
- Badge shows Inactive

### Test 11: Keyboard Navigation

**Steps:**
1. Open create organization dialog
2. Verify focus on first input
3. Use Tab to navigate between fields
4. Use Tab to switch between tabs
5. **Screenshot:** Focus on submit button
6. Press Enter to submit (or Tab + Enter)
7. Verify form submitted

**Expected Results:**
- Tab navigation works
- Focus trap within dialog
- Can submit via keyboard

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/organizations` | Create new organization |

## Request/Response Format

**Create Organization Request:**
```json
{
  "name": "Full Test Organization",
  "slug": "full-test-org",
  "is_active": true,
  "display_name": "Full Test Organization Inc.",
  "physical_address_line1": "123 Main St",
  "physical_address_line2": "Suite 100",
  "city": "New York",
  "state_province": "NY",
  "postal_code": "10001",
  "country": "USA",
  "contact_email": "contact@fulltest.com",
  "contact_phone": "+1-555-0123"
}
```

**Create Organization Response (Success):**
```json
{
  "id": "new-org-uuid",
  "name": "Full Test Organization",
  "slug": "full-test-org",
  "is_active": true,
  "created_time": "2024-01-21T10:00:00Z",
  "updated_time": "2024-01-21T10:00:00Z",
  "deletion_requested": false,
  "deletion_requested_time": null
}
```

**Create Organization Response (Error - Duplicate Slug):**
```json
{
  "detail": "Organization with this slug already exists"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create organization/i })` |
| Create dialog | Dialog component |
| Dialog title | `getByRole('heading', { name: /create organization/i })` |
| Basic Info tab | `getByRole('tab', { name: /basic/i })` |
| Details tab | `getByRole('tab', { name: /details/i })` |
| Name input | `getByLabelText(/name/i)` |
| Slug input | `getByLabelText(/slug/i)` |
| Active checkbox | `getByLabelText(/active/i)` or Switch component |
| Display name input | `getByLabelText(/display name/i)` |
| Address inputs | Various by label |
| Contact email | `getByLabelText(/contact.*email/i)` |
| Contact phone | `getByLabelText(/contact.*phone/i)` |
| Create button (submit) | `getByRole('button', { name: /create/i })` within dialog |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Validation errors | FormMessage components |
| Loading indicator | Spinner within submit button |

## Success Criteria

- Create dialog opens with tabbed interface
- Organization can be created with required fields
- All optional fields can be populated
- Validation prevents invalid/empty required fields
- Slug format validated (lowercase, alphanumeric, hyphens)
- Duplicate slug rejected
- Cancel/X closes without saving
- Loading state prevents double submission
- New organization appears in list

## Notes

- Verify slug is auto-generated from name (if feature exists)
- Test with maximum length field values
- Verify newly created org can have users added
- Check SSO/2FA defaults for new organizations
- Verify audit log records organization creation
- Verify i18n for form labels and errors
