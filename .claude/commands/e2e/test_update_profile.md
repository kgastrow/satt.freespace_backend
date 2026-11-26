# E2E Test: Update Profile

## Test Description
Validate that authenticated users can update their profile information including first name, last name, and phone number.

## User Story
As an authenticated user
I want to update my profile information
So that I can keep my account details current and accurate

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Update First Name and Last Name

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile form to load
3. **Screenshot:** Initial profile state
4. Clear the first name field
5. Enter new first name: "Updated"
6. Clear the last name field
7. Enter new last name: "Username"
8. Click the "Save" or "Update Profile" button
9. Wait for save operation to complete
10. **Screenshot:** After save with success message
11. Verify success toast notification appears
12. Refresh the page
13. Verify updated values persist

**Expected Results:**
- Form accepts new values
- Save button becomes enabled when changes detected
- Success notification appears after save
- Updated values persist after page refresh

### Test 2: Update Phone Number

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile form to load
3. **Screenshot:** Phone field before update
4. Clear the phone field
5. Enter new phone number: "+1987654321"
6. Click the "Save" button
7. Wait for save operation to complete
8. **Screenshot:** After phone update
9. Verify success toast notification
10. Verify phone field shows updated value

**Expected Results:**
- Phone number field accepts valid phone format
- Save operation completes successfully
- Updated phone number displayed after save

### Test 3: Form Validation - Required Fields

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile form to load
3. Clear the first name field (leave empty)
4. Click the "Save" button
5. **Screenshot:** Validation error for first name
6. Verify validation error message appears
7. Clear the last name field (leave empty)
8. Click the "Save" button
9. **Screenshot:** Validation error for last name
10. Verify validation error message appears

**Expected Results:**
- Form prevents submission with empty required fields
- Validation error messages displayed for each required field
- Save button disabled or form submission prevented

### Test 4: Form State - Dirty Detection

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile form to load
3. Verify Save button is disabled initially (no changes)
4. **Screenshot:** Initial state with disabled save
5. Modify any field (e.g., add character to first name)
6. Verify Save button becomes enabled
7. **Screenshot:** Save button enabled after change
8. Revert the change back to original value
9. Verify Save button returns to disabled state

**Expected Results:**
- Save button reflects form dirty state
- Button enabled only when actual changes made
- Button disabled when form returns to original state

### Test 5: Concurrent Edit Warning

**Steps:**
1. Navigate to `/settings/account/profile`
2. Make changes to first name
3. In another browser/tab, update the same user's profile
4. Click Save in original tab
5. **Screenshot:** Conflict handling (if implemented)
6. Verify appropriate error or warning is shown

**Expected Results:**
- System handles concurrent edits gracefully
- User notified of conflict if data changed externally
- Latest data displayed after refresh

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/user/me` | Fetch current user profile |
| PUT | `/user/me` | Update user profile |

## Request/Response Format

**Update Profile Request:**
```json
{
  "first_name": "Updated",
  "last_name": "Username",
  "phone": "+1987654321"
}
```

**Update Profile Response:**
```json
{
  "id": "uuid",
  "email": "test@example.com",
  "first_name": "Updated",
  "last_name": "Username",
  "phone": "+1987654321",
  "organization_id": "uuid",
  "updated_time": "2024-01-01T00:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| First name input | `input[name="firstName"]` or `getByLabelText(/first name/i)` |
| Last name input | `input[name="lastName"]` or `getByLabelText(/last name/i)` |
| Phone input | `input[name="phone"]` or `getByLabelText(/phone/i)` |
| Save button | `getByRole('button', { name: /save|update/i })` |
| Success toast | `[role="status"]` or toast container |
| Validation error | `[class*="error"]` or `FormMessage` component |

## Success Criteria

- All profile fields can be updated successfully
- Form validation prevents invalid submissions
- Success feedback provided after save
- Changes persist after page refresh
- Loading states shown during save operation
- Form dirty state correctly tracked

## Notes

- Email field is typically read-only (changed via separate flow)
- Test with various phone number formats
- Verify i18n translations for validation messages
- Check that special characters in names are handled correctly
- Test with maximum length inputs
