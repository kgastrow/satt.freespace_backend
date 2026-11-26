# E2E Test: Announcements Management

## Test Description
Validate that administrators can create, edit, and delete system announcements with scheduling, priority levels, and customization options.

## User Story
As an administrator
I want to manage system announcements
So that I can communicate important information to users across the platform

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with announcement management permissions

## Test Steps

### Test 1: Access Announcements Page

**Steps:**
1. Login as admin user
2. Navigate to announcements page (e.g., `/admin/announcements`)
3. **Screenshot:** Announcements page loaded
4. Verify page title "Announcements" or similar
5. Verify announcements table is displayed
6. Verify "Create" button is present
7. Verify table columns: title, priority, scope, dismissible, created, actions

**Expected Results:**
- Admin can access announcements management
- Announcements fetched from `GET /announcements`
- Table displays all announcements
- Create button is visible

### Test 2: Create Basic Announcement

**Steps:**
1. Navigate to announcements page
2. Click "Create" button
3. **Screenshot:** Create announcement dialog/form
4. Fill in details:
   - Title: "System Update Notice"
   - Body: "We will be updating the system this weekend."
   - Priority: "Normal"
   - Dismissible: Yes (toggle on)
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new announcement appears in table
11. Verify priority badge shows "Normal"

**Expected Results:**
- Create dialog opens with form fields
- Announcement created via `POST /announcements`
- Success notification displayed
- Announcement appears in table

### Test 3: Create High Priority Announcement

**Steps:**
1. Click "Create" button
2. Fill in details:
   - Title: "Critical Security Update"
   - Body: "Please update your password immediately."
   - Priority: "Critical" or "High"
3. **Screenshot:** High priority selected
4. Save announcement
5. Verify priority badge shows appropriate color (red for critical)
6. **Screenshot:** Priority badge in table

**Expected Results:**
- Priority levels: critical, high, normal, low
- Critical/high priorities have distinct styling
- Badge colors indicate priority

### Test 4: Create Announcement with Custom Styling

**Steps:**
1. Click "Create" button
2. Fill in title and body
3. Expand styling options (if collapsed)
4. Set background color: #FFF3CD (yellow)
5. Set text color: #856404 (dark brown)
6. **Screenshot:** Custom colors selected
7. View preview (if available)
8. **Screenshot:** Announcement preview with colors
9. Save announcement
10. Verify announcement displays with custom colors

**Expected Results:**
- Color pickers work correctly
- Preview shows custom styling
- Saved announcement uses custom colors
- Colors are accessible (contrast)

### Test 5: Create Announcement with Featured Image

**Steps:**
1. Click "Create" button
2. Fill in title and body
3. Click "Upload Image" or add featured image URL
4. Upload or enter image URL
5. **Screenshot:** Featured image added
6. View preview
7. Verify image appears in preview
8. Save announcement
9. **Screenshot:** Announcement with image in table/display

**Expected Results:**
- Image upload or URL entry works
- Preview shows featured image
- Image displays with announcement

### Test 6: Create Announcement with CTA Button

**Steps:**
1. Click "Create" button
2. Fill in title and body
3. Locate CTA (Call to Action) button configuration
4. Add CTA button:
   - Button text: "Learn More"
   - Button URL: "https://example.com/update-info"
5. **Screenshot:** CTA button configured
6. View preview
7. Verify button appears in preview
8. Save announcement
9. Click the CTA button (in preview or live)
10. Verify it navigates to the configured URL

**Expected Results:**
- CTA button can be added
- Button text and URL are customizable
- Button appears in announcement
- Click navigates to correct URL

### Test 7: Schedule Announcement

**Steps:**
1. Click "Create" button
2. Fill in title and body
3. Set start time: 1 hour from now
4. Set end time: 24 hours from now
5. **Screenshot:** Scheduled times set
6. Save announcement
7. Verify announcement is saved but not visible to users yet
8. Verify status shows "Scheduled"
9. Wait for start time (or adjust for testing)
10. Verify announcement becomes visible

**Expected Results:**
- Scheduling options available
- Announcements respect start/end times
- Status indicates scheduled vs active
- Auto-show at start time

### Test 8: Platform-wide vs Organization Announcement

**Steps:**
1. Click "Create" button
2. Fill in title and body
3. Toggle "Platform Wide" option
4. **Screenshot:** Platform wide selected
5. Save announcement
6. Verify scope column shows "Platform" badge
7. Create another announcement
8. Leave "Platform Wide" off (organization-scoped)
9. Save and verify scope shows "Organization"

**Expected Results:**
- Scope option works correctly
- Platform-wide reaches all organizations
- Organization scope limits visibility
- Scope badge displayed in table

### Test 9: Edit Announcement

**Steps:**
1. Navigate to announcements page
2. Find an existing announcement
3. Click "Edit" action button
4. **Screenshot:** Edit dialog with pre-filled data
5. Verify form is pre-filled with existing data
6. Modify title: "Updated Announcement Title"
7. Change priority level
8. **Screenshot:** Modified form
9. Click "Save" button
10. Verify success notification
11. Verify table shows updated data

**Expected Results:**
- Edit dialog opens with existing data
- All fields are editable
- Changes saved via `PUT /announcements/{id}`
- Table reflects updates

### Test 10: Delete Announcement

**Steps:**
1. Navigate to announcements page
2. Find an announcement to delete
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation shows announcement title
6. Click "Confirm Delete"
7. Verify success notification
8. **Screenshot:** After deletion
9. Verify announcement removed from table

**Expected Results:**
- Delete requires confirmation
- Announcement deleted via `DELETE /announcements/{id}`
- Success notification shown
- Announcement removed from list

### Test 11: Dismissible Announcement Behavior

**Steps:**
1. Create announcement with dismissible: true
2. View announcement as regular user
3. **Screenshot:** Announcement with dismiss button
4. Verify dismiss/close button is present
5. Click dismiss button
6. Verify announcement is hidden
7. Refresh page
8. Verify announcement stays dismissed
9. Create non-dismissible announcement
10. Verify no dismiss button present

**Expected Results:**
- Dismissible announcements have close button
- Dismissed state persists (localStorage or API)
- Non-dismissible announcements cannot be closed

### Test 12: Announcement Preview

**Steps:**
1. Click "Create" button
2. Fill in all fields including styling
3. Locate preview section
4. **Screenshot:** Full announcement preview
5. Verify preview shows:
   - Title with styling
   - Body content
   - Featured image (if added)
   - CTA button (if added)
   - Custom colors
6. Make changes to form
7. Verify preview updates in real-time

**Expected Results:**
- Preview accurately represents final announcement
- Real-time updates as form changes
- All elements visible in preview

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/announcements` | List all announcements |
| POST | `/announcements` | Create new announcement |
| PUT | `/announcements/{id}` | Update announcement |
| DELETE | `/announcements/{id}` | Delete announcement |

## Request/Response Format

**Create Announcement Request:**
```json
{
  "title": "System Update Notice",
  "body": "We will be updating the system this weekend.",
  "priority": "normal",
  "dismissible": true,
  "platform_wide": false,
  "background_color": "#FFF3CD",
  "text_color": "#856404",
  "featured_image_url": "https://example.com/image.jpg",
  "cta_button": {
    "text": "Learn More",
    "url": "https://example.com/update-info"
  },
  "start_time": "2024-01-15T10:00:00Z",
  "end_time": "2024-01-16T10:00:00Z"
}
```

**Announcement Response:**
```json
{
  "id": "uuid",
  "title": "System Update Notice",
  "body": "We will be updating the system this weekend.",
  "priority": "normal",
  "dismissible": true,
  "platform_wide": false,
  "background_color": "#FFF3CD",
  "text_color": "#856404",
  "featured_image_url": "https://example.com/image.jpg",
  "cta_button": {
    "text": "Learn More",
    "url": "https://example.com/update-info"
  },
  "start_time": "2024-01-15T10:00:00Z",
  "end_time": "2024-01-16T10:00:00Z",
  "created_at": "2024-01-14T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add/i })` |
| Announcements table | Table with announcement rows |
| Title input | `getByLabelText(/title/i)` |
| Body textarea | `getByLabelText(/body|content|message/i)` |
| Priority select | `getByLabelText(/priority/i)` |
| Dismissible toggle | `getByRole('switch', { name: /dismissible/i })` |
| Platform wide toggle | `getByRole('switch', { name: /platform/i })` |
| Background color picker | Color picker input |
| Start time input | Date/time picker for start |
| End time input | Date/time picker for end |
| CTA button text | `getByLabelText(/button text/i)` |
| CTA button URL | `getByLabelText(/button url/i)` |
| Preview section | Preview card/container |
| Priority badge | Badge with priority level |

## Success Criteria

- CRUD operations work correctly
- Priority levels display with correct styling
- Custom colors apply to announcements
- Featured images display correctly
- CTA buttons work with correct links
- Scheduling respects start/end times
- Platform-wide scope works correctly
- Dismissible behavior functions properly
- Preview accurately reflects announcement

## Notes

- Verify real-time announcement delivery (WebSocket)
- Test with multiple active announcements (stacking)
- Verify announcement ordering (by priority/date)
- Test color accessibility (contrast ratios)
- Verify i18n translations
- Test on mobile devices
