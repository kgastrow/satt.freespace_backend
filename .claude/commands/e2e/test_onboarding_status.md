# E2E Test: Onboarding Status

## Test Description
Validate that users can view their onboarding status and progress.

## User Story
As a user
I want to see my onboarding progress
So that I know what steps remain to complete

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with onboarding in progress:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Onboarding Status Page

**Steps:**
1. Log in as user with onboarding
2. Navigate to `/onboarding`
3. **Screenshot:** Onboarding page
4. Verify page loads correctly
5. Verify progress indicator visible

**Expected Results:**
- Page loads successfully
- Progress shown
- Current step indicated

### Test 2: Progress Bar Display

**Steps:**
1. Navigate to onboarding page
2. **Screenshot:** Progress bar
3. Verify progress bar shows:
   - Completed steps count
   - Total steps count
   - Visual progress percentage
4. Verify step progress text: "Step X of Y"

**Expected Results:**
- Progress bar visible
- Accurate counts
- Visual matches numbers

### Test 3: Step List with Status

**Steps:**
1. Navigate to onboarding page
2. **Screenshot:** Step list
3. Verify all steps listed showing:
   - Step name
   - Completion status (checkmark for completed)
   - Current step indicator
4. Verify completed steps visually distinct

**Expected Results:**
- All steps listed
- Status icons shown
- Current step highlighted

### Test 4: View Pending Review Status

**Steps:**
1. Set up user with pending_review status
2. Navigate to `/onboarding`
3. **Screenshot:** Pending review state
4. Verify banner shows "Pending Review"
5. Verify info message about review process
6. Verify cannot submit more steps

**Expected Results:**
- Pending review clearly shown
- Info message displayed
- Steps locked

### Test 5: View Approved Status

**Steps:**
1. Set up user with approved onboarding
2. Navigate to `/onboarding`
3. **Screenshot:** Approved state
4. Verify approval message
5. Verify redirect to dashboard option

**Expected Results:**
- Approval confirmed
- Can proceed to app
- No more steps needed

### Test 6: View Rejected Status

**Steps:**
1. Set up user with rejected onboarding
2. Navigate to `/onboarding`
3. **Screenshot:** Rejected state
4. Verify rejection badge
5. Verify info about next steps

**Expected Results:**
- Rejection status shown
- Guidance provided

### Test 7: View Changes Requested Status

**Steps:**
1. Set up user with change_requested status
2. Navigate to `/onboarding`
3. **Screenshot:** Changes requested state
4. Verify "Changes Requested" badge
5. Verify reviewer feedback shown
6. Verify option to edit and resubmit

**Expected Results:**
- Change request shown
- Feedback visible
- Can edit submission

### Test 8: Onboarding Progress Card on Dashboard

**Steps:**
1. Log in as user with incomplete onboarding
2. Navigate to dashboard
3. **Screenshot:** Progress card on dashboard
4. Verify progress card shows:
   - Current progress
   - Continue button
5. Click continue
6. Verify navigates to onboarding

**Expected Results:**
- Progress card visible
- Shows current step
- Links to onboarding

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/onboarding/status` | Get onboarding status |

## Request/Response Format

**Get Status Response:**
```json
{
  "status": "in_progress",
  "user_type": {
    "id": "type-uuid",
    "name": "Standard User"
  },
  "steps": [
    {
      "id": "step-uuid",
      "name": "Personal Information",
      "display_order": 1,
      "is_completed": true
    },
    {
      "id": "step-uuid-2",
      "name": "Contact Details",
      "display_order": 2,
      "is_completed": false
    }
  ],
  "completed_steps": 1,
  "total_steps": 5
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading')` |
| Progress bar | Progress component |
| Step count text | Text with "Step X of Y" |
| Step list | List of step items |
| Step checkmark | Checkmark icon on completed |
| Current step | Highlighted step indicator |
| Status badge | Badge showing status |
| Continue button | `getByRole('button', { name: /continue/i })` |
| Dashboard card | OnboardingProgressCard component |

## Success Criteria

- Onboarding status page loads
- Progress bar shows accurate counts
- Step list displays all steps
- Completed steps clearly marked
- Current step highlighted
- All status states displayed correctly
- Dashboard progress card works

## Notes

- Test with various completion levels
- Verify progress updates on step completion
- Check i18n for status messages
- Test mobile responsiveness
