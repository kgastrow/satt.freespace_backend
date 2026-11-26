# E2E Test: API Rate Limits Management

## Test Description
Validate that administrators can create, edit, and delete API rate limit policies per permission code.

## User Story
As an administrator
I want to configure API rate limits
So that I can prevent API abuse and ensure fair resource usage

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with rate limit management permissions
- Permission codes exist in the system

## Test Steps

### Test 1: Access Rate Limits Page

**Steps:**
1. Login as admin user
2. Navigate to rate limits page (e.g., `/admin/api-keys/rate-limits` or `/admin/rate-limits`)
3. **Screenshot:** Rate limits page loaded
4. Verify page title "API Rate Limits" or similar
5. Verify rate limits table is displayed
6. Verify "Create" button is present
7. Verify table columns: permission_code, requests_per_minute, burst_limit, updated, actions

**Expected Results:**
- Admin can access rate limits management
- Limits fetched from `GET /api-key-rate-limits`
- Table displays all rate limit policies
- Create button is visible

### Test 2: Create New Rate Limit Policy

**Steps:**
1. Navigate to rate limits page
2. Click "Create" button
3. **Screenshot:** Create rate limit dialog
4. Fill in details:
   - Permission Code: Select from dropdown (e.g., "read:users")
   - Requests Per Minute: 100
   - Burst Limit: 10
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new policy appears in table
11. Verify permission_code shows as code badge

**Expected Results:**
- Create dialog opens with form fields
- Permission code dropdown lists available permissions
- Policy created via `POST /api-key-rate-limits`
- Success notification displayed
- Policy appears in table

### Test 3: Rate Limit Input Validation

**Steps:**
1. Click "Create" button
2. Leave all fields empty
3. Try to save
4. **Screenshot:** Validation errors
5. Verify all required fields show errors
6. Enter negative value for requests_per_minute: -10
7. Verify validation error for negative value
8. Enter zero for burst_limit: 0
9. Verify handling (may be valid or show error)
10. Enter very large value: 999999
11. Verify if there's a maximum limit validation

**Expected Results:**
- Required field validation works
- Negative values rejected
- Reasonable limits enforced
- Clear validation messages

### Test 4: Edit Rate Limit Policy

**Steps:**
1. Navigate to rate limits page
2. Find an existing rate limit policy
3. Click "Edit" action button
4. **Screenshot:** Edit dialog with pre-filled data
5. Verify form shows existing values
6. Verify permission_code may not be editable (or is shown)
7. Modify requests_per_minute: 200
8. Modify burst_limit: 20
9. **Screenshot:** Modified form
10. Click "Save" button
11. Verify success notification
12. Verify table shows updated values

**Expected Results:**
- Edit dialog opens with existing data
- Permission code typically not editable
- Changes saved via `PUT /api-key-rate-limits/{id}`
- Table reflects updates

### Test 5: Delete Rate Limit Policy

**Steps:**
1. Navigate to rate limits page
2. Find a rate limit policy to delete
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation shows policy details
6. Click "Confirm Delete"
7. Verify success notification
8. **Screenshot:** After deletion
9. Verify policy removed from table

**Expected Results:**
- Delete requires confirmation
- Policy deleted via `DELETE /api-key-rate-limits/{id}`
- Success notification shown
- Policy removed from list

### Test 6: Unique Permission Code Constraint

**Steps:**
1. Note an existing permission_code in the table
2. Click "Create" button
3. Select the same permission_code from dropdown
4. Fill in rate limit values
5. Try to save
6. **Screenshot:** Duplicate error
7. Verify error message about duplicate permission_code
8. Select a different permission_code
9. Verify form can be submitted

**Expected Results:**
- Each permission_code can only have one policy
- Duplicate attempt shows error
- Clear error message explains constraint

### Test 7: Permission Code Badge Display

**Steps:**
1. Navigate to rate limits page
2. **Screenshot:** Permission code badges
3. Verify permission codes display as styled badges/chips
4. Verify badge format is consistent
5. Verify badge shows full permission code text

**Expected Results:**
- Permission codes styled as code badges
- Consistent styling across table
- Full code visible or in tooltip

### Test 8: View Rate Limit Details

**Steps:**
1. Navigate to rate limits page
2. Hover over or click on a rate limit row
3. **Screenshot:** Rate limit details
4. Verify details shown:
   - Permission code
   - Requests per minute
   - Burst limit
   - Last updated timestamp
   - Updated by user (if available)

**Expected Results:**
- Details are accessible
- All configured values visible
- Audit information shown

### Test 9: Bulk Operations (if available)

**Steps:**
1. Navigate to rate limits page
2. Check if bulk selection is available
3. Select multiple rate limit policies
4. Look for bulk actions (delete, update)
5. **Screenshot:** Bulk selection
6. If available, perform bulk delete
7. Verify confirmation includes count
8. Confirm action
9. Verify all selected items deleted

**Expected Results:**
- Bulk selection works (if implemented)
- Bulk actions available
- Confirmation shows affected count
- Operations complete successfully

### Test 10: Rate Limit Effect Verification

**Steps:**
1. Create a very low rate limit: 2 requests per minute
2. Note the permission code
3. Use an API key with that permission
4. Make rapid API calls (> 2 per minute)
5. **Screenshot:** Rate limit exceeded error
6. Verify 429 Too Many Requests response
7. Verify error message includes retry information
8. Delete or update the test rate limit

**Expected Results:**
- Rate limits are enforced
- 429 response returned when exceeded
- Retry-After header or message provided
- Rate limit resets after time window

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api-key-rate-limits` | List all rate limit policies |
| POST | `/api-key-rate-limits` | Create new rate limit policy |
| PUT | `/api-key-rate-limits/{id}` | Update rate limit policy |
| DELETE | `/api-key-rate-limits/{id}` | Delete rate limit policy |

## Request/Response Format

**Create Rate Limit Request:**
```json
{
  "permission_code": "read:users",
  "requests_per_minute": 100,
  "burst_limit": 10
}
```

**Rate Limit Response:**
```json
{
  "id": "uuid",
  "permission_code": "read:users",
  "requests_per_minute": 100,
  "burst_limit": 10,
  "created_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:00:00Z"
}
```

**List Rate Limits Response:**
```json
{
  "rate_limits": [
    {
      "id": "uuid",
      "permission_code": "read:users",
      "requests_per_minute": 100,
      "burst_limit": 10,
      "updated_at": "2024-01-15T10:00:00Z"
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add/i })` |
| Rate limits table | Table with policy rows |
| Permission code select | `getByLabelText(/permission/i)` or select element |
| Requests per minute input | `getByLabelText(/requests.*minute/i)` |
| Burst limit input | `getByLabelText(/burst/i)` |
| Save button | `getByRole('button', { name: /save|create/i })` |
| Edit button | `getByRole('button', { name: /edit/i })` |
| Delete button | `getByRole('button', { name: /delete/i })` |
| Permission code badge | Badge/chip with code styling |

## Success Criteria

- CRUD operations work correctly
- Input validation prevents invalid values
- Unique permission code constraint enforced
- Rate limits are actually enforced in API
- Permission codes display as badges
- Delete requires confirmation
- Changes reflect immediately

## Notes

- Verify rate limit algorithm (sliding window, token bucket, etc.)
- Test burst limit behavior separately from per-minute
- Consider default rate limits for unconfigured permissions
- Verify rate limit headers in API responses
- Test with different permission scopes
- Verify admin-only access
