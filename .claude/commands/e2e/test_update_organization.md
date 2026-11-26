# E2E Test: Update Organization

## Test Description
Validate that organization owners and super admins can update organization details including name, description, and contact information.

## User Story
As an organization owner
I want to update my organization's details
So that the information stays accurate and current

## Prerequisites
- Backend server running
- Frontend dev server running
- Organization owner user:
  - Email: owner@example.com
  - Password: OwnerPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Edit Organization Basic Info

**Steps:**
1. Navigate to `/admin/organization`
2. Wait for organization data to load
3. Locate edit form or edit button
4. Change organization display name
5. **Screenshot:** Form with changes
6. Click Save button
7. Wait for API response
8. **Screenshot:** After save
9. Verify success notification
10. Verify changes displayed

**Expected Results:**
- Form allows editing
- Save completes successfully
- Success notification shown
- Changes reflected in UI

### Test 2: Update Contact Information

**Steps:**
1. Navigate to organization settings
2. Locate contact info fields in OrganizationDetailsForm
3. Update contact email: "new-contact@acme.com"
4. Update contact phone: "+1-555-9999"
5. **Screenshot:** Updated contact fields
6. Click Save button
7. Verify success notification
8. Refresh page
9. Verify changes persisted

**Expected Results:**
- Contact fields editable
- Valid email format required
- Phone number accepted
- Changes persist after refresh

### Test 3: Update Address Information

**Steps:**
1. Navigate to organization settings
2. Locate address fields in details form
3. Update fields:
   - Address line 1: "456 New Street"
   - Address line 2: "Floor 2"
   - City: "Los Angeles"
   - State: "CA"
   - Postal code: "90001"
   - Country: "USA"
4. **Screenshot:** Updated address
5. Click Save button
6. Verify success notification
7. Verify address updated in UI

**Expected Results:**
- All address fields editable
- Changes saved successfully
- No validation errors for valid data

### Test 4: Validation - Invalid Email

**Steps:**
1. Navigate to organization settings
2. Enter invalid contact email: "not-an-email"
3. Click Save button
4. **Screenshot:** Email validation error
5. Verify validation error displayed
6. Verify form not submitted
7. Enter valid email
8. Verify can now save

**Expected Results:**
- Email format validated
- Error message shown
- Form prevented from submitting
- Can correct and retry

### Test 5: Clear Optional Fields

**Steps:**
1. Navigate to organization settings with populated details
2. Clear address line 2 (optional field)
3. Clear display name (optional field)
4. **Screenshot:** Cleared optional fields
5. Click Save button
6. Verify save succeeds
7. Verify fields stored as empty/null

**Expected Results:**
- Optional fields can be cleared
- Save succeeds with empty optionals
- Fields convert to null on API

### Test 6: Loading State During Save

**Steps:**
1. Navigate to organization settings
2. Make changes to form
3. Click Save button
4. **Screenshot:** Loading state
5. Verify Save button shows loading indicator
6. Verify form inputs disabled during save
7. Wait for completion

**Expected Results:**
- Loading indicator on button
- Prevents double submission
- Form disabled during save

### Test 7: Save Error Handling

**Steps:**
1. Navigate to organization settings
2. Make changes
3. Simulate network error
4. Click Save button
5. **Screenshot:** Error state
6. Verify error notification displayed
7. Verify changes preserved in form
8. Restore network
9. Retry save successfully

**Expected Results:**
- Error message shown
- Changes not lost on error
- Can retry save

### Test 8: Cancel/Revert Changes

**Steps:**
1. Navigate to organization settings
2. Note original values
3. Make changes to multiple fields
4. **Screenshot:** Form with changes
5. Click Cancel or navigate away
6. Return to organization settings
7. Verify original values restored

**Expected Results:**
- Unsaved changes not persisted
- Original values remain
- Navigation doesn't save automatically

### Test 9: Super Admin Edit Any Organization

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find a target organization
4. Click Edit or actions dropdown
5. **Screenshot:** Super admin edit dialog
6. Modify organization name
7. Toggle is_active status
8. Click Save button
9. Verify changes saved

**Expected Results:**
- Super admin can edit any org
- Can toggle active status
- All fields accessible
- Changes persist

### Test 10: Edit Organization in Dialog (Super Admin)

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Click actions dropdown for an organization
4. Click "Edit" option
5. **Screenshot:** Edit dialog open
6. Verify dialog shows tabs:
   - Basic Info tab
   - Details tab
7. Make changes in both tabs
8. Click Save button
9. Verify all changes saved

**Expected Results:**
- Dialog has tabbed interface
- Both tabs functional
- All changes saved together
- Dialog closes on success

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| PUT | `/organizations/{id}` | Update basic organization info |
| PATCH | `/organizations/{id}/details` | Update detailed organization info |

## Request/Response Format

**Update Organization Request:**
```json
{
  "name": "Updated Org Name",
  "is_active": true
}
```

**Update Organization Details Request:**
```json
{
  "display_name": "Updated Display Name",
  "physical_address_line1": "456 New Street",
  "physical_address_line2": "Floor 2",
  "city": "Los Angeles",
  "state_province": "CA",
  "postal_code": "90001",
  "country": "USA",
  "contact_email": "new-contact@acme.com",
  "contact_phone": "+1-555-9999"
}
```

**Update Response (Success):**
```json
{
  "id": "org-uuid",
  "name": "Updated Org Name",
  "slug": "updated-org-name",
  "is_active": true,
  "updated_time": "2024-01-21T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Details form | OrganizationDetailsForm component |
| Display name input | `getByLabelText(/display name/i)` |
| Address line 1 | `getByLabelText(/address.*1/i)` |
| Address line 2 | `getByLabelText(/address.*2/i)` |
| City input | `getByLabelText(/city/i)` |
| State input | `getByLabelText(/state|province/i)` |
| Postal code input | `getByLabelText(/postal|zip/i)` |
| Country input | `getByLabelText(/country/i)` |
| Contact email | `getByLabelText(/contact.*email/i)` |
| Contact phone | `getByLabelText(/contact.*phone/i)` |
| Save button | `getByRole('button', { name: /save/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Edit dialog (super admin) | Dialog component |
| Basic Info tab | `getByRole('tab', { name: /basic/i })` |
| Details tab | `getByRole('tab', { name: /details/i })` |
| Validation error | FormMessage component |

## Success Criteria

- Organization details can be updated
- All form fields work correctly
- Validation prevents invalid data
- Optional fields can be cleared
- Loading state during save
- Errors handled gracefully
- Changes persist after refresh
- Super admins can edit any organization
- Tabbed edit dialog works (super admin)

## Notes

- Verify audit log records updates
- Test with max length field values
- Check slug uniqueness if slug can be edited
- Verify i18n for form labels and errors
- Test with organizations in deletion pending state
- Verify logo upload if implemented
