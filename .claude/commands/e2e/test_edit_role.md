# E2E Test: Edit Role

## Test Description
Validate that super admins can edit existing role name and description.

## User Story
As a super admin
I want to edit existing roles
So that I can update role details as requirements change

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
  - Organization: test-org
- At least one role exists in the system
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Edit Role Dialog

**Steps:**
1. Navigate to `/admin/roles`
2. Wait for roles to load
3. Find a role in the list
4. Click actions dropdown for that role
5. Click "Edit" option
6. **Screenshot:** Edit dialog with pre-filled data
7. Verify dialog title shows "Edit Role"
8. Verify name field pre-filled with current name
9. Verify description field pre-filled with current description

**Expected Results:**
- Edit dialog opens
- Form pre-populated with existing data
- All fields editable

### Test 2: Update Role Name

**Steps:**
1. Open edit dialog for a role
2. Note original name
3. Clear name field
4. Enter new name: "Updated Role Name"
5. **Screenshot:** Updated name field
6. Click "Save" or "Update" button
7. Wait for API response
8. **Screenshot:** After update
9. Verify success notification
10. Verify role name updated in table

**Expected Results:**
- Name can be changed
- Update succeeds
- Table reflects new name

### Test 3: Update Role Description

**Steps:**
1. Open edit dialog for a role
2. Note original description
3. Clear description field
4. Enter new description: "Updated description text"
5. **Screenshot:** Updated description
6. Click "Save" button
7. Verify success notification
8. Verify description updated

**Expected Results:**
- Description can be changed
- Update succeeds
- Change persisted

### Test 4: Clear Description

**Steps:**
1. Open edit dialog for a role with description
2. Clear the description field completely
3. **Screenshot:** Empty description field
4. Click "Save" button
5. Verify update succeeds
6. Verify role now has empty description

**Expected Results:**
- Description can be cleared
- Empty description accepted
- No validation error

### Test 5: Validation - Empty Name on Edit

**Steps:**
1. Open edit dialog for a role
2. Clear the name field
3. Click "Save" button
4. **Screenshot:** Validation error
5. Verify error: "Name is required"
6. Verify form not submitted
7. Enter valid name
8. Verify can now save

**Expected Results:**
- Name still required on edit
- Validation prevents empty name
- Can fix and retry

### Test 6: Cancel Edit

**Steps:**
1. Open edit dialog for a role
2. Note original name and description
3. Change name and description
4. **Screenshot:** Modified form
5. Click "Cancel" button
6. Verify dialog closes
7. Verify role unchanged in table
8. Re-open edit dialog
9. Verify original values restored

**Expected Results:**
- Cancel discards changes
- Original data preserved
- No API call made

### Test 7: Loading State During Edit

**Steps:**
1. Open edit dialog for a role
2. Make changes to form
3. Click "Save" button
4. **Screenshot:** Loading state
5. Verify button shows loading indicator
6. Verify button disabled
7. Verify form inputs disabled
8. Wait for completion

**Expected Results:**
- Loading state shown
- Prevents double submission
- Inputs disabled during save

### Test 8: Edit Error Handling

**Steps:**
1. Open edit dialog for a role
2. Change name to duplicate existing role name
3. Click "Save" button
4. **Screenshot:** Error state
5. Verify error toast notification
6. Verify dialog remains open
7. Verify can correct and retry

**Expected Results:**
- Error message displayed
- Dialog stays open
- Original data recoverable

### Test 9: Edit Without Changes

**Steps:**
1. Open edit dialog for a role
2. Do not modify any fields
3. Click "Save" button
4. **Screenshot:** Save without changes
5. Verify behavior (may succeed or warn)
6. Verify no unexpected changes

**Expected Results:**
- Saving without changes handled gracefully
- No unexpected side effects

### Test 10: Edit Multiple Roles in Sequence

**Steps:**
1. Edit first role, save successfully
2. Edit second role, save successfully
3. **Screenshot:** Both roles updated
4. Verify both changes persisted
5. Verify no data contamination between edits

**Expected Results:**
- Form properly reset between edits
- Each role edited independently
- No stale data issues

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/roles/{id}` | Get role details (if needed) |
| PUT | `/roles/{id}` | Update role |

## Request/Response Format

**Update Role Request:**
```json
{
  "name": "Updated Role Name",
  "description": "Updated description text"
}
```

**Update Role Response (Success):**
```json
{
  "id": "role-uuid",
  "name": "Updated Role Name",
  "description": "Updated description text",
  "created_time": "2024-01-15T10:30:00Z",
  "updated_time": "2024-01-16T14:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in role row |
| Edit option | `getByRole('menuitem', { name: /edit/i })` |
| Edit dialog | Dialog component |
| Dialog title | `getByRole('heading', { name: /edit role/i })` |
| Name input | `getByLabelText(/name/i)` or `getByRole('textbox', { name: /name/i })` |
| Description textarea | `getByLabelText(/description/i)` or `textarea` |
| Save button | `getByRole('button', { name: /save|update/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Validation error | FormMessage component with error text |

## Success Criteria

- Edit dialog pre-populated with current data
- Name can be updated
- Description can be updated or cleared
- Validation prevents empty name
- Cancel discards changes
- Loading state prevents double submission
- Errors handled gracefully
- Changes reflected in table

## Notes

- Verify editing built-in roles (may have restrictions)
- Check if role name uniqueness enforced
- Verify audit log records role edits
- Test with roles assigned to users (changes should propagate)
- Verify i18n for form labels and messages
