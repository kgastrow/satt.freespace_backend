# E2E Test: Change Password

## Test Description
Validate that authenticated users can change their account password by providing their current password and a new password.

## User Story
As an authenticated user
I want to change my password
So that I can maintain account security and update my credentials

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Change Password Successfully

**Steps:**
1. Navigate to `/settings/security/password`
2. Wait for password change form to load
3. **Screenshot:** Password change form
4. Enter current password: "TestPassword123!"
5. Enter new password: "NewSecurePassword456!"
6. Enter confirm password: "NewSecurePassword456!"
7. Click "Change Password" button
8. Wait for operation to complete
9. **Screenshot:** Success state
10. Verify success toast notification
11. Log out and log back in with new password
12. Verify login succeeds with new password

**Expected Results:**
- Form accepts valid current password
- New password accepted and confirmed
- Success notification displayed
- User can log in with new password

### Test 2: Password Requirements Validation

**Steps:**
1. Navigate to `/settings/security/password`
2. Enter current password correctly
3. Enter weak new password: "weak"
4. **Screenshot:** Password requirements errors
5. Verify password requirements are displayed:
   - Minimum 8 characters
   - Uppercase letter required
   - Lowercase letter required
   - Number required
   - Special character required
6. Enter progressively stronger passwords
7. Verify requirements check off as met

**Expected Results:**
- Password requirements clearly displayed
- Real-time validation feedback
- Each requirement visually marked as met/unmet
- Submit prevented until all requirements met

### Test 3: Password Confirmation Mismatch

**Steps:**
1. Navigate to `/settings/security/password`
2. Enter current password correctly
3. Enter new password: "NewSecurePassword456!"
4. Enter different confirm password: "DifferentPassword789!"
5. Click "Change Password" button
6. **Screenshot:** Password mismatch error
7. Verify error message about passwords not matching

**Expected Results:**
- Form validates password confirmation
- Clear error message when passwords don't match
- Submit prevented until passwords match

### Test 4: Incorrect Current Password

**Steps:**
1. Navigate to `/settings/security/password`
2. Enter incorrect current password: "WrongPassword123!"
3. Enter valid new password: "NewSecurePassword456!"
4. Enter matching confirm password
5. Click "Change Password" button
6. Wait for server response
7. **Screenshot:** Current password error
8. Verify error message about incorrect current password

**Expected Results:**
- Server validates current password
- Clear error message when current password wrong
- User must re-enter correct current password

### Test 5: Password Show/Hide Toggle

**Steps:**
1. Navigate to `/settings/security/password`
2. Enter text in current password field
3. Verify password is masked (type="password")
4. **Screenshot:** Masked password
5. Click show password toggle icon
6. Verify password text is visible (type="text")
7. **Screenshot:** Visible password
8. Click toggle again to hide
9. Verify password is masked again

**Expected Results:**
- All password fields have show/hide toggle
- Toggle reveals/hides password text
- Toggle state is independent per field

### Test 6: Change Password via Dialog (If Available)

**Steps:**
1. Navigate to `/settings/account/profile`
2. Look for "Change Password" link or button
3. Click to open password change dialog
4. **Screenshot:** Password change dialog
5. Complete password change in dialog
6. Verify dialog closes on success

**Expected Results:**
- Dialog-based password change works
- Dialog provides same validation as page
- Success closes dialog automatically

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/user/me/change-password` | Change user password |

## Request/Response Format

**Change Password Request:**
```json
{
  "current_password": "TestPassword123!",
  "new_password": "NewSecurePassword456!"
}
```

**Change Password Response (Success):**
```json
{
  "message": "Password changed successfully"
}
```

**Change Password Response (Error):**
```json
{
  "detail": "Current password is incorrect"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Current password input | `input[name="currentPassword"]` or `getByLabelText(/current password/i)` |
| New password input | `input[name="newPassword"]` or `getByLabelText(/new password/i)` |
| Confirm password input | `input[name="confirmPassword"]` or `getByLabelText(/confirm password/i)` |
| Submit button | `getByRole('button', { name: /change password/i })` |
| Show/hide toggle | Button with eye icon adjacent to password field |
| Password requirements | PasswordRequirements component |
| Error messages | `[class*="error"]` or FormMessage |

## Success Criteria

- Valid password change completes successfully
- Password requirements enforced and displayed
- Confirmation mismatch prevented
- Current password verified by server
- Show/hide toggle works for all password fields
- User can log in with new password after change
- Loading state shown during operation

## Notes

- After password change, test that old password no longer works
- Verify session handling after password change
- Test with passwords at exact minimum length
- Test special characters in passwords
- Verify rate limiting on failed attempts
- Check that password change invalidates other sessions (if implemented)
