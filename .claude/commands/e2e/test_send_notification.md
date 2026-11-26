# E2E Test: Send Notification (Admin)

## Test Description
Validate that administrators can send notifications to individual users.

## User Story
As an administrator
I want to send notifications to users
So that I can communicate important information

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with notification permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- Target users exist in the system
- Notification templates exist
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Send Notification Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/notifications/send`
3. **Screenshot:** Send notification page
4. Verify page loads correctly
5. Verify form fields visible

**Expected Results:**
- Page loads successfully
- Form displayed
- All fields visible

### Test 2: Select Channel

**Steps:**
1. Navigate to send notification page
2. **Screenshot:** Channel selector
3. Verify channel options:
   - Email
   - SMS
   - WhatsApp
   - In-App
4. Select "Email" channel
5. Verify form updates for email

**Expected Results:**
- All channels available
- Selection updates form
- Channel-specific fields shown

### Test 3: Select Recipient

**Steps:**
1. Locate user/recipient selector
2. **Screenshot:** Recipient combobox
3. Type to search for user
4. **Screenshot:** User search results
5. Select a user from dropdown
6. Verify user selected

**Expected Results:**
- User search works
- Users listed in dropdown
- Selection shown

### Test 4: Send with Custom Content

**Steps:**
1. Select channel: Email
2. Select recipient
3. Toggle content source to "Custom Content"
4. Enter subject: "Test Notification"
5. Enter message: "This is a test notification"
6. **Screenshot:** Custom content filled
7. Click "Send" button
8. Wait for response
9. **Screenshot:** Success state
10. Verify success notification

**Expected Results:**
- Custom content form works
- Email sends successfully
- Success feedback shown

### Test 5: Send with Template

**Steps:**
1. Select channel: Email
2. Select recipient
3. Toggle content source to "Use Template"
4. **Screenshot:** Template selector
5. Select a template from dropdown
6. **Screenshot:** Template selected
7. Verify template info shown
8. Click "Send" button
9. Verify success

**Expected Results:**
- Template selection works
- Template content used
- Notification sends

### Test 6: Email Channel - Subject Field

**Steps:**
1. Select channel: Email
2. Verify "Subject" field appears
3. Enter subject
4. **Screenshot:** Subject field
5. Toggle to SMS channel
6. Verify Subject field hidden

**Expected Results:**
- Subject shown for Email
- Hidden for SMS/WhatsApp

### Test 7: In-App Channel - Title Field

**Steps:**
1. Select channel: In-App
2. Verify "Title" field appears
3. Enter title
4. Enter message
5. **Screenshot:** In-App form
6. Send notification
7. Verify success

**Expected Results:**
- Title field for In-App
- Notification creates correctly

### Test 8: SMS Channel Validation

**Steps:**
1. Select channel: SMS
2. Verify message length indicator
3. Enter very long message
4. **Screenshot:** Length warning/limit
5. Verify character limit enforced or warned

**Expected Results:**
- SMS has length considerations
- User warned about limits

### Test 9: Set Urgent Flag

**Steps:**
1. Fill out notification form
2. Toggle "Urgent" flag
3. **Screenshot:** Urgent flag enabled
4. Send notification
5. Verify urgent notification sent

**Expected Results:**
- Urgent flag available
- Affects notification priority

### Test 10: Validation - Missing Required Fields

**Steps:**
1. Leave recipient empty
2. Click Send
3. **Screenshot:** Validation error
4. Verify error message
5. Fill recipient, leave message empty
6. Verify message required
7. Fill all required
8. Verify can send

**Expected Results:**
- Recipient required
- Message/content required
- Clear validation errors

### Test 11: Loading State During Send

**Steps:**
1. Fill out form completely
2. Click Send button
3. **Screenshot:** Loading state
4. Verify button shows loading
5. Verify form disabled
6. Wait for completion

**Expected Results:**
- Loading indicator shown
- Prevents double submission
- Form disabled during send

### Test 12: Navigate Back After Send

**Steps:**
1. Send notification successfully
2. Verify navigation to notifications list
3. **Screenshot:** Notifications page
4. Verify can send another

**Expected Results:**
- Navigates after send
- Can send more
- Form resets

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/notifications/send` | Send notification to user |
| GET | `/notifications/templates` | List available templates |
| GET | `/users` | Search/list users for recipient |

## Request/Response Format

**Send Notification Request:**
```json
{
  "channel": "email",
  "user_id": "user-uuid",
  "subject": "Test Notification",
  "content": "This is a test notification",
  "template_id": null,
  "is_urgent": false
}
```

**Send with Template Request:**
```json
{
  "channel": "email",
  "user_id": "user-uuid",
  "template_id": "template-uuid",
  "template_variables": {
    "name": "John"
  }
}
```

**Send Response:**
```json
{
  "message": "Notification sent successfully",
  "notification_id": "notif-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Channel selector | Select component for channel |
| Email option | `getByRole('option', { name: /email/i })` |
| Recipient combobox | Combobox for user selection |
| Template toggle | Toggle between template/custom |
| Template selector | Select component for template |
| Subject input | `getByLabelText(/subject/i)` |
| Title input | `getByLabelText(/title/i)` |
| Message textarea | `getByLabelText(/message|content/i)` |
| Urgent toggle | Switch for urgent flag |
| Send button | `getByRole('button', { name: /send/i })` |
| Validation error | Error message components |
| Loading indicator | Spinner on send button |

## Success Criteria

- All channels available
- Recipient selection works
- Custom content can be entered
- Templates can be selected
- Channel-specific fields shown
- Urgent flag available
- Validation prevents invalid sends
- Loading state during send
- Success feedback shown
- Navigation after send

## Notes

- Verify template filtering by channel
- Test with all channel types
- Check template variable substitution
- Verify user search performance
- Test with organization-wide send (if supported)
- Verify i18n for all labels
