# E2E Test: API Error Toast Notifications

## Test Description
Validate that API errors are properly displayed to users via toast notifications, providing clear feedback about what went wrong.

## User Story
As a user
I want to see clear error messages when something goes wrong
So that I understand what happened and can take appropriate action

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user session
- Understanding of toast notification system (sonner or similar)

## Test Steps

### Test 1: Display API Error Toast

**Steps:**
1. Login as user
2. Trigger an API error (e.g., try to access forbidden resource)
3. **Screenshot:** Error toast displayed
4. Verify toast notification appears
5. Verify toast contains error message
6. Verify toast has error styling (red/destructive)
7. Wait for toast to auto-dismiss or close manually

**Expected Results:**
- Error toast appears on API failure
- Message describes the error
- Toast has appropriate error styling
- Toast is noticeable but not blocking

### Test 2: 400 Bad Request Error

**Steps:**
1. Trigger a 400 Bad Request error (e.g., invalid form data)
2. **Screenshot:** 400 error toast
3. Verify toast appears with validation error
4. Verify message is helpful (explains what's wrong)
5. Verify toast doesn't show technical details

**Expected Results:**
- User-friendly validation message
- No technical jargon exposed
- Clear indication of what to fix

### Test 3: 401 Unauthorized Error

**Steps:**
1. Simulate expired token or unauthorized access
2. **Screenshot:** 401 error handling
3. Verify appropriate response:
   - Toast with "Session expired" message
   - OR automatic redirect to login
4. Verify user understands they need to re-authenticate

**Expected Results:**
- Clear session expiry message
- User directed to login
- No confusing error codes

### Test 4: 403 Forbidden Error

**Steps:**
1. Try to access a resource user doesn't have permission for
2. **Screenshot:** 403 error toast
3. Verify toast indicates permission denied
4. Verify message is clear (e.g., "You don't have permission")
5. Verify no sensitive information exposed

**Expected Results:**
- Permission denied message shown
- User understands they lack access
- No information leakage

### Test 5: 404 Not Found Error (API)

**Steps:**
1. Request a resource that doesn't exist (via API)
2. **Screenshot:** 404 error toast
3. Verify toast indicates resource not found
4. Verify helpful message (e.g., "Item not found")
5. Verify appropriate for context

**Expected Results:**
- Not found message displayed
- Context-appropriate wording
- User understands item doesn't exist

### Test 6: 422 Validation Error

**Steps:**
1. Submit form with invalid data that passes client validation but fails server
2. **Screenshot:** 422 validation error toast
3. Verify toast shows validation error
4. Verify specific field errors shown (if available)
5. Verify message helps user fix the issue

**Expected Results:**
- Server validation errors displayed
- Specific field guidance if possible
- User can correct and retry

### Test 7: 429 Rate Limit Error

**Steps:**
1. Trigger rate limiting (rapid API calls)
2. **Screenshot:** 429 rate limit toast
3. Verify toast indicates rate limiting
4. Verify message suggests waiting
5. Verify retry-after info shown (if available)

**Expected Results:**
- Rate limit clearly communicated
- User knows to slow down
- Retry guidance provided

### Test 8: 500 Internal Server Error

**Steps:**
1. Trigger a 500 error (may need backend manipulation)
2. **Screenshot:** 500 error toast
3. Verify generic error message shown
4. Verify no technical stack trace exposed
5. Verify message is apologetic/professional

**Expected Results:**
- Generic "something went wrong" message
- No sensitive server details exposed
- Professional error handling

### Test 9: Network Error (No Connection)

**Steps:**
1. Simulate network disconnect (DevTools > Offline)
2. Trigger an API call
3. **Screenshot:** Network error toast
4. Verify toast indicates network issue
5. Verify message suggests checking connection
6. Restore network and retry

**Expected Results:**
- Network error distinguished from API error
- User understands it's connectivity issue
- Suggestion to check connection

### Test 10: Toast Dismissal

**Steps:**
1. Trigger an error to show toast
2. Verify toast appears
3. Wait for auto-dismiss (typically 3-5 seconds)
4. **Screenshot:** Toast dismissed automatically
5. Trigger another error
6. Manually close toast (click X or dismiss)
7. **Screenshot:** Toast manually dismissed
8. Verify toast closes immediately

**Expected Results:**
- Toasts auto-dismiss after timeout
- Manual dismiss works via close button
- Dismissed toasts don't reappear

### Test 11: Multiple Error Toasts

**Steps:**
1. Trigger multiple errors in quick succession
2. **Screenshot:** Multiple toasts displayed
3. Verify all errors shown (stacked)
4. Verify each has distinct message
5. Verify toasts don't overlap
6. Dismiss one toast
7. Verify others remain
8. Let remaining auto-dismiss

**Expected Results:**
- Multiple toasts can display
- Proper stacking/positioning
- Each toast independent
- No UI overlap issues

### Test 12: Toast Positioning

**Steps:**
1. Trigger an error toast
2. **Screenshot:** Toast position
3. Verify toast appears in expected location (typically top-right or bottom-right)
4. Verify toast doesn't cover important UI elements
5. Verify toast is visible without scrolling

**Expected Results:**
- Consistent toast position
- Doesn't block critical UI
- Visible immediately

### Test 13: Error Toast Accessibility

**Steps:**
1. Enable screen reader
2. Trigger an error toast
3. **Screenshot:** Accessibility check
4. Verify toast is announced by screen reader
5. Verify toast has appropriate ARIA role (alert or status)
6. Verify close button is accessible
7. Tab to close button and activate

**Expected Results:**
- Screen reader announces toast
- Proper ARIA attributes
- Keyboard accessible dismiss

### Test 14: Error Message Translation

**Steps:**
1. Set language to non-English
2. Trigger various errors
3. **Screenshot:** Translated error messages
4. Verify error messages are translated
5. Verify no untranslated text
6. Verify backend error messages translated

**Expected Results:**
- Error messages respect language setting
- Backend errors translated via namespace
- Consistent language experience

### Test 15: Error Toast with Action

**Steps:**
1. Trigger error that has an action (if implemented)
   - e.g., "Session expired" with "Login" button
2. **Screenshot:** Toast with action button
3. Verify action button is present
4. Click action button
5. Verify action is executed (e.g., navigate to login)

**Expected Results:**
- Action buttons work in toasts
- Actions execute correctly
- Provides quick recovery path

### Test 16: Form Submission Error Toast

**Steps:**
1. Fill out a form (e.g., profile update)
2. Submit with valid client-side data but cause server error
3. **Screenshot:** Form error toast
4. Verify toast shows error
5. Verify form data is preserved (not cleared)
6. Verify user can correct and retry

**Expected Results:**
- Form submission errors shown via toast
- Form state preserved for retry
- User can fix and resubmit

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| Various | Various | Any endpoint that can return errors |

## Common Error Response Format

**400/422 Validation Error:**
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "Invalid email format",
      "type": "value_error"
    }
  ]
}
```

**401 Unauthorized:**
```json
{
  "detail": "Not authenticated"
}
```

**403 Forbidden:**
```json
{
  "detail": "Not enough permissions"
}
```

**500 Internal Error:**
```json
{
  "detail": "Internal server error"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Toast container | Toast container element (sonner or custom) |
| Error toast | Toast with error/destructive variant |
| Toast message | Text content within toast |
| Close button | `getByRole('button', { name: /close|dismiss/i })` |
| Action button | Button within toast (if present) |

## Success Criteria

- All API errors trigger toast notifications
- Error messages are user-friendly
- No technical details exposed to users
- Toasts have appropriate error styling
- Auto-dismiss works correctly
- Manual dismiss works correctly
- Multiple toasts stack properly
- Toasts are accessible
- Messages are translated
- Network errors handled distinctly

## Notes

- Use toast library consistently (sonner recommended)
- Consider error logging for debugging
- Verify error boundaries don't swallow toast-worthy errors
- Test with slow network (timeout errors)
- Consider retry functionality for transient errors
- Verify error deduplication (same error not shown multiple times)
- Test toast behavior during navigation
