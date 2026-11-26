# E2E Test: Create Role

## Test Description
Validate that super admins can create new roles with name and description.

## User Story
As a super admin
I want to create new roles
So that I can define different access levels for users

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Create Role Dialog

**Steps:**
1. Navigate to `/admin/roles`
2. Wait for page to load
3. Click "Add Role" button
4. **Screenshot:** Create role dialog
5. Verify dialog appears with title "Create Role"
6. Verify form fields:
   - Name input (required)
   - Description textarea (optional)
7. Verify "Cancel" and "Create" buttons present

**Expected Results:**
- Dialog opens on button click
- Form fields are empty
- Both buttons visible

### Test 2: Create Role with Valid Data

**Steps:**
1. Open create role dialog
2. Enter name: "Test Editor Role"
3. Enter description: "A role for testing editors"
4. **Screenshot:** Form filled
5. Click "Create" button
6. Wait for API response
7. **Screenshot:** Success state
8. Verify success toast notification
9. Verify dialog closes
10. Verify new role appears in table

**Expected Results:**
- Role created successfully
- Success notification shown
- Dialog closes automatically
- New role visible in list

### Test 3: Create Role Without Description

**Steps:**
1. Open create role dialog
2. Enter name: "Minimal Role"
3. Leave description empty
4. **Screenshot:** Form with name only
5. Click "Create" button
6. Wait for response
7. Verify role created successfully
8. Verify role appears in list

**Expected Results:**
- Description is optional
- Role created without description
- No validation errors

### Test 4: Validation - Empty Name

**Steps:**
1. Open create role dialog
2. Leave name field empty
3. Enter description: "Some description"
4. Click "Create" button
5. **Screenshot:** Validation error
6. Verify error message: "Name is required"
7. Verify form not submitted
8. Verify dialog remains open

**Expected Results:**
- Name field required
- Validation error displayed
- Form prevented from submitting

### Test 5: Cancel Create Dialog

**Steps:**
1. Open create role dialog
2. Enter name: "Cancelled Role"
3. Enter description: "This will be cancelled"
4. **Screenshot:** Filled form
5. Click "Cancel" button
6. Verify dialog closes
7. Verify no role created
8. Verify no success/error notification

**Expected Results:**
- Cancel closes dialog
- No API call made
- Data discarded

### Test 6: Close Dialog via X Button

**Steps:**
1. Open create role dialog
2. Enter some data
3. Click X button in dialog header
4. **Screenshot:** Dialog closing
5. Verify dialog closes
6. Verify no role created

**Expected Results:**
- X button closes dialog
- Same behavior as Cancel

### Test 7: Loading State During Create

**Steps:**
1. Open create role dialog
2. Fill in valid data
3. Click "Create" button
4. **Screenshot:** Loading state
5. Verify button shows loading spinner
6. Verify button is disabled
7. Verify form inputs disabled during submission
8. Wait for completion

**Expected Results:**
- Loading indicator on button
- Prevents double submission
- Form inputs disabled

### Test 8: Create Role Error Handling

**Steps:**
1. Open create role dialog
2. Enter duplicate role name (if existing)
3. Click "Create" button
4. **Screenshot:** Error response
5. Verify error toast notification
6. Verify dialog remains open
7. Verify can fix and retry

**Expected Results:**
- Error message displayed
- Dialog stays open for correction
- Can retry submission

### Test 9: Keyboard Navigation

**Steps:**
1. Open create role dialog
2. Verify focus on first input (name)
3. Enter name using keyboard
4. Press Tab to move to description
5. Enter description
6. Press Tab to reach buttons
7. **Screenshot:** Focus on Create button
8. Press Enter to submit
9. Verify form submitted

**Expected Results:**
- Tab navigation works
- Focus trap within dialog
- Enter submits form

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/roles` | Create new role |

## Request/Response Format

**Create Role Request:**
```json
{
  "name": "Test Editor Role",
  "description": "A role for testing editors"
}
```

**Create Role Response (Success):**
```json
{
  "id": "new-role-uuid",
  "name": "Test Editor Role",
  "description": "A role for testing editors",
  "created_time": "2024-01-15T10:30:00Z"
}
```

**Create Role Response (Error - Duplicate):**
```json
{
  "detail": "Role with this name already exists"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Add Role button | `getByRole('button', { name: /add role/i })` |
| Create dialog | Dialog component |
| Dialog title | `getByRole('heading', { name: /create role/i })` |
| Name input | `getByLabelText(/name/i)` or `getByRole('textbox', { name: /name/i })` |
| Description textarea | `getByLabelText(/description/i)` or `textarea` |
| Create button | `getByRole('button', { name: /create/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Close (X) button | `getByRole('button', { name: /close/i })` |
| Validation error | FormMessage component with error text |
| Loading spinner | Spinner within Create button |

## Success Criteria

- Create dialog opens correctly
- Role can be created with name and description
- Role can be created with name only
- Validation prevents empty name
- Cancel/X buttons close without saving
- Loading state prevents double submission
- Errors handled and displayed
- New role appears in list after creation

## Notes

- Role names should be unique (verify backend enforcement)
- Verify i18n for form labels and validation messages
- Test with very long name/description
- Verify newly created role can be assigned to users
- Check audit log records role creation
