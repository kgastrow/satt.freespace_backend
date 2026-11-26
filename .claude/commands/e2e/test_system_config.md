# E2E Test: System Configuration Management

## Test Description
Validate that administrators can create, edit, and delete system configuration key-value pairs.

## User Story
As an administrator
I want to manage system configuration settings
So that I can control application behavior without code changes

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with system configuration management permissions

## Test Steps

### Test 1: Access System Config Page

**Steps:**
1. Login as admin user
2. Navigate to system config page (e.g., `/admin/system-config`)
3. **Screenshot:** System config page loaded
4. Verify page title "System Configuration" or similar
5. Verify config table is displayed
6. Verify "Create" button is present
7. Verify table columns: key, value, type, last_updated, updated_by, actions

**Expected Results:**
- Admin can access system config management
- Config fetched from `GET /system-configs`
- Table displays all configuration entries
- Create button is visible

### Test 2: Create String Configuration

**Steps:**
1. Navigate to system config page
2. Click "Create" button
3. **Screenshot:** Create config dialog
4. Fill in details:
   - Key: "app.maintenance_message"
   - Value: "System is under maintenance"
   - Description: "Message shown during maintenance mode"
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new config appears in table
11. Verify type badge shows "string"

**Expected Results:**
- Create dialog opens with form fields
- Key validation enforces format
- Config created via `POST /system-configs`
- Type auto-detected as string
- Entry appears in table

### Test 3: Key Format Validation

**Steps:**
1. Click "Create" button
2. Enter invalid key: "Invalid Key!"
3. Try to save
4. **Screenshot:** Key validation error
5. Verify key format validation error
6. Verify allowed format: lowercase, numbers, dots, dashes, underscores
7. Enter valid key: "app.feature.enabled_v2"
8. Verify validation passes
9. Cancel creation

**Expected Results:**
- Key format: `^[a-z0-9._-]+$`
- Invalid keys rejected with clear message
- Valid keys accepted

### Test 4: Create JSON Configuration

**Steps:**
1. Click "Create" button
2. Fill in details:
   - Key: "email.smtp_settings"
   - Value: `{"host": "smtp.example.com", "port": 587, "tls": true}`
3. **Screenshot:** JSON value entered
4. Click "Save" button
5. Verify success notification
6. Verify new config appears in table
7. Verify type badge shows "json" or "object"
8. **Screenshot:** JSON type badge

**Expected Results:**
- JSON values are detected and parsed
- Type shows as JSON/object
- Value stored correctly
- Can be retrieved as JSON

### Test 5: Create Numeric Configuration

**Steps:**
1. Click "Create" button
2. Fill in details:
   - Key: "rate_limit.default_rpm"
   - Value: "1000"
3. Click "Save" button
4. Verify type badge shows "number"
5. Verify value stored as numeric

**Expected Results:**
- Numeric values detected
- Type badge shows "number"
- Value preserved correctly

### Test 6: Create Boolean Configuration

**Steps:**
1. Click "Create" button
2. Fill in details:
   - Key: "feature.dark_mode_enabled"
   - Value: "true"
3. Click "Save" button
4. Verify type badge shows "boolean"
5. Create another with value "false"
6. Verify both boolean values work

**Expected Results:**
- Boolean values detected
- "true" and "false" handled correctly
- Type badge shows "boolean"

### Test 7: Edit Configuration

**Steps:**
1. Navigate to system config page
2. Find an existing configuration
3. Click "Edit" action button
4. **Screenshot:** Edit dialog with pre-filled data
5. Verify key is displayed (may not be editable)
6. Modify value: "Updated value"
7. Modify description: "Updated description"
8. **Screenshot:** Modified form
9. Click "Save" button
10. Verify success notification
11. Verify table shows updated value
12. Verify last_updated timestamp changed
13. Verify updated_by shows current user

**Expected Results:**
- Edit dialog opens with existing data
- Key typically not editable (or with warning)
- Changes saved via `PUT /system-configs/{id}`
- Audit fields updated

### Test 8: Value Truncation Display

**Steps:**
1. Create or find a config with a long value
2. **Screenshot:** Truncated value in table
3. Verify long values are truncated (e.g., 50 chars)
4. Hover over truncated value
5. Verify full value shown in tooltip
6. OR click to view details
7. Verify full value accessible

**Expected Results:**
- Long values truncated in table
- Full value accessible via tooltip or detail view
- Truncation indicator (ellipsis)

### Test 9: Delete Configuration

**Steps:**
1. Navigate to system config page
2. Find a configuration to delete
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation shows key being deleted
6. Verify warning about potential impact
7. Click "Confirm Delete"
8. Verify success notification
9. **Screenshot:** After deletion
10. Verify config removed from table

**Expected Results:**
- Delete requires confirmation
- Warning about application impact
- Config deleted via `DELETE /system-configs/{id}`
- Entry removed from table

### Test 10: Unique Key Constraint

**Steps:**
1. Note an existing key in the table
2. Click "Create" button
3. Enter the same key
4. Fill in a value
5. Try to save
6. **Screenshot:** Duplicate key error
7. Verify error message about duplicate key
8. Enter a unique key
9. Verify form can be submitted

**Expected Results:**
- Each key must be unique
- Duplicate key attempt shows error
- Clear error message

### Test 11: Search/Filter Configurations

**Steps:**
1. Navigate to system config page with multiple entries
2. Enter search term in filter input (e.g., "email")
3. **Screenshot:** Filtered results
4. Verify only matching configs shown
5. Clear search
6. Verify all configs shown

**Expected Results:**
- Search filters by key and value
- Filter is case-insensitive
- Clear restores full list

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/system-configs` | List all configurations |
| POST | `/system-configs` | Create new configuration |
| PUT | `/system-configs/{id}` | Update configuration |
| DELETE | `/system-configs/{id}` | Delete configuration |

## Request/Response Format

**Create Config Request:**
```json
{
  "key": "app.maintenance_message",
  "value": "System is under maintenance",
  "description": "Message shown during maintenance mode"
}
```

**Config Response:**
```json
{
  "id": "uuid",
  "key": "app.maintenance_message",
  "value": "System is under maintenance",
  "value_type": "string",
  "description": "Message shown during maintenance mode",
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z",
  "updated_by": {
    "id": "uuid",
    "email": "admin@example.com"
  }
}
```

**List Configs Response:**
```json
{
  "configs": [
    {
      "id": "uuid",
      "key": "app.maintenance_message",
      "value": "System is under maintenance",
      "value_type": "string",
      "description": "...",
      "updated_at": "2024-01-15T10:00:00Z",
      "updated_by_email": "admin@example.com"
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add/i })` |
| Config table | Table with config rows |
| Key input | `getByLabelText(/key/i)` |
| Value input/textarea | `getByLabelText(/value/i)` |
| Description input | `getByLabelText(/description/i)` |
| Type badge | Badge showing value type |
| Save button | `getByRole('button', { name: /save|create/i })` |
| Edit button | `getByRole('button', { name: /edit/i })` |
| Delete button | `getByRole('button', { name: /delete/i })` |
| Search input | `getByPlaceholder(/search|filter/i)` |

## Success Criteria

- CRUD operations work correctly
- Key format validation enforces pattern
- Different value types detected correctly
- Type badges display appropriately
- Long values truncated with full view available
- Unique key constraint enforced
- Audit fields track changes
- Search/filter works

## Notes

- Verify configuration changes take effect in application
- Test with sensitive values (may need encryption)
- Consider environment-specific configs
- Verify key naming conventions
- Test with nested JSON objects
- Verify admin-only access
