# E2E Test: SSO Settings

## Test Description
Validate that administrators can configure SSO providers for their organization.

## User Story
As an organization administrator
I want to configure SSO settings
So that users can authenticate via third-party providers like Google

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with organization:write permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- SSO must be allowed by super admin for the organization
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to SSO Settings Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/sso/settings`
3. **Screenshot:** SSO settings page
4. Verify page loads correctly
5. Verify SSO configuration form visible

**Expected Results:**
- Page loads successfully
- Form displays SSO options
- Current settings shown

### Test 2: View SSO Not Allowed State

**Steps:**
1. Set up organization where SSO is not allowed
2. Navigate to `/admin/sso/settings`
3. **Screenshot:** SSO not allowed message
4. Verify error alert displayed
5. Verify form is disabled or hidden

**Expected Results:**
- Alert shows SSO not allowed by platform admin
- Cannot configure SSO
- Contact admin message shown

### Test 3: Enable Google SSO

**Steps:**
1. Navigate to SSO settings
2. **Screenshot:** Google SSO disabled
3. Toggle "Enable Google SSO" switch to on
4. **Screenshot:** Credential fields appear
5. Verify Google Client ID field shown
6. Verify Google Client Secret field shown

**Expected Results:**
- Switch toggles on
- Credential fields revealed
- Fields are editable

### Test 4: Configure Google SSO Credentials

**Steps:**
1. Enable Google SSO
2. Enter Google Client ID: "test-client-id.apps.googleusercontent.com"
3. Enter Google Client Secret: "test-client-secret"
4. **Screenshot:** Credentials entered
5. Click "Save Settings" button
6. **Screenshot:** After save
7. Verify success toast displayed

**Expected Results:**
- Credentials accepted
- Form submits successfully
- Success notification shown

### Test 5: View Saved SSO Settings

**Steps:**
1. Save SSO settings
2. Navigate away from page
3. Return to `/admin/sso/settings`
4. **Screenshot:** Saved settings loaded
5. Verify Google SSO toggle is on
6. Verify Client ID is pre-filled
7. Verify Client Secret shows "set" indicator (masked)

**Expected Results:**
- Settings persisted
- Toggle reflects saved state
- Client ID visible
- Secret masked for security

### Test 6: Update Google SSO Credentials

**Steps:**
1. Load existing SSO settings
2. Update Google Client ID
3. Clear and re-enter Client Secret
4. **Screenshot:** Updated credentials
5. Click "Save Settings"
6. Verify changes saved

**Expected Results:**
- Can update existing settings
- Both fields editable
- Changes persisted

### Test 7: Disable Google SSO

**Steps:**
1. Load page with Google SSO enabled
2. Toggle "Enable Google SSO" to off
3. **Screenshot:** Google SSO disabled
4. Click "Save Settings"
5. Verify settings saved
6. Verify credential fields hidden

**Expected Results:**
- Toggle disables SSO
- Credentials cleared/hidden
- SSO provider disabled

### Test 8: Validation - Empty Credentials

**Steps:**
1. Enable Google SSO
2. Leave Client ID empty
3. Leave Client Secret empty
4. Click "Save Settings"
5. **Screenshot:** Validation errors

**Expected Results:**
- Validation prevents save
- Error messages for required fields
- Form remains in error state

### Test 9: Permission Denied

**Steps:**
1. Log in as user without organization:write permission
2. Navigate to `/admin/sso/settings`
3. **Screenshot:** Permission denied
4. Verify access denied or redirect

**Expected Results:**
- Page not accessible
- Redirect to unauthorized page
- Or hidden in navigation

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/organization-sso-settings` | Get current SSO settings |
| PUT | `/organization-sso-settings` | Update SSO settings |
| GET | `/organization-sso-settings/enabled-providers` | Get enabled providers (public) |

## Request/Response Format

**Get SSO Settings Response:**
```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "google_enabled": true,
  "google_client_id": "client-id.apps.googleusercontent.com"
}
```

**Update SSO Settings Request:**
```json
{
  "google_enabled": true,
  "google_client_id": "client-id.apps.googleusercontent.com",
  "google_client_secret": "client-secret"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page heading | `getByRole('heading', { name: /sso settings/i })` |
| Google SSO toggle | Switch component for google_enabled |
| Client ID input | `getByLabelText(/client id/i)` |
| Client Secret input | `getByLabelText(/client secret/i)` |
| Save button | `getByRole('button', { name: /save/i })` |
| Success toast | Toast notification |
| Error alert | Alert component |
| Validation error | Error message element |

## Success Criteria

- SSO settings page loads for authorized users
- SSO not allowed state displays correctly
- Can enable/disable Google SSO
- Can configure Google credentials
- Settings persist after save
- Client secrets are masked
- Validation prevents invalid saves
- Permission denied for unauthorized users

## Notes

- Currently only Google SSO is supported
- Super admin must allow SSO before org can configure
- Client secrets are never returned in full from API
- Test with SSO allowed and not allowed states
- Verify i18n for all labels and messages

