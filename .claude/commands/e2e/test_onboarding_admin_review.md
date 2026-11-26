# E2E Test: Onboarding Admin Review

## Test Description
Validate that administrators can review and approve/reject onboarding submissions.

## User Story
As an administrator
I want to review onboarding submissions
So that I can approve or request changes from users

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with onboarding review permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- Onboarding submissions pending review
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Review Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/onboarding-review`
3. **Screenshot:** Review page
4. Verify page loads correctly
5. Verify submission list visible

**Expected Results:**
- Page loads successfully
- Submissions listed
- Filter controls visible

### Test 2: View Submission List

**Steps:**
1. Navigate to review page
2. **Screenshot:** Submission list
3. Verify list shows:
   - User name/email
   - User type badge
   - Submission date
   - Attention indicator
4. Verify pagination if many

**Expected Results:**
- Submissions displayed
- Key info visible
- Pagination works

### Test 3: Filter by Status

**Steps:**
1. View submission list
2. Click "Pending Review" tab
3. **Screenshot:** Pending only
4. Verify only pending shown
5. Click "Change Requested" tab
6. Verify only change_requested shown

**Expected Results:**
- Status tabs filter
- Results match filter
- Counts accurate

### Test 4: Search Submissions

**Steps:**
1. Enter user name in search
2. **Screenshot:** Search results
3. Verify filtered results
4. Clear search
5. Verify all shown again

**Expected Results:**
- Search filters list
- Matches by name/email
- Clear works

### Test 5: View Submission Details

**Steps:**
1. Click on a submission in list
2. **Screenshot:** Detail panel opens
3. Verify details shown:
   - User info header
   - All step data in accordions
   - Field values displayed
4. Verify can scroll through data

**Expected Results:**
- Detail panel opens
- All data visible
- Steps in accordions

### Test 6: View Submitted File

**Steps:**
1. Find submission with uploaded file
2. Open detail panel
3. **Screenshot:** File display
4. Click download link
5. Verify file downloads

**Expected Results:**
- File shown in submission
- Download link works
- File downloads correctly

### Test 7: Approve Submission

**Steps:**
1. Select pending submission
2. Click "Approve" button
3. **Screenshot:** Approve confirmation
4. Confirm approval
5. **Screenshot:** After approval
6. Verify submission status changes
7. Verify removed from pending list

**Expected Results:**
- Approve button works
- Confirmation shown
- Status changes to approved

### Test 8: Reject Submission

**Steps:**
1. Select pending submission
2. Click "Reject" button
3. **Screenshot:** Reject dialog
4. Enter rejection reason
5. Click "Reject"
6. **Screenshot:** After rejection
7. Verify status changes to rejected

**Expected Results:**
- Reject requires reason
- Reason is required field
- Status changes to rejected

### Test 9: Request Changes

**Steps:**
1. Select pending submission
2. Click "Request Changes" button
3. **Screenshot:** Request changes dialog
4. Enter feedback comment
5. Click "Request Changes"
6. **Screenshot:** After request
7. Verify status changes to change_requested
8. Verify comment saved

**Expected Results:**
- Change request works
- Comment required
- Status changes
- Comment visible

### Test 10: Add Review Comment

**Steps:**
1. Open submission detail
2. Scroll to comments section
3. Enter comment in input
4. Click "Add Comment"
5. **Screenshot:** Comment added
6. Verify comment appears in thread
7. Verify timestamp shown

**Expected Results:**
- Can add comments
- Comment appears
- Timestamped correctly

### Test 11: View Comment Thread

**Steps:**
1. Find submission with comments
2. Open detail panel
3. **Screenshot:** Comments thread
4. Verify shows:
   - Admin comments
   - User responses
   - Author labels
   - Timestamps
5. Verify chronological order

**Expected Results:**
- All comments visible
- Author identified
- Timestamps shown
- Proper order

### Test 12: Navigate Between Submissions

**Steps:**
1. Open a submission
2. Click "Next" navigation
3. **Screenshot:** Next submission
4. Verify different submission shown
5. Click "Previous"
6. Verify returns to first

**Expected Results:**
- Navigation arrows work
- Can browse submissions
- No page reload needed

### Test 13: Keyboard Navigation

**Steps:**
1. Select a submission
2. Press Down Arrow
3. Verify next submission selected
4. Press Up Arrow
5. Verify previous selected
6. Press Escape
7. Verify detail panel closes

**Expected Results:**
- Arrow keys navigate
- Escape closes detail
- Power user friendly

### Test 14: Mobile Detail View

**Steps:**
1. View on mobile viewport
2. Click submission
3. **Screenshot:** Mobile detail sheet
4. Verify bottom sheet opens
5. Verify can scroll content
6. Close sheet

**Expected Results:**
- Mobile uses sheet
- Touch friendly
- Can close easily

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/onboarding/review/submissions` | List submissions |
| GET | `/onboarding/review/{id}` | Get submission details |
| POST | `/onboarding/review/{id}/approve` | Approve |
| POST | `/onboarding/review/{id}/reject` | Reject |
| POST | `/onboarding/review/{id}/request-change` | Request changes |
| GET | `/onboarding/review/{id}/comments` | Get comments |
| POST | `/onboarding/review/{id}/comments` | Add comment |

## Request/Response Format

**Approve Request:**
```json
{}
```

**Reject Request:**
```json
{
  "reason": "Documentation incomplete"
}
```

**Request Changes Request:**
```json
{
  "comment": "Please update your address"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Submission list | List of submission items |
| Status tabs | Tab components for filtering |
| Search input | `getByPlaceholder(/search/i)` |
| Submission item | Clickable list item |
| Detail panel | Side panel or sheet |
| User info | Header section in detail |
| Step accordion | Accordion items for steps |
| Field value | Data display elements |
| Approve button | `getByRole('button', { name: /approve/i })` |
| Reject button | `getByRole('button', { name: /reject/i })` |
| Request Changes button | `getByRole('button', { name: /request changes/i })` |
| Reason textarea | Textarea in dialog |
| Comment input | Input for adding comments |
| Comment thread | List of comment messages |
| Navigation arrows | Previous/Next buttons |

## Success Criteria

- Review page shows submissions
- Can filter by status
- Can search submissions
- Detail panel shows all data
- Approve changes status
- Reject requires reason
- Request changes works
- Comments can be added
- Comment thread displays
- Navigation works
- Keyboard shortcuts work
- Mobile view works

## Notes

- Test with various submission types
- Verify file preview/download
- Check permission requirements
- Test with many submissions
- Verify i18n for all labels
- Test with required attention flag
