# E2E Test: Notification Unsubscribe

## Test Description
Validate that users can unsubscribe from notifications via email link.

## User Story
As a user
I want to unsubscribe from notifications via email link
So that I can stop receiving unwanted notifications

## Prerequisites
- Backend server running
- Frontend dev server running
- Valid unsubscribe token generated
- User with active notifications

## Test Steps

### Test 1: Access Unsubscribe Page with Valid Token

**Steps:**
1. Generate valid unsubscribe token (via API or email link)
2. Navigate to `/unsubscribe?token={valid_token}`
3. **Screenshot:** Unsubscribe confirmation page
4. Verify page loads correctly
5. Verify displayed information:
   - User email
   - Organization name
   - Category name (if applicable)
   - Channel type

**Expected Results:**
- Page loads with token
- User info displayed
- Confirm/Cancel buttons shown

### Test 2: View Unsubscribe Details

**Steps:**
1. Access unsubscribe page with valid token
2. **Screenshot:** Unsubscribe details
3. Verify details shown:
   - What they're unsubscribing from
   - Email address affected
   - Channel type (Email/SMS/etc)
4. Verify clear explanation

**Expected Results:**
- Details clearly shown
- User understands action
- Channel specified

### Test 3: Confirm Unsubscribe

**Steps:**
1. Access unsubscribe page
2. Review the details
3. **Screenshot:** Before confirming
4. Click "Confirm" or "Unsubscribe" button
5. Wait for processing
6. **Screenshot:** Success page
7. Verify success message
8. Verify checkmark icon shown

**Expected Results:**
- Click processes unsubscribe
- Success page displayed
- Clear confirmation message

### Test 4: Cancel Unsubscribe

**Steps:**
1. Access unsubscribe page
2. Click "Cancel" button
3. **Screenshot:** After cancel
4. Verify navigation away or dialog closes
5. Verify no unsubscribe processed
6. User still subscribed

**Expected Results:**
- Cancel doesn't unsubscribe
- User remains subscribed
- Clean cancellation

### Test 5: Invalid Token - Error State

**Steps:**
1. Navigate to `/unsubscribe?token=invalid_token`
2. **Screenshot:** Error page
3. Verify error message displayed
4. Verify no user info shown
5. Verify helpful guidance

**Expected Results:**
- Invalid token shows error
- Clear error message
- No action possible

### Test 6: Missing Token - Error State

**Steps:**
1. Navigate to `/unsubscribe` (no token)
2. **Screenshot:** Missing token error
3. Verify error message
4. Verify guidance to login for preferences

**Expected Results:**
- Missing token shows error
- Link to login/preferences

### Test 7: Expired Token

**Steps:**
1. Navigate with expired token
2. **Screenshot:** Expired token error
3. Verify expiration message
4. Verify guidance to get new link

**Expected Results:**
- Expired token detected
- Clear expiration message
- Guidance provided

### Test 8: Already Unsubscribed

**Steps:**
1. Complete unsubscribe with token
2. Use same token again
3. Navigate to `/unsubscribe?token={used_token}`
4. **Screenshot:** Already unsubscribed
5. Verify message indicating already done
6. No error, just info

**Expected Results:**
- Already unsubscribed shown
- Friendly message
- No duplicate action

### Test 9: Loading State

**Steps:**
1. Navigate to unsubscribe page
2. **Screenshot:** Loading state
3. Observe loading spinner
4. Wait for data to load
5. Verify page content appears

**Expected Results:**
- Loading spinner shown
- Data loads
- Smooth transition

### Test 10: Unsubscribe from Specific Category

**Steps:**
1. Get token for category-specific unsubscribe
2. Navigate to unsubscribe page
3. **Screenshot:** Category unsubscribe
4. Verify category name shown
5. Confirm unsubscribe
6. Verify only that category unsubscribed

**Expected Results:**
- Category-specific unsubscribe
- Only affects one category
- Other notifications remain

### Test 11: Unsubscribe from All (Channel)

**Steps:**
1. Get token for full channel unsubscribe
2. Navigate to unsubscribe page
3. **Screenshot:** Full channel unsubscribe
4. Verify "all email notifications" or similar
5. Confirm unsubscribe
6. Verify all notifications for channel stopped

**Expected Results:**
- Full channel unsubscribe
- All notifications affected
- Clear indication of scope

### Test 12: Link to Manage Preferences

**Steps:**
1. View unsubscribe success page
2. **Screenshot:** Link to preferences
3. Verify link to login/manage preferences
4. Click link
5. Verify navigation to login or preferences

**Expected Results:**
- Link to manage preferences
- Can access full settings
- Alternative to email links

### Test 13: Mobile Responsiveness

**Steps:**
1. Access unsubscribe page on mobile
2. **Screenshot:** Mobile view
3. Verify page displays correctly
4. Verify buttons are touch-friendly
5. Complete unsubscribe on mobile

**Expected Results:**
- Mobile-friendly layout
- Buttons accessible
- Works on mobile

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/unsubscribe?token={token}` | Get unsubscribe info |
| POST | `/notifications/unsubscribe` | Process unsubscribe |

## Request/Response Format

**Get Unsubscribe Info Response:**
```json
{
  "email": "user@example.com",
  "organization_name": "Acme Corp",
  "category_name": "Marketing Updates",
  "channel": "email",
  "is_already_unsubscribed": false
}
```

**Process Unsubscribe Request:**
```json
{
  "token": "valid-unsubscribe-token"
}
```

**Process Unsubscribe Response:**
```json
{
  "message": "Successfully unsubscribed",
  "email": "user@example.com",
  "category": "Marketing Updates"
}
```

**Error Response (Invalid Token):**
```json
{
  "detail": "Invalid or expired unsubscribe token"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Unsubscribe page | Page component |
| User email display | Text showing email |
| Organization name | Text showing org name |
| Category name | Text showing category |
| Channel type | Text showing channel |
| Confirm button | `getByRole('button', { name: /confirm|unsubscribe/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Success checkmark | Checkmark icon |
| Success message | Success text content |
| Error message | Error text content |
| Loading spinner | Spinner animation |
| Preferences link | Link to manage preferences |

## Success Criteria

- Valid token loads unsubscribe page
- User info displayed correctly
- Confirm completes unsubscribe
- Cancel preserves subscription
- Invalid token shows error
- Missing token shows error
- Expired token handled
- Already unsubscribed handled
- Category-specific works
- Full channel works
- Link to preferences available
- Mobile responsive

## Notes

- Test token expiration time
- Verify unsubscribe affects notifications
- Check email footer link generation
- Verify i18n for all messages
- Test with different category types
- Verify audit logging of unsubscribes
- Check GDPR compliance aspects
