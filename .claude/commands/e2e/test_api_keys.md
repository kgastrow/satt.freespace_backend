# E2E Test: API Keys Management

## Test Description
Validate that administrators can create, edit, delete API keys and manage their permissions and expiration settings.

## User Story
As an administrator
I want to manage API keys
So that I can provide secure programmatic access to the API for integrations

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with API key management permissions
- Assignable permissions exist in the system

## Test Steps

### Test 1: Access API Keys Page

**Steps:**
1. Login as admin user
2. Navigate to API keys page (e.g., `/admin/api-keys`)
3. **Screenshot:** API keys page loaded
4. Verify page title "API Keys" or similar
5. Verify API keys table is displayed
6. Verify "Create" button is present
7. Verify table columns: name, prefix, permissions, created, expires, last_used, actions

**Expected Results:**
- Admin can access API keys management
- Keys fetched from `GET /api-keys`
- Table displays all API keys
- Key values are masked (only prefix shown)

### Test 2: Create New API Key

**Steps:**
1. Navigate to API keys page
2. Click "Create" button
3. **Screenshot:** Create API key dialog
4. Fill in details:
   - Name: "Integration API Key"
   - Expiration: 90 days from now (or custom date)
5. Select permissions from available list
6. **Screenshot:** Permissions selected
7. Click "Create" button
8. Wait for success response
9. **Screenshot:** Key created dialog showing full key
10. Verify full API key is displayed (only time it's shown)
11. Verify "Copy to clipboard" button is present
12. Verify warning about storing key securely
13. Copy the key
14. Close dialog
15. Verify new key appears in table with masked value

**Expected Results:**
- Create dialog shows form and permission selector
- Key created via `POST /api-keys`
- Full key shown ONLY on creation
- Copy to clipboard works
- Key stored securely (masked in future views)

### Test 3: Copy API Key on Creation

**Steps:**
1. Create a new API key (follow Test 2 steps)
2. When full key is displayed, click "Copy" button
3. **Screenshot:** Copy confirmation
4. Verify copy success feedback (toast or icon change)
5. Paste key somewhere to verify it copied correctly
6. Close the dialog

**Expected Results:**
- Copy button copies full key to clipboard
- Visual feedback confirms copy
- Key is correctly copied

### Test 4: API Key Permission Selection

**Steps:**
1. Click "Create" button
2. Locate permissions selector
3. **Screenshot:** Available permissions
4. Verify permissions are listed with descriptions
5. Select multiple permissions
6. Verify selected permissions are highlighted
7. Deselect a permission
8. Verify it's removed from selection
9. Cancel creation

**Expected Results:**
- Permissions fetched from `GET /api-keys/permissions`
- Multi-select works correctly
- Clear visual indication of selected permissions

### Test 5: Edit API Key

**Steps:**
1. Navigate to API keys page
2. Find an existing API key
3. Click "Edit" action button
4. **Screenshot:** Edit dialog
5. Verify name is editable
6. Verify permissions can be changed
7. Verify expiration can be updated
8. Modify name: "Updated Key Name"
9. Add/remove a permission
10. Click "Save" button
11. Verify success notification
12. Verify table shows updated data

**Expected Results:**
- Edit dialog opens with existing data
- Name and permissions are editable
- Key value is NOT shown (cannot be retrieved)
- Changes saved via `PUT /api-keys/{id}`

### Test 6: View API Key Details

**Steps:**
1. Navigate to API keys page
2. Find an API key with permissions
3. Note permissions count in table
4. Click on key row or "View" action
5. **Screenshot:** Key details view
6. Verify details shown:
   - Name
   - Key prefix (masked)
   - Permissions list
   - Created date
   - Expiration date
   - Last used timestamp

**Expected Results:**
- Details view shows all metadata
- Full key is NOT shown
- Permissions are listed clearly

### Test 7: API Key Expiration Status

**Steps:**
1. Navigate to API keys page
2. Look for keys with various expiration states
3. **Screenshot:** Expiration badges
4. Verify expired keys show "Expired" badge (red)
5. Verify keys expiring soon show warning (yellow)
6. Verify valid keys show normal expiration date
7. Create a key with past expiration (if allowed)
8. Verify it shows as expired immediately

**Expected Results:**
- Expiration status is clearly indicated
- Expired badge styling is distinct
- Warning for soon-to-expire keys

### Test 8: Delete API Key

**Steps:**
1. Navigate to API keys page
2. Find an API key to delete
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation shows key name
6. Verify warning about breaking integrations
7. Click "Confirm Delete"
8. Verify success notification
9. **Screenshot:** After deletion
10. Verify key removed from table

**Expected Results:**
- Delete requires confirmation
- Warning about integration impact
- Key deleted via `DELETE /api-keys/{id}`
- Key removed from list

### Test 9: Regenerate API Key

**Steps:**
1. Navigate to API keys page
2. Find an existing API key
3. Click "Regenerate" action (if available)
4. **Screenshot:** Regenerate confirmation
5. Verify warning about old key being invalidated
6. Confirm regeneration
7. **Screenshot:** New key displayed
8. Verify new full key is shown
9. Verify old key no longer works (manual verification)

**Expected Results:**
- Regenerate creates new key value
- Old key is immediately invalidated
- New key shown like on creation
- Permissions and metadata preserved

### Test 10: Filter API Keys

**Steps:**
1. Navigate to API keys page with multiple keys
2. Enter search term in filter input
3. **Screenshot:** Filtered results
4. Verify only matching keys shown
5. Filter by expiration status (if available)
6. Clear filters
7. Verify all keys shown

**Expected Results:**
- Search filters by name
- Status filters work
- Filters can be cleared

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api-keys` | List all API keys |
| POST | `/api-keys` | Create new API key |
| PUT | `/api-keys/{id}` | Update API key |
| DELETE | `/api-keys/{id}` | Delete API key |
| POST | `/api-keys/{id}/regenerate` | Regenerate key |
| GET | `/api-keys/permissions` | Get assignable permissions |

## Request/Response Format

**Create API Key Request:**
```json
{
  "name": "Integration API Key",
  "expires_at": "2024-04-15T00:00:00Z",
  "permissions": ["read:users", "write:users", "read:metrics"]
}
```

**Create API Key Response (includes full key):**
```json
{
  "id": "uuid",
  "name": "Integration API Key",
  "key": "sk_live_abc123xyz789...",
  "prefix": "sk_live_abc1...",
  "permissions": ["read:users", "write:users", "read:metrics"],
  "expires_at": "2024-04-15T00:00:00Z",
  "created_at": "2024-01-15T10:00:00Z"
}
```

**List API Keys Response (key masked):**
```json
{
  "api_keys": [
    {
      "id": "uuid",
      "name": "Integration API Key",
      "prefix": "sk_live_abc1...",
      "permissions_count": 3,
      "expires_at": "2024-04-15T00:00:00Z",
      "last_used_at": "2024-01-14T15:30:00Z",
      "created_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|generate/i })` |
| API keys table | Table with key rows |
| Name input | `getByLabelText(/name/i)` |
| Expiration input | Date picker or input |
| Permission checkboxes | Checkbox list for permissions |
| Copy button | `getByRole('button', { name: /copy/i })` |
| Edit button | `getByRole('button', { name: /edit/i })` |
| Delete button | `getByRole('button', { name: /delete|revoke/i })` |
| Regenerate button | `getByRole('button', { name: /regenerate/i })` |
| Expired badge | Badge with "Expired" text |
| Key prefix | Masked key display |

## Success Criteria

- API keys can be created with permissions
- Full key shown only on creation
- Copy to clipboard works
- Keys properly masked in list
- Edit updates metadata (not key)
- Delete revokes access immediately
- Expiration status clearly shown
- Regenerate creates new key

## Notes

- Verify key format (prefix indicates environment)
- Test key authentication in separate test
- Verify rate limiting respects key permissions
- Test with maximum permissions
- Verify admin-only access
- Consider testing key in API call
