# E2E Test: Bulk Notifications

## Test Description
Validate that administrators can create and manage bulk notification campaigns.

## User Story
As an administrator
I want to send notifications to multiple users at once
So that I can efficiently communicate with my organization

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with notification permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- Multiple users exist in the organization
- Notification templates exist
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Bulk Notifications Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/notifications/bulk`
3. **Screenshot:** Bulk notifications page
4. Verify page loads correctly
5. Verify campaign list visible
6. Verify "Create Campaign" button

**Expected Results:**
- Page loads successfully
- Campaign table displayed
- Create button visible

### Test 2: View Campaign List

**Steps:**
1. Navigate to bulk notifications page
2. **Screenshot:** Campaign list
3. Verify table columns:
   - Campaign Name
   - Channel
   - Status
   - Progress
   - Created Date
   - Actions
4. Verify existing campaigns shown

**Expected Results:**
- All columns present
- Campaign data displayed
- Status badges visible

### Test 3: Create New Campaign - Open Dialog

**Steps:**
1. Click "Create Campaign" button
2. **Screenshot:** Create campaign dialog
3. Verify dialog opens
4. Verify form fields:
   - Campaign Name
   - Channel
   - Content Source (Template/Custom)
   - Recipients selection

**Expected Results:**
- Dialog opens
- Form fields visible
- Can configure campaign

### Test 4: Create Campaign with Template

**Steps:**
1. Open create campaign dialog
2. Enter name: "Monthly Update"
3. Select channel: Email
4. Select content source: Template
5. Select template from dropdown
6. **Screenshot:** Campaign with template
7. Click "Create" button
8. Wait for response
9. **Screenshot:** Campaign created

**Expected Results:**
- Template selection works
- Campaign created successfully
- Appears in list

### Test 5: Create Campaign with Custom Content

**Steps:**
1. Open create campaign dialog
2. Enter name: "Custom Announcement"
3. Select channel: In-App
4. Select content source: Custom
5. Enter subject: "Important Update"
6. Enter message content
7. **Screenshot:** Custom content campaign
8. Click "Create"
9. Verify success

**Expected Results:**
- Custom content form works
- Campaign created
- Content saved correctly

### Test 6: Campaign Status Badges

**Steps:**
1. View campaign list with various statuses
2. **Screenshot:** Status badges
3. Verify status colors:
   - Pending: Blue/neutral
   - Processing: Yellow/amber
   - Completed: Green
   - Failed: Red
   - Cancelled: Gray
4. Verify badge text matches status

**Expected Results:**
- Status badges colored correctly
- Clear visual distinction
- Text accurate

### Test 7: Campaign Progress Display

**Steps:**
1. Find a processing or completed campaign
2. **Screenshot:** Progress bar
3. Verify progress bar shows:
   - Sent count
   - Failed count
   - Total percentage
4. Verify bar visual matches numbers

**Expected Results:**
- Progress bar displayed
- Counts accurate
- Visual matches data

### Test 8: Cancel Pending Campaign

**Steps:**
1. Find a pending campaign
2. Click actions dropdown
3. **Screenshot:** Cancel option
4. Click "Cancel" option
5. Verify confirmation dialog
6. Confirm cancellation
7. **Screenshot:** Campaign cancelled
8. Verify status changed to "Cancelled"

**Expected Results:**
- Cancel option available for pending
- Confirmation required
- Status updates to cancelled

### Test 9: Cannot Cancel Completed Campaign

**Steps:**
1. Find a completed campaign
2. Click actions dropdown
3. **Screenshot:** Actions for completed
4. Verify Cancel option:
   - Not present, OR
   - Disabled
5. Note available actions

**Expected Results:**
- Cannot cancel completed
- Appropriate restrictions

### Test 10: Email Verified Filter

**Steps:**
1. Open create campaign dialog
2. Select Email channel
3. **Screenshot:** Email verified checkbox
4. Verify "Email verified only" checkbox
5. Enable the checkbox
6. Create campaign
7. Verify only verified users targeted

**Expected Results:**
- Filter option available
- Restricts to verified users

### Test 11: Campaign Creation Validation

**Steps:**
1. Open create dialog
2. Leave name empty
3. Click Create
4. **Screenshot:** Validation error
5. Verify error message
6. Fill name, skip content
7. Verify content required

**Expected Results:**
- Name required
- Content/template required
- Clear validation errors

### Test 12: Campaign Progress Updates

**Steps:**
1. Create a bulk campaign
2. Watch progress in list
3. **Screenshot:** Progress updating
4. Verify progress increments
5. Verify completion state

**Expected Results:**
- Progress updates (may need polling)
- Completion shown
- Final counts accurate

### Test 13: View Campaign Details

**Steps:**
1. Find a campaign in list
2. Click to view details (if available)
3. **Screenshot:** Campaign details
4. Verify details shown:
   - Full campaign info
   - Recipient count
   - Success/failure breakdown

**Expected Results:**
- Details accessible
- Full information shown

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/bulk` | List bulk campaigns |
| POST | `/notifications/bulk` | Create bulk campaign |
| GET | `/notifications/bulk/{id}` | Get campaign details |
| POST | `/notifications/bulk/{id}/cancel` | Cancel campaign |

## Request/Response Format

**Create Bulk Campaign Request:**
```json
{
  "name": "Monthly Update",
  "channel": "email",
  "template_id": "template-uuid",
  "verified_contact_only": true
}
```

**Create with Custom Content:**
```json
{
  "name": "Custom Announcement",
  "channel": "in_app",
  "subject": "Important Update",
  "content": "Message content here",
  "template_id": null
}
```

**Campaign Response:**
```json
{
  "id": "campaign-uuid",
  "name": "Monthly Update",
  "channel": "email",
  "status": "pending",
  "total_recipients": 100,
  "sent_count": 0,
  "failed_count": 0,
  "created_time": "2024-01-21T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create Campaign button | `getByRole('button', { name: /create campaign/i })` |
| Campaign table | DataTable component |
| Campaign name | Text in name column |
| Channel badge | Badge in channel column |
| Status badge | Badge in status column |
| Progress bar | Progress component in progress column |
| Actions dropdown | DropdownMenu trigger |
| Cancel option | `getByRole('menuitem', { name: /cancel/i })` |
| Create dialog | Dialog component |
| Name input | `getByLabelText(/name/i)` |
| Channel select | Select for channel |
| Content source toggle | Toggle between template/custom |
| Template select | Select for template |
| Subject input | `getByLabelText(/subject/i)` |
| Message textarea | Textarea for content |
| Email verified checkbox | Checkbox for verified filter |
| Submit button | `getByRole('button', { name: /create/i })` |
| Confirmation dialog | ConfirmDialog component |

## Success Criteria

- Campaign list displays correctly
- Create dialog opens with form
- Template and custom content work
- Status badges show correct colors
- Progress displays accurately
- Can cancel pending campaigns
- Cannot cancel completed campaigns
- Email verified filter works
- Validation prevents invalid campaigns
- Progress updates shown

## Notes

- Verify progress polling or WebSocket updates
- Test with large recipient lists
- Check cancellation timing (before processing starts)
- Verify template variable support
- Test retry for failed campaigns (if supported)
- Verify i18n for all text
