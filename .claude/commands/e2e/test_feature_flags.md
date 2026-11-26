# E2E Test: Feature Flags Management

## Test Description
Validate that administrators can create, edit, delete feature flags and manage organization-level overrides.

## User Story
As an administrator
I want to manage feature flags
So that I can control feature rollouts and enable/disable functionality for specific organizations

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with feature flag management permissions
- At least one organization exists for override testing

## Test Steps

### Test 1: Access Feature Flags Page

**Steps:**
1. Login as admin user
2. Navigate to feature flags page (e.g., `/admin/feature-flags`)
3. **Screenshot:** Feature flags page loaded
4. Verify page title "Feature Flags" or similar
5. Verify feature flags table is displayed
6. Verify "Create" button is present
7. Verify table columns: key, name, description, default_enabled, overrides, actions

**Expected Results:**
- Admin can access feature flags management
- Flags fetched from `GET /feature-flags`
- Table displays all feature flags
- Create button is visible

### Test 2: Create New Feature Flag

**Steps:**
1. Navigate to feature flags page
2. Click "Create" button
3. **Screenshot:** Create feature flag dialog
4. Fill in details:
   - Key: "new_dashboard_ui"
   - Name: "New Dashboard UI"
   - Description: "Enable the redesigned dashboard interface"
   - Default Enabled: false (toggle off)
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new flag appears in table
11. Verify default_enabled shows "Disabled" badge

**Expected Results:**
- Create dialog opens with form fields
- Key validation (lowercase, underscores, no spaces)
- Flag created via `POST /feature-flags`
- Success notification displayed
- Flag appears in list

### Test 3: Feature Flag Key Validation

**Steps:**
1. Click "Create" button
2. Enter invalid key: "Invalid Key!"
3. Try to save
4. **Screenshot:** Key validation error
5. Verify key format validation error
6. Enter valid key: "valid_feature_key"
7. Verify validation passes
8. Close dialog without saving

**Expected Results:**
- Invalid keys are rejected
- Key format: lowercase, underscores allowed
- No spaces or special characters
- Clear validation message

### Test 4: Edit Feature Flag

**Steps:**
1. Navigate to feature flags page
2. Find an existing feature flag
3. Click "Edit" action button
4. **Screenshot:** Edit dialog with pre-filled data
5. Verify form is pre-filled with existing data
6. Modify name: "Updated Feature Name"
7. Modify description: "Updated description"
8. Toggle default_enabled to opposite state
9. **Screenshot:** Modified form
10. Click "Save" button
11. Verify success notification
12. Verify table shows updated data

**Expected Results:**
- Edit dialog opens with existing data
- Changes saved via `PUT /feature-flags/{id}`
- Table reflects updates
- Default enabled state can be toggled

### Test 5: Add Organization Override

**Steps:**
1. Navigate to feature flags page
2. Find a feature flag
3. Click "Manage Overrides" or "Override" action
4. **Screenshot:** Override management dialog
5. Click "Add Override" button
6. Select an organization from dropdown
7. Set override value: enabled (if default is disabled)
8. **Screenshot:** Override configured
9. Click "Save" button
10. Verify success notification
11. Verify overrides column shows organization badge
12. **Screenshot:** Overrides badge in table

**Expected Results:**
- Override dialog shows existing overrides
- Can add override for specific organization
- Override saved successfully
- Organization badge appears in overrides column

### Test 6: Edit Organization Override

**Steps:**
1. Navigate to feature flags page
2. Find flag with existing override
3. Click "Manage Overrides"
4. **Screenshot:** Existing overrides list
5. Find the override and click edit
6. Toggle override value
7. Save changes
8. Verify override updated

**Expected Results:**
- Existing overrides are listed
- Can edit override values
- Changes persist after save

### Test 7: Remove Organization Override

**Steps:**
1. Navigate to feature flags page
2. Find flag with existing override
3. Click "Manage Overrides"
4. Find override to remove
5. Click "Remove" or delete icon
6. **Screenshot:** Remove confirmation
7. Confirm removal
8. Verify override is removed
9. Verify organization badge removed from table

**Expected Results:**
- Can remove individual overrides
- Removal requires confirmation
- Override removed from list
- Table updates accordingly

### Test 8: Toggle Feature Flag Default State

**Steps:**
1. Navigate to feature flags page
2. Find a feature flag
3. Note current default_enabled state
4. Click toggle in the default_enabled column (if available)
5. OR edit and toggle default_enabled
6. **Screenshot:** State toggled
7. Verify success notification
8. Verify badge updates (Enabled/Disabled)

**Expected Results:**
- Default state can be toggled quickly
- Visual feedback shows new state
- Change persists

### Test 9: Delete Feature Flag

**Steps:**
1. Navigate to feature flags page
2. Find a feature flag to delete
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation shows flag key
6. Click "Confirm Delete"
7. Verify success notification
8. **Screenshot:** After deletion
9. Verify flag removed from table

**Expected Results:**
- Delete requires confirmation
- Flag deleted via `DELETE /feature-flags/{id}`
- All overrides also deleted
- Success notification shown

### Test 10: Search/Filter Feature Flags

**Steps:**
1. Navigate to feature flags page (with multiple flags)
2. Enter search term in filter input
3. **Screenshot:** Filtered results
4. Verify only matching flags are shown
5. Clear search
6. Verify all flags shown again

**Expected Results:**
- Search filters by key and name
- Filter is case-insensitive
- Clear restores full list

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/feature-flags` | List all feature flags |
| POST | `/feature-flags` | Create new feature flag |
| PUT | `/feature-flags/{id}` | Update feature flag |
| DELETE | `/feature-flags/{id}` | Delete feature flag |
| POST | `/feature-flags/{id}/overrides` | Add organization override |
| PUT | `/feature-flags/{id}/overrides/{org_id}` | Update override |
| DELETE | `/feature-flags/{id}/overrides/{org_id}` | Remove override |

## Request/Response Format

**Create Feature Flag Request:**
```json
{
  "key": "new_dashboard_ui",
  "name": "New Dashboard UI",
  "description": "Enable the redesigned dashboard interface",
  "default_enabled": false
}
```

**Feature Flag Response:**
```json
{
  "id": "uuid",
  "key": "new_dashboard_ui",
  "name": "New Dashboard UI",
  "description": "Enable the redesigned dashboard interface",
  "default_enabled": false,
  "overrides": [
    {
      "organization_id": "uuid",
      "organization_name": "Acme Corp",
      "enabled": true
    }
  ],
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Add Override Request:**
```json
{
  "organization_id": "uuid",
  "enabled": true
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add/i })` |
| Feature flags table | Table with flag rows |
| Key input | `getByLabelText(/key/i)` |
| Name input | `getByLabelText(/name/i)` |
| Description input | `getByLabelText(/description/i)` |
| Default enabled toggle | `getByRole('switch')` or toggle |
| Overrides button | `getByRole('button', { name: /overrides/i })` |
| Organization select | Select dropdown for organizations |
| Edit button | `getByRole('button', { name: /edit/i })` |
| Delete button | `getByRole('button', { name: /delete/i })` |
| Override badge | Badge showing organization names |

## Success Criteria

- CRUD operations work correctly
- Key validation enforces format
- Organization overrides work
- Toggle default state updates properly
- Overrides show as badges
- Delete removes flag and overrides
- Search/filter works

## Notes

- Verify key uniqueness validation
- Test with many overrides (UI scaling)
- Verify override priority (org override > default)
- Test flag evaluation in application
- Verify admin-only access
