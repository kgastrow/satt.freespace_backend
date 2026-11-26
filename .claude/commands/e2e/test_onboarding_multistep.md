# E2E Test: Onboarding Multi-Step Progress

## Test Description
Validate navigation between onboarding steps and progress tracking.

## User Story
As a user
I want to navigate between onboarding steps
So that I can complete the process at my own pace

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with multi-step onboarding:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Onboarding with 3+ steps configured
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Step Indicators

**Steps:**
1. Navigate to `/onboarding`
2. **Screenshot:** Step indicators
3. Verify step indicators show:
   - Total number of steps
   - Current step highlighted
   - Completed steps marked
4. Verify step numbers/names visible

**Expected Results:**
- All steps visible
- Current step clear
- Progress indicators work

### Test 2: Progress from Step 1 to Step 2

**Steps:**
1. Start at step 1
2. Fill required fields
3. Click "Next" button
4. **Screenshot:** Step 2 loaded
5. Verify step 2 form displays
6. Verify step indicator updates
7. Verify progress bar advances

**Expected Results:**
- Navigation to step 2
- Form changes
- Progress updates

### Test 3: Progress Through All Steps

**Steps:**
1. Start at step 1
2. Complete and submit step 1
3. Complete and submit step 2
4. Continue through all steps
5. **Screenshot:** Final step
6. Complete final step
7. **Screenshot:** Onboarding complete

**Expected Results:**
- Can complete all steps
- Progress tracks correctly
- Final submission works

### Test 4: Back Navigation

**Steps:**
1. Complete step 1
2. Move to step 2
3. Click "Back" button
4. **Screenshot:** Back to step 1
5. Verify step 1 displays
6. Verify data preserved
7. Click "Next" again
8. Verify returns to step 2

**Expected Results:**
- Back button works
- Data preserved
- Can return forward

### Test 5: Click to Navigate to Completed Step

**Steps:**
1. Complete steps 1 and 2
2. Currently on step 3
3. Click on step 1 indicator
4. **Screenshot:** Jumped to step 1
5. Verify step 1 form shows
6. Verify saved data displayed
7. Click step 3 to return

**Expected Results:**
- Can click completed steps
- Navigates correctly
- Data shown

### Test 6: Cannot Skip to Future Steps

**Steps:**
1. Start at step 1 (not complete)
2. Try to click step 3 indicator
3. **Screenshot:** Step locked
4. Verify cannot navigate ahead
5. Verify visual indicator of locked

**Expected Results:**
- Future steps not clickable
- Must complete in order
- Clear visual feedback

### Test 7: Step Progress Text

**Steps:**
1. Navigate to various steps
2. **Screenshot:** Progress text
3. Verify text shows "Step 1 of 5"
4. Move to next step
5. Verify text shows "Step 2 of 5"
6. Complete all steps
7. Verify completion message

**Expected Results:**
- Progress text accurate
- Updates on navigation
- Shows total

### Test 8: Resume Onboarding

**Steps:**
1. Complete steps 1 and 2
2. Navigate away from onboarding
3. Return to `/onboarding`
4. **Screenshot:** Resumed progress
5. Verify starts at step 3 (first incomplete)
6. Verify completed steps still marked

**Expected Results:**
- Progress saved
- Resumes at current step
- Previous work retained

### Test 9: Final Step Submit Button

**Steps:**
1. Navigate to final step
2. **Screenshot:** Final step
3. Verify button says "Submit" not "Next"
4. Fill final step
5. Click "Submit"
6. **Screenshot:** Submission complete

**Expected Results:**
- Final step has "Submit"
- Completes onboarding
- Status changes

### Test 10: Progress Bar Animation

**Steps:**
1. Complete a step
2. **Screenshot:** Progress bar updating
3. Observe progress bar animation
4. Verify smooth transition
5. Verify final width matches percentage

**Expected Results:**
- Smooth animation
- Visual feedback
- Accurate percentage

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/onboarding/status` | Get current progress |
| POST | `/onboarding/steps/{id}/submit` | Submit step |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Step indicators | Step list or tabs |
| Current step indicator | Highlighted step item |
| Completed step checkmark | Checkmark icon |
| Next button | `getByRole('button', { name: /next/i })` |
| Back button | `getByRole('button', { name: /back/i })` |
| Submit button (final) | `getByRole('button', { name: /submit/i })` |
| Progress text | Text with "Step X of Y" |
| Progress bar | Progress component |
| Step form | Form component |
| Locked step indicator | Disabled step with lock/gray |

## Success Criteria

- Step indicators show all steps
- Can navigate forward with Next
- Can navigate back with Back
- Can click completed steps
- Cannot skip ahead
- Progress bar accurate
- Progress text updates
- Resume works correctly
- Final step has Submit

## Notes

- Test with varying number of steps
- Verify step order is correct
- Check keyboard navigation
- Test with required vs optional steps
- Verify i18n for navigation labels
