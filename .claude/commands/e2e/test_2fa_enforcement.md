# E2E Test: 2FA Enforcement

## Test Description
Validate that administrators can configure organization-wide two-factor authentication policies.

## User Story
As an organization administrator
I want to enforce 2FA policies for my organization
So that I can improve account security for all users

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with two_factor:write permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- 2FA settings must be allowed by super admin
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to 2FA Settings Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/two-factor`
3. **Screenshot:** 2FA settings page
4. Verify page loads correctly
5. Verify policy options visible

**Expected Results:**
- Page loads successfully
- Policy selection visible
- Current policy highlighted

### Test 2: View Policy Options

**Steps:**
1. Navigate to 2FA settings page
2. **Screenshot:** Policy options
3. Verify three policy options shown:
   - Disabled
   - Optional
   - Mandatory
4. Verify current policy selected

**Expected Results:**
- All policies visible
- Current selection highlighted
- Descriptions shown for each

### Test 3: Set Policy to Disabled

**Steps:**
1. Select "Disabled" policy option
2. **Screenshot:** Disabled selected
3. Click "Save" button
4. Verify success notification
5. Verify policy persists on reload

**Expected Results:**
- Disabled option selectable
- Settings saved
- 2FA optional for all users

### Test 4: Set Policy to Optional

**Steps:**
1. Select "Optional" policy option
2. **Screenshot:** Optional selected
3. Click "Save" button
4. Verify success notification
5. Verify users can choose to enable 2FA

**Expected Results:**
- Optional policy saved
- Users have choice
- No enforcement

### Test 5: Set Policy to Mandatory

**Steps:**
1. Select "Mandatory" policy option
2. **Screenshot:** Mandatory selected
3. Verify grace period field appears
4. Enter grace period: 7 days
5. **Screenshot:** Grace period configured
6. Click "Save" button
7. Verify settings saved

**Expected Results:**
- Mandatory option selectable
- Grace period field shown
- Settings saved with grace period

### Test 6: Configure Grace Period

**Steps:**
1. Select Mandatory policy
2. Set grace period to 1 day (minimum)
3. **Screenshot:** Minimum grace period
4. Save and verify
5. Set grace period to 30 days (maximum)
6. **Screenshot:** Maximum grace period
7. Save and verify

**Expected Results:**
- Grace period accepts 1-30 days
- Validation for out-of-range values
- Saved correctly

### Test 7: View Enforcement Start Date

**Steps:**
1. Configure mandatory policy
2. Save settings
3. **Screenshot:** Enforcement start date
4. Verify enforcement date displayed
5. Verify calculated from grace period

**Expected Results:**
- Start date shown
- Date calculated correctly
- Clear deadline message

### Test 8: View Users Without 2FA

**Steps:**
1. Set mandatory policy
2. **Screenshot:** Users without 2FA list
3. Verify list of non-compliant users shown
4. Verify shows user name and email
5. Verify pagination if many users

**Expected Results:**
- Non-compliant users listed
- User info displayed
- Can see who needs to enable 2FA

### Test 9: 2FA Not Allowed by Platform

**Steps:**
1. Set up org where 2FA settings are not allowed
2. Navigate to `/admin/two-factor`
3. **Screenshot:** 2FA not allowed
4. Verify warning/error shown
5. Verify cannot modify settings

**Expected Results:**
- Warning about platform restriction
- Settings read-only or hidden
- Contact admin message

### Test 10: Validation - Invalid Grace Period

**Steps:**
1. Select Mandatory policy
2. Enter grace period: 0 days
3. **Screenshot:** Validation error
4. Verify error message
5. Enter grace period: 31 days
6. Verify validation error

**Expected Results:**
- 0 days rejected
- 31+ days rejected
- Error messages clear

### Test 11: Permission Check

**Steps:**
1. Log in as user without two_factor:write
2. Navigate to `/admin/two-factor`
3. **Screenshot:** Permission denied
4. Verify cannot access or modify

**Expected Results:**
- Access denied
- Redirect or error page
- Settings not modifiable

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organization-two-factor-settings` | Get current 2FA settings |
| PUT | `/organization-two-factor-settings` | Update 2FA policy |
| GET | `/two-factor/users-without-2fa` | List users without 2FA |

## Request/Response Format

**Get 2FA Settings Response:**
```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "enforcement_policy": "optional",
  "grace_period_days": 7,
  "enforcement_start_date": "2026-01-26T00:00:00Z"
}
```

**Update 2FA Settings Request:**
```json
{
  "enforcement_policy": "mandatory",
  "grace_period_days": 7
}
```

**Users Without 2FA Response:**
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 10
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page heading | `getByRole('heading', { name: /two-factor/i })` |
| Policy options | Radio group for enforcement_policy |
| Disabled option | `getByRole('radio', { name: /disabled/i })` |
| Optional option | `getByRole('radio', { name: /optional/i })` |
| Mandatory option | `getByRole('radio', { name: /mandatory/i })` |
| Grace period input | `getByLabelText(/grace period/i)` |
| Enforcement date | Date display element |
| Users list | List of user items |
| User name | User display name |
| User email | User email address |
| Save button | `getByRole('button', { name: /save/i })` |
| Success toast | Toast notification |

## Success Criteria

- 2FA settings page loads for authorized users
- All three policy options available
- Can switch between policies
- Grace period configurable for mandatory
- Enforcement date calculated correctly
- Users without 2FA listed
- Settings persist after save
- Validation prevents invalid inputs
- Permission check enforced

## Notes

- Test with different user counts
- Verify grace period edge cases
- Check i18n for policy descriptions
- Test mobile responsiveness
- Verify enforcement countdown display
- Super admin can allow/disallow 2FA settings per org

