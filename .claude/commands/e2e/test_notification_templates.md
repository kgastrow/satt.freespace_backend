# E2E Test: Notification Templates

## Test Description
Validate that administrators can manage notification templates (create, edit, delete).

## User Story
As an administrator
I want to manage notification templates
So that I can create reusable notification content

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with notification permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Templates Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/notifications/templates`
3. **Screenshot:** Templates page
4. Verify page loads correctly
5. Verify templates table visible
6. Verify "Create Template" button

**Expected Results:**
- Page loads successfully
- Templates listed
- Create button visible

### Test 2: View Templates List

**Steps:**
1. Navigate to templates page
2. **Screenshot:** Templates table
3. Verify table columns:
   - Name
   - Code
   - Channel
   - Status (Active/Inactive)
   - Actions
4. Verify templates displayed

**Expected Results:**
- All columns present
- Template data shown
- Status badges visible

### Test 3: Filter Templates by Channel

**Steps:**
1. View templates list
2. Locate channel filter
3. **Screenshot:** Channel filter
4. Select "Email" filter
5. **Screenshot:** Email templates only
6. Verify only email templates shown
7. Select "All" to reset

**Expected Results:**
- Filter options visible
- Filtering works correctly
- Reset shows all

### Test 4: Create New Template - Open Form

**Steps:**
1. Click "Create Template" button
2. **Screenshot:** Create template form/dialog
3. Verify form fields:
   - Code (unique identifier)
   - Name
   - Description
   - Channel
   - Subject (email/in-app)
   - Body (text)
   - HTML Body (email)
   - Active toggle

**Expected Results:**
- Form opens
- All fields visible
- Can configure template

### Test 5: Create Email Template

**Steps:**
1. Open create template form
2. Enter code: "welcome_email"
3. Enter name: "Welcome Email"
4. Enter description: "Welcome new users"
5. Select channel: Email
6. Enter subject: "Welcome to {{org_name}}"
7. Enter body: "Hello {{user_name}}, welcome!"
8. **Screenshot:** Email template form
9. Click "Create" button
10. **Screenshot:** Template created
11. Verify success notification
12. Verify template in list

**Expected Results:**
- Template created successfully
- Appears in list
- All data saved

### Test 6: Create In-App Template

**Steps:**
1. Open create template form
2. Enter code: "system_alert"
3. Enter name: "System Alert"
4. Select channel: In-App
5. Enter subject/title: "System Alert"
6. Enter body: "{{message}}"
7. **Screenshot:** In-App template
8. Create template
9. Verify success

**Expected Results:**
- In-App template works
- Subject as title
- Template created

### Test 7: Create SMS Template

**Steps:**
1. Open create template form
2. Enter code: "sms_reminder"
3. Enter name: "SMS Reminder"
4. Select channel: SMS
5. Enter body: "Reminder: {{message}}"
6. **Screenshot:** SMS template (no subject)
7. Verify Subject field hidden for SMS
8. Create template

**Expected Results:**
- SMS doesn't have subject
- Body only required
- Template created

### Test 8: Template Variable Placeholders

**Steps:**
1. Create/edit template
2. Use variable: `{{user_name}}`
3. **Screenshot:** Variable in template
4. Verify variable syntax explained
5. Add multiple variables
6. Save template

**Expected Results:**
- Variables supported
- Syntax documented
- Variables saved

### Test 9: Edit Existing Template

**Steps:**
1. Find a template in list
2. Click actions dropdown
3. Click "Edit" option
4. **Screenshot:** Edit form with data
5. Verify form pre-filled
6. Change name: "Updated Name"
7. Change body content
8. **Screenshot:** Changes made
9. Click "Save"
10. Verify changes saved

**Expected Results:**
- Edit loads existing data
- Can modify fields
- Code not editable (immutable)
- Changes persist

### Test 10: Code Field Immutable on Edit

**Steps:**
1. Edit an existing template
2. **Screenshot:** Code field
3. Verify code field is:
   - Disabled, OR
   - Hidden, OR
   - Read-only
4. Attempt to change code
5. Verify code preserved

**Expected Results:**
- Code cannot be changed after creation
- Clear indication of immutability

### Test 11: Toggle Template Active/Inactive

**Steps:**
1. Find an active template
2. Edit or use quick action
3. Toggle Active to Inactive
4. **Screenshot:** Template inactive
5. Save changes
6. Verify status badge shows Inactive
7. Toggle back to Active

**Expected Results:**
- Active toggle works
- Status badge updates
- Setting persists

### Test 12: Delete Template

**Steps:**
1. Find a non-system template
2. Click actions dropdown
3. Click "Delete" option
4. **Screenshot:** Delete confirmation
5. Verify confirmation dialog
6. Confirm deletion
7. **Screenshot:** Template deleted
8. Verify template removed from list

**Expected Results:**
- Delete option available
- Confirmation required
- Template removed

### Test 13: Cannot Delete System Templates

**Steps:**
1. Find a system template (lock icon)
2. Click actions dropdown
3. **Screenshot:** System template actions
4. Verify Delete option:
   - Not present, OR
   - Disabled

**Expected Results:**
- System templates protected
- Cannot be deleted

### Test 14: Preview Template

**Steps:**
1. Find a template
2. Click "Preview" option (if available)
3. **Screenshot:** Template preview
4. Verify preview shows:
   - Subject
   - Body content
   - HTML rendering (for email)
5. Close preview

**Expected Results:**
- Preview shows template
- Variables shown as placeholders
- HTML rendered (if applicable)

### Test 15: Validation - Duplicate Code

**Steps:**
1. Create new template
2. Enter existing code
3. Fill other fields
4. Click Create
5. **Screenshot:** Duplicate code error
6. Verify error message
7. Enter unique code
8. Verify can create

**Expected Results:**
- Duplicate code rejected
- Clear error message
- Unique codes enforced

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/notifications/templates` | List templates |
| GET | `/notifications/templates/{id}` | Get template details |
| POST | `/notifications/templates` | Create template |
| PUT | `/notifications/templates/{id}` | Update template |
| DELETE | `/notifications/templates/{id}` | Delete template |

## Request/Response Format

**Create Template Request:**
```json
{
  "code": "welcome_email",
  "name": "Welcome Email",
  "description": "Welcome new users to the platform",
  "channel": "email",
  "subject": "Welcome to {{org_name}}",
  "body": "Hello {{user_name}}, welcome to our platform!",
  "html_body": "<h1>Welcome {{user_name}}</h1>",
  "is_active": true
}
```

**Template Response:**
```json
{
  "id": "template-uuid",
  "code": "welcome_email",
  "name": "Welcome Email",
  "description": "Welcome new users",
  "channel": "email",
  "subject": "Welcome to {{org_name}}",
  "body": "Hello {{user_name}}...",
  "html_body": "<h1>...</h1>",
  "is_active": true,
  "is_system": false,
  "created_time": "2024-01-21T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create Template button | `getByRole('button', { name: /create template/i })` |
| Templates table | DataTable component |
| Channel filter | Select/tabs for filtering |
| Template name | Text in name column |
| Code column | Text in code column |
| Channel badge | Badge in channel column |
| Status badge | Badge showing Active/Inactive |
| System indicator | Lock icon for system templates |
| Actions dropdown | DropdownMenu trigger |
| Edit option | `getByRole('menuitem', { name: /edit/i })` |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Preview option | `getByRole('menuitem', { name: /preview/i })` |
| Template form | Form component |
| Code input | `getByLabelText(/code/i)` |
| Name input | `getByLabelText(/name/i)` |
| Description textarea | `getByLabelText(/description/i)` |
| Channel select | Select for channel |
| Subject input | `getByLabelText(/subject/i)` |
| Body textarea | `getByLabelText(/body/i)` |
| HTML body textarea | Textarea for HTML content |
| Active toggle | Switch for active status |
| Submit button | `getByRole('button', { name: /save|create/i })` |
| Confirmation dialog | ConfirmDialog component |
| Preview dialog | Dialog for template preview |

## Success Criteria

- Templates list displays correctly
- Can filter by channel
- Create template form works
- All channel types supported
- Variable placeholders work
- Edit updates templates
- Code immutable after creation
- Active/Inactive toggle works
- Can delete non-system templates
- System templates protected
- Preview shows template content
- Validation prevents duplicates

## Notes

- Verify variable substitution works on send
- Test HTML email rendering
- Check template code uniqueness
- Verify i18n for all labels
- Test with organization-specific templates
- Check template versioning (if supported)
