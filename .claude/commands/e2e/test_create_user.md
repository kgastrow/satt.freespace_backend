# E2E Test: Create User

## Test Description
Validate that organization admins can create new user accounts within their organization.

## User Story
As an organization admin
I want to create new user accounts
So that I can onboard new team members to the system

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with `users:write` permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Create User Dialog

**Steps:**
1. Navigate to `/admin/users`
2. Wait for page to load
3. **Screenshot:** Users page with create button
4. Locate "Create User" or "Add User" button
5. Click create button
6. Wait for dialog to open
7. **Screenshot:** Create user dialog
8. Verify dialog contains all required fields

**Expected Results:**
- Create button visible to authorized users
- Dialog opens with form fields
- Form is initially empty

### Test 2: Create User with Valid Data

**Steps:**
1. Open create user dialog (Test 1)
2. Enter first name: "New"
3. Enter last name: "User"
4. Enter email: "newuser@example.com"
5. Enter password: "SecurePassword123!"
6. Enter phone (optional): "+1234567890"
7. **Screenshot:** Filled create form
8. Click "Create" or "Submit" button
9. Wait for creation to complete
10. **Screenshot:** Success state
11. Verify success toast notification
12. Verify dialog closes
13. Verify new user appears in list

**Expected Results:**
- Form accepts valid data
- User created successfully
- Success notification shown
- New user visible in table

### Test 3: Form Validation - Required Fields

**Steps:**
1. Open create user dialog
2. Leave first name empty
3. Click "Create" button
4. **Screenshot:** First name validation error
5. Verify validation message for first name
6. Leave last name empty
7. Click "Create" button
8. Verify validation message for last name
9. Leave email empty
10. Click "Create" button
11. Verify validation message for email
12. Leave password empty
13. Click "Create" button
14. Verify validation message for password

**Expected Results:**
- All required fields validated
- Clear error messages per field
- Form submission prevented

### Test 4: Email Validation

**Steps:**
1. Open create user dialog
2. Enter invalid email: "notanemail"
3. Fill other required fields
4. Click "Create" button
5. **Screenshot:** Email validation error
6. Verify email format error message
7. Enter valid email format
8. Verify error clears

**Expected Results:**
- Invalid email formats rejected
- Clear validation message
- Valid email accepted

### Test 5: Password Validation

**Steps:**
1. Open create user dialog
2. Fill required fields
3. Enter weak password: "weak"
4. Click "Create" button
5. **Screenshot:** Password validation error
6. Verify password requirements message (min 8 chars)
7. Enter strong password: "SecurePassword123!"
8. Verify error clears

**Expected Results:**
- Weak passwords rejected
- Password requirements enforced
- Valid passwords accepted

### Test 6: Duplicate Email Prevention

**Steps:**
1. Note an existing user's email in the system
2. Open create user dialog
3. Enter the existing email address
4. Fill all other required fields
5. Click "Create" button
6. **Screenshot:** Duplicate email error
7. Verify error about email already in use

**Expected Results:**
- Duplicate emails prevented
- Clear error message
- User not created with duplicate email

### Test 7: Super Admin Can Set Admin Flag

**Steps:**
1. Log in as super admin (is_admin: true)
2. Navigate to `/admin/users`
3. Open create user dialog
4. **Screenshot:** Form with admin toggle (super admin only)
5. Fill required fields
6. Toggle "Is Admin" or "Super Admin" switch on
7. Click "Create" button
8. Verify user created with admin privileges

**Expected Results:**
- Admin toggle visible only to super admins
- Can create admin users
- Admin flag set correctly on user

### Test 8: Cancel Create User

**Steps:**
1. Open create user dialog
2. Fill some fields with data
3. **Screenshot:** Partially filled form
4. Click "Cancel" button
5. Verify dialog closes
6. Re-open create dialog
7. Verify form is empty (not persisted)

**Expected Results:**
- Cancel closes dialog
- No user created
- Form data not persisted

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users` | Create new user |

## Request/Response Format

**Create User Request:**
```json
{
  "email": "newuser@example.com",
  "first_name": "New",
  "last_name": "User",
  "password": "SecurePassword123!",
  "phone": "+1234567890",
  "is_admin": false
}
```

**Create User Response:**
```json
{
  "id": "new-uuid",
  "email": "newuser@example.com",
  "first_name": "New",
  "last_name": "User",
  "phone": "+1234567890",
  "is_admin": false,
  "organization_id": "org-uuid",
  "created_time": "2024-01-01T00:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create user button | `getByRole('button', { name: /create user|add user/i })` |
| Dialog | Dialog component |
| First name input | `input[name="firstName"]` or `getByLabelText(/first name/i)` |
| Last name input | `input[name="lastName"]` or `getByLabelText(/last name/i)` |
| Email input | `input[name="email"]` or `getByLabelText(/email/i)` |
| Password input | `input[name="password"]` or `getByLabelText(/password/i)` |
| Phone input | `input[name="phone"]` or `getByLabelText(/phone/i)` |
| Admin toggle | Switch component for is_admin |
| Submit button | `getByRole('button', { name: /create|submit/i })` within dialog |
| Cancel button | `getByRole('button', { name: /cancel/i })` within dialog |
| Validation errors | FormMessage components |

## Success Criteria

- Create dialog opens and displays form
- Valid user data accepted and user created
- Form validation prevents invalid submissions
- Duplicate emails rejected
- Password requirements enforced
- Super admin can set admin flag
- Cancel properly dismisses dialog
- New user appears in list after creation

## Notes

- Verify email verification workflow triggered if applicable
- Test with various email formats
- Test phone number with different formats
- Verify created user can log in
- Check audit logging for user creation
- Verify i18n for form labels and errors
