# E2E Test: Onboarding Form Submission

## Test Description
Validate that users can complete onboarding form steps and submit their data.

## User Story
As a user
I want to complete onboarding forms
So that I can finish setting up my account

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with onboarding in progress:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Onboarding steps configured
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Current Step Form

**Steps:**
1. Navigate to `/onboarding`
2. **Screenshot:** Current step form
3. Verify form title matches step name
4. Verify form fields displayed
5. Verify required field indicators

**Expected Results:**
- Form displays for current step
- All fields visible
- Required fields marked

### Test 2: Fill Text Fields

**Steps:**
1. Find a text input field
2. Enter valid text data
3. **Screenshot:** Text field filled
4. Verify no validation errors
5. Verify can proceed

**Expected Results:**
- Text input works
- Data entered correctly
- No errors for valid data

### Test 3: Fill Email Field

**Steps:**
1. Find email field (if present)
2. Enter valid email: "test@example.com"
3. **Screenshot:** Email field
4. Verify email validation passes
5. Enter invalid email
6. Verify validation error

**Expected Results:**
- Email validation works
- Valid emails accepted
- Invalid rejected with error

### Test 4: Submit Step Successfully

**Steps:**
1. Fill all required fields with valid data
2. **Screenshot:** Form filled
3. Click "Next" or "Submit" button
4. Wait for submission
5. **Screenshot:** After submission
6. Verify success message
7. Verify progress updates

**Expected Results:**
- Form submits successfully
- Progress increases
- Next step shown

### Test 5: Validation - Required Fields

**Steps:**
1. Leave required field empty
2. Click submit button
3. **Screenshot:** Validation error
4. Verify error message for required field
5. Fill the field
6. Verify can now submit

**Expected Results:**
- Required fields enforced
- Clear error messages
- Can fix and proceed

### Test 6: Pre-filled User Data

**Steps:**
1. Navigate to step with profile fields
2. **Screenshot:** Pre-filled fields
3. Verify first_name pre-filled
4. Verify last_name pre-filled
5. Verify email pre-filled
6. Verify phone pre-filled (if available)

**Expected Results:**
- Profile data auto-fills
- Reduces user effort
- Can be modified

### Test 7: Navigate to Previous Step

**Steps:**
1. Complete first step
2. Move to second step
3. Click "Back" button
4. **Screenshot:** Back to previous step
5. Verify previous step shown
6. Verify data preserved

**Expected Results:**
- Back navigation works
- Previous step displays
- Data not lost

### Test 8: Edit Completed Step

**Steps:**
1. Complete multiple steps
2. Click on completed step in list
3. **Screenshot:** Editing completed step
4. Verify form shows saved data
5. Make changes
6. Save changes

**Expected Results:**
- Can return to completed steps
- Saved data displayed
- Can make edits

### Test 9: Form Loading State

**Steps:**
1. Submit a step
2. **Screenshot:** Loading state
3. Verify submit button shows loading
4. Verify form disabled during submit
5. Wait for completion

**Expected Results:**
- Loading indicator shown
- Prevents double submit
- Completes successfully

### Test 10: Resubmit After Changes Requested

**Steps:**
1. Set up submission with change_requested status
2. Navigate to onboarding
3. View change request feedback
4. Edit affected steps
5. **Screenshot:** Edited form
6. Click "Resubmit for Review"
7. **Screenshot:** After resubmit
8. Verify status changes to pending_review

**Expected Results:**
- Can edit after change request
- Resubmit button works
- Status updates

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/onboarding/status` | Get steps and data |
| POST | `/onboarding/steps/{step_id}/submit` | Submit step |
| POST | `/onboarding/submissions/{id}/resubmit` | Resubmit |

## Request/Response Format

**Submit Step Request:**
```json
{
  "data": {
    "first_name": "John",
    "last_name": "Doe",
    "email": "john@example.com",
    "phone": "+1234567890"
  }
}
```

**Submit Step Response:**
```json
{
  "message": "Step submitted successfully",
  "step_id": "step-uuid",
  "next_step_id": "next-step-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Step form | Form component |
| Text input | `getByLabelText()` with field name |
| Email input | `input[type="email"]` |
| Required indicator | Asterisk or required text |
| Submit button | `getByRole('button', { name: /next|submit/i })` |
| Back button | `getByRole('button', { name: /back/i })` |
| Validation error | Error message element |
| Loading indicator | Spinner on submit button |
| Step list | Clickable step items |

## Success Criteria

- Current step form displays correctly
- Text and email fields work
- Form submits successfully
- Progress updates on submit
- Required field validation works
- Profile data pre-fills
- Back navigation works
- Can edit completed steps
- Resubmit works after change request

## Notes

- Test with various field types
- Verify form data size limit (100KB)
- Check validation messages are i18n
- Test with optional fields
