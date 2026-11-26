# E2E Test: View Feedback (Admin)

## Test Description
Validate that administrators can view, filter, and respond to user feedback submissions.

## User Story
As an administrator
I want to view and manage user feedback
So that I can address issues, respond to users, and track feedback trends

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with feedback management permissions
- Multiple feedback submissions exist with various types and statuses

## Test Steps

### Test 1: Access Admin Feedback Dashboard

**Steps:**
1. Login as admin user
2. Navigate to admin feedback page (e.g., `/admin/feedback`)
3. **Screenshot:** Feedback dashboard loaded
4. Verify page title "Feedback" or "User Feedback"
5. Verify feedback list/table is displayed
6. Verify filter options are available
7. Verify feedback items show:
   - User email/name
   - Type badge
   - Status badge
   - Message preview
   - Submission date
   - Rating (if provided)

**Expected Results:**
- Admin can access feedback management
- Feedback is fetched from `GET /feedback`
- All feedback items are listed with details
- Pagination or infinite scroll works

### Test 2: Filter Feedback by Type

**Steps:**
1. Navigate to admin feedback page
2. Note total feedback count
3. Select filter: Type = "Bug"
4. **Screenshot:** Filtered by bug type
5. Verify only bug reports are displayed
6. Verify count updates to show filtered results
7. Select filter: Type = "Suggestion"
8. Verify only suggestions are displayed
9. Clear type filter
10. Verify all feedback is shown again

**Expected Results:**
- Type filter works correctly
- API call includes type filter parameter
- Results update immediately
- Filter can be cleared

### Test 3: Filter Feedback by Status

**Steps:**
1. Navigate to admin feedback page
2. Select filter: Status = "New"
3. **Screenshot:** New feedback only
4. Verify only new/unreviewed feedback is shown
5. Select filter: Status = "In Review"
6. Verify only in-review feedback is shown
7. Select filter: Status = "Resolved"
8. Verify only resolved feedback is shown
9. Clear status filter

**Expected Results:**
- Status filter works correctly
- Multiple statuses can be filtered
- Filters can be combined (type + status)

### Test 4: View Feedback Details

**Steps:**
1. Navigate to admin feedback page
2. Click on a feedback item to expand/view details
3. **Screenshot:** Expanded feedback details
4. Verify full message is displayed
5. Verify user information is shown
6. Verify submission timestamp
7. Verify rating display (stars)
8. Verify any previous admin replies are shown
9. Verify reply form/option is available

**Expected Results:**
- Feedback details expand correctly
- Full message visible (not truncated)
- User context is provided
- Reply functionality is accessible

### Test 5: Reply to Feedback

**Steps:**
1. Navigate to admin feedback page
2. Click on a feedback item to expand
3. Locate reply form/textarea
4. Enter reply: "Thank you for your feedback. We are looking into this issue."
5. **Screenshot:** Reply form filled
6. Click "Send Reply" or submit button
7. Wait for response
8. **Screenshot:** Reply submitted
9. Verify success notification
10. Verify reply appears in feedback thread
11. Verify feedback status may update (if auto-update configured)

**Expected Results:**
- Admin can reply to feedback
- Reply is submitted via `POST /feedback/{id}/reply`
- Reply appears in conversation thread
- User will be notified (via email/notification)

### Test 6: Update Feedback Status

**Steps:**
1. Navigate to admin feedback page
2. Find a feedback item with "New" status
3. Click status dropdown or edit option
4. **Screenshot:** Status change options
5. Change status to "In Review"
6. Verify success notification
7. Verify status badge updates in list
8. Change status to "Resolved"
9. Verify status updates
10. Change status to "Dismissed"
11. Verify status updates

**Expected Results:**
- Status can be changed via dropdown or action
- Status updates via `PATCH /feedback/{id}/status`
- Status badge reflects change immediately
- Status changes are logged

### Test 7: Mark Feedback as Viewed

**Steps:**
1. Navigate to admin feedback page
2. Note any feedback with "unviewed" indicator (bold, badge, etc.)
3. Click on the unviewed feedback item
4. Wait for view to register
5. **Screenshot:** Viewed state
6. Verify unviewed indicator is removed
7. Navigate away and back
8. Verify feedback still shows as viewed

**Expected Results:**
- Viewing feedback marks it as viewed
- API call: `POST /feedback/{id}/viewed`
- Visual indicator changes
- View state persists

### Test 8: Pagination and Sorting

**Steps:**
1. Navigate to admin feedback page (with many items)
2. Verify initial page shows limited items
3. Scroll down or click "Load More"
4. **Screenshot:** More items loaded
5. Verify additional feedback items appear
6. If sorting available, sort by date descending
7. Verify newest feedback appears first
8. Sort by date ascending
9. Verify oldest feedback appears first

**Expected Results:**
- Pagination works correctly
- Sorting options function properly
- Large feedback lists are manageable

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/feedback` | List all feedback (admin view) |
| GET | `/feedback/{id}` | Get single feedback details |
| POST | `/feedback/{id}/reply` | Reply to feedback |
| PATCH | `/feedback/{id}/status` | Update feedback status |
| POST | `/feedback/{id}/viewed` | Mark feedback as viewed |

## Request/Response Format

**List Feedback Response:**
```json
{
  "feedback": [
    {
      "id": "uuid",
      "user": {
        "id": "uuid",
        "email": "user@example.com",
        "name": "John Doe"
      },
      "type": "bug",
      "message": "Found an issue with...",
      "rating": 2,
      "status": "new",
      "viewed": false,
      "created_at": "2024-01-15T10:00:00Z",
      "replies": []
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 20
}
```

**Reply to Feedback Request:**
```json
{
  "message": "Thank you for your feedback. We are looking into this."
}
```

**Update Status Request:**
```json
{
  "status": "in_review"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Feedback list | List/table container |
| Type filter | Filter dropdown for type |
| Status filter | Filter dropdown for status |
| Feedback item | List item or table row |
| Expand button | Click target to expand details |
| Reply textarea | `getByLabelText(/reply|response/i)` |
| Send reply button | `getByRole('button', { name: /send|reply/i })` |
| Status dropdown | Status change selector |
| Type badge | Badge with type indicator |
| Status badge | Badge with status indicator |

## Success Criteria

- Admin can view all user feedback
- Filtering by type and status works
- Feedback details are fully viewable
- Replies can be submitted successfully
- Status updates work correctly
- Viewed state is tracked
- Pagination handles large datasets

## Notes

- Verify admin-only access (non-admins cannot access)
- Test real-time updates if using WebSockets
- Verify email notifications sent on reply
- Test i18n translations for admin interface
- Consider export functionality if available
