# E2E Test: Submit User Feedback

## Test Description
Validate that users can submit feedback through the feedback form, including bug reports, suggestions, complaints, and praise.

## User Story
As a user
I want to submit feedback about the application
So that I can report issues, suggest improvements, or share my experience

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user session

## Test Steps

### Test 1: Access Feedback Form

**Steps:**
1. Login as regular user
2. Navigate to feedback page (e.g., `/settings/feedback` or feedback form location)
3. **Screenshot:** Feedback form page
4. Verify feedback form is displayed
5. Verify form fields are present:
   - Feedback type selector (bug, suggestion, complaint, praise, other)
   - Message/description textarea
   - Rating (optional, if applicable)
6. Verify submit button is present

**Expected Results:**
- Feedback form loads successfully
- All required form fields are visible
- Form is ready for input

### Test 2: Submit Bug Report Feedback

**Steps:**
1. Navigate to feedback form
2. Select feedback type: "Bug"
3. Enter detailed message: "When I click the export button on the dashboard, the application shows an error. Steps to reproduce: 1) Go to dashboard 2) Click export 3) Error appears"
4. Add rating if available: 2 stars
5. **Screenshot:** Completed bug report form
6. Click "Submit" button
7. Wait for submission response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify form is cleared or success message shown
11. Verify feedback appears in user's feedback history

**Expected Results:**
- Bug report is submitted via `POST /feedback`
- Success notification displayed
- Feedback is recorded with correct type
- User can see submitted feedback in history

### Test 3: Submit Suggestion Feedback

**Steps:**
1. Navigate to feedback form
2. Select feedback type: "Suggestion"
3. Enter message: "It would be great to have a dark mode option for the application"
4. Add rating if available: 4 stars
5. **Screenshot:** Suggestion form filled
6. Click "Submit" button
7. Wait for submission response
8. Verify success notification
9. Verify feedback recorded with "suggestion" type

**Expected Results:**
- Suggestion is submitted successfully
- Type is recorded as "suggestion"
- Feedback visible in user history

### Test 4: Submit Praise Feedback

**Steps:**
1. Navigate to feedback form
2. Select feedback type: "Praise"
3. Enter message: "Love the new interface! Very intuitive and easy to use."
4. Add rating if available: 5 stars
5. **Screenshot:** Praise form filled
6. Click "Submit" button
7. Verify success notification

**Expected Results:**
- Praise feedback submitted successfully
- Type is recorded as "praise"
- Rating captured correctly

### Test 5: Form Validation - Empty Submission

**Steps:**
1. Navigate to feedback form
2. Leave all fields empty
3. Click "Submit" button
4. **Screenshot:** Validation errors
5. Verify message field shows required error
6. Verify type field shows required error (if required)
7. Fill in message only
8. Click "Submit" button
9. Verify submission proceeds (if type has default)

**Expected Results:**
- Empty form submission is prevented
- Validation errors are clear and specific
- Required fields must be filled

### Test 6: View Submitted Feedback History

**Steps:**
1. Submit multiple feedback items (from previous tests)
2. Navigate to feedback history section
3. **Screenshot:** Feedback history list
4. Verify all submitted feedback items are displayed
5. Verify each item shows:
   - Type badge (bug, suggestion, etc.)
   - Message content
   - Submission date
   - Status (new, in_review, resolved, dismissed)
6. Click on a feedback item to expand details
7. Verify full message and any admin replies are shown

**Expected Results:**
- User can view their feedback history
- History is fetched from `GET /feedback` (user-scoped)
- Feedback items show correct type and status
- Expandable details work correctly

### Test 7: Feedback Status Badges

**Steps:**
1. Navigate to feedback history
2. **Screenshot:** Various status badges
3. Verify status badges display correctly:
   - "New" - default badge style
   - "In Review" - secondary style
   - "Resolved" - success/default style
   - "Dismissed" - outline style
4. Verify type badges display correctly:
   - "Bug" - destructive/red style
   - "Suggestion" - blue style
   - "Complaint" - warning style
   - "Praise" - success/green style
   - "Other" - default style

**Expected Results:**
- Status badges use correct colors/variants
- Type badges are visually distinct
- All badge text is readable

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/feedback` | Submit new feedback |
| GET | `/feedback` | Get user's feedback history |

## Request/Response Format

**Submit Feedback Request:**
```json
{
  "type": "bug",
  "message": "Description of the bug or feedback",
  "rating": 3
}
```

**Submit Feedback Response:**
```json
{
  "id": "uuid",
  "type": "bug",
  "message": "Description of the bug or feedback",
  "rating": 3,
  "status": "new",
  "created_at": "2024-01-15T10:00:00Z"
}
```

**Get Feedback History Response:**
```json
{
  "feedback": [
    {
      "id": "uuid",
      "type": "bug",
      "message": "Description...",
      "rating": 3,
      "status": "in_review",
      "created_at": "2024-01-15T10:00:00Z",
      "admin_replies": [
        {
          "id": "uuid",
          "message": "Thank you for reporting...",
          "created_at": "2024-01-16T10:00:00Z"
        }
      ]
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Feedback type select | `getByLabelText(/type|category/i)` or select element |
| Message textarea | `getByLabelText(/message|description|feedback/i)` |
| Rating input | Star rating component or radio buttons |
| Submit button | `getByRole('button', { name: /submit|send/i })` |
| Feedback history | List container with feedback items |
| Status badge | Badge element with status text |
| Type badge | Badge element with type text |
| Expand button | Accordion or collapsible trigger |

## Success Criteria

- Users can submit feedback of all types
- Form validation works correctly
- Success notifications display on submission
- Feedback history shows all submissions
- Status and type badges display correctly
- Admin replies are visible in history

## Notes

- Verify feedback types match backend enum values
- Test optional rating field behavior
- Verify character limits on message field
- Test i18n translations for all feedback types and statuses
- Consider testing attachment uploads if supported
