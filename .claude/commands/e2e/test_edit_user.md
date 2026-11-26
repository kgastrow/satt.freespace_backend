# E2E Test: Edit User

## Test Description
Validate that organization admins can edit existing user details including name, phone, and optionally password.

## User Story
As an organization admin
I want to edit user account details
So that I can update user information when needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with `users:write` permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- At least one other user exists in the organization
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Edit User Dialog

**Steps:**
1. Navigate to `/admin/users`
2. Wait for user list to load
3. Find a user row to edit
4. Click actions dropdown for that user
5. **Screenshot:** Actions dropdown open
6. Click "Edit" option
7. Wait for edit dialog to open
8. **Screenshot:** Edit user dialog with pre-filled data
9. Verify form is pre-populated with user's current data

**Expected Results:**
- Edit option in actions dropdown
- Dialog opens with existing data
- All editable fields populated

### Test 2: Update User Name

**Steps:**
1. Open edit dialog for a user (Test 1)
2. Note original first name and last name
3. **Screenshot:** Original values
4. Clear first name field
5. Enter new first name: "Updated"
6. Clear last name field
7. Enter new last name: "Name"
8. Click "Save" or "Update" button
9. Wait for update to complete
10. **Screenshot:** Success state
11. Verify success notification
12. Verify user list shows updated name

**Expected Results:**
- Name fields can be updated
- Changes saved successfully
- Updated values reflected in list

### Test 3: Update User Phone

**Steps:**
1. Open edit dialog for a user
2. **Screenshot:** Current phone value
3. Clear phone field
4. Enter new phone: "+9876543210"
5. Click "Save" button
6. Wait for update
7. Verify success notification
8. Re-open edit dialog
9. Verify phone is updated

**Expected Results:**
- Phone field can be updated
- New phone number saved
- Changes persist

### Test 4: Update User Password (Optional)

**Steps:**
1. Open edit dialog for a user
2. **Screenshot:** Password field (optional)
3. Locate password field (may be empty/optional)
4. Enter new password: "NewUserPassword123!"
5. Click "Save" button
6. Wait for update
7. **Screenshot:** After password update
8. Verify success (may need to test login with new password)

**Expected Results:**
- Password update is optional
- Empty password field doesn't clear password
- New password can be set
- User can login with new password

### Test 5: Edit Validation - Required Fields

**Steps:**
1. Open edit dialog for a user
2. Clear first name field (leave empty)
3. Click "Save" button
4. **Screenshot:** Validation error
5. Verify error message for required field
6. Restore first name
7. Clear last name field
8. Click "Save" button
9. Verify error message

**Expected Results:**
- Required fields validated
- Cannot save with empty required fields
- Clear error messages

### Test 6: Edit Validation - Email (Usually Read-Only)

**Steps:**
1. Open edit dialog for a user
2. **Screenshot:** Email field state
3. Verify email field is read-only or disabled
4. Verify email cannot be changed via edit

**Expected Results:**
- Email typically not editable (security reason)
- Field displayed but disabled
- Email change requires separate process

### Test 7: Cancel Edit Without Saving

**Steps:**
1. Open edit dialog for a user
2. Note original values
3. Modify first name and last name
4. **Screenshot:** Modified form
5. Click "Cancel" button
6. Verify dialog closes
7. Check user list - verify original values unchanged
8. Re-open edit dialog
9. Verify original values still present

**Expected Results:**
- Cancel discards changes
- Original data preserved
- No partial saves

### Test 8: Edit Self (Edge Case)

**Steps:**
1. Find current admin user in the list
2. Open edit dialog for self
3. **Screenshot:** Editing own account
4. Modify first name
5. Click "Save"
6. Verify update succeeds
7. Verify header/profile reflects change

**Expected Results:**
- Can edit own account (if permitted)
- Changes reflected across app
- Session not disrupted

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/users/{id}` | Get user details for edit form |
| PUT | `/users/{id}` | Update user details |

## Request/Response Format

**Update User Request:**
```json
{
  "first_name": "Updated",
  "last_name": "Name",
  "phone": "+9876543210",
  "password": "NewUserPassword123!"
}
```

**Update User Response:**
```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "first_name": "Updated",
  "last_name": "Name",
  "phone": "+9876543210",
  "organization_id": "org-uuid",
  "updated_time": "2024-01-01T00:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Edit option | `getByRole('menuitem', { name: /edit/i })` |
| Edit dialog | Dialog component |
| First name input | `input[name="firstName"]` |
| Last name input | `input[name="lastName"]` |
| Email input | `input[name="email"]` (likely disabled) |
| Phone input | `input[name="phone"]` |
| Password input | `input[name="password"]` |
| Save button | `getByRole('button', { name: /save|update/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |

## Success Criteria

- Edit dialog pre-populates with current data
- Name and phone can be updated
- Password optionally updateable
- Required field validation works
- Email typically read-only
- Cancel discards changes
- Updates reflected in list immediately
- Success feedback provided

## Notes

- Verify audit log records edit operations
- Test editing users with different roles
- Check permission boundaries (can admin A edit admin B?)
- Verify cannot edit super admin if not super admin
- Test with various phone formats
- Verify i18n for dialog labels and messages
