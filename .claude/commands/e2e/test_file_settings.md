# E2E Test: File Settings

## Test Description
Validate that organization admins can configure file upload limits, allowed types, and storage quotas.

## User Story
As an organization admin
I want to configure file settings
So that I can control upload limits and storage for my organization

## Prerequisites
- Backend server running
- Frontend dev server running
- Organization admin with file settings permissions:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
  - Permissions: file_settings:read, file_settings:write
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to File Settings

**Steps:**
1. Log in as organization admin
2. Navigate to `/admin/files/settings`
3. Wait for page to load
4. **Screenshot:** File settings page
5. Verify page header shows settings title
6. Verify settings cards displayed

**Expected Results:**
- Settings page loads
- Cards show current settings
- All sections visible

### Test 2: View Current Settings

**Steps:**
1. Navigate to file settings page
2. **Screenshot:** All settings sections
3. Verify displayed settings:
   - Size Limits card
   - Allowed File Types card
   - Storage Quotas card
   - URL & Retention Settings card
4. Verify current values populated

**Expected Results:**
- All settings sections visible
- Current values displayed
- Forms pre-populated

### Test 3: Update Max File Size

**Steps:**
1. Navigate to file settings
2. Locate Size Limits card
3. Find "Max File Size" input
4. Note current value
5. Change value to: 50 (MB)
6. **Screenshot:** Updated file size
7. Click Save button
8. Verify success notification
9. Refresh page
10. Verify value persisted

**Expected Results:**
- Can edit max file size
- Value saves successfully
- Setting persists

### Test 4: Update Max Video Size

**Steps:**
1. Locate "Max Video Size" input
2. Note current value
3. Change value to: 500 (MB)
4. **Screenshot:** Updated video size
5. Click Save button
6. Verify success notification
7. Verify value saved

**Expected Results:**
- Video size separate from file size
- Can set larger limit for videos
- Setting saves correctly

### Test 5: Validation - Size Limits

**Steps:**
1. Enter invalid max file size: 0
2. Click Save
3. **Screenshot:** Validation error
4. Verify error message
5. Enter value exceeding max: 2000 (MB)
6. Verify validation error
7. Enter valid value: 100
8. Verify can save

**Expected Results:**
- Minimum size enforced (1 MB)
- Maximum size enforced (1024 MB for files)
- Clear error messages

### Test 6: Update Allowed File Types

**Steps:**
1. Locate Allowed File Types card
2. **Screenshot:** Current allowed types
3. Add new extension: "csv"
4. **Screenshot:** Extension added
5. Remove an existing extension
6. **Screenshot:** Extension removed
7. Click Save button
8. Verify success notification
9. Verify changes persisted

**Expected Results:**
- Can add extensions via TagInput
- Can remove extensions
- Changes save correctly

### Test 7: Update User Storage Quota

**Steps:**
1. Locate Storage Quotas card
2. Find "User Storage Quota" input
3. Enter value: 10 (GB)
4. **Screenshot:** User quota set
5. Click Save button
6. Verify success notification
7. Verify value saved

**Expected Results:**
- User quota can be set
- GB to bytes conversion works
- Setting saves correctly

### Test 8: Update Organization Storage Quota

**Steps:**
1. Find "Organization Storage Quota" input
2. Enter value: 100 (GB)
3. **Screenshot:** Org quota set
4. Click Save button
5. Verify success notification
6. Verify value saved

**Expected Results:**
- Org quota can be set
- Setting saves correctly
- Org-wide limit enforced

### Test 9: Set Unlimited Quota (Clear Field)

**Steps:**
1. Find User Storage Quota input
2. Clear the field (leave empty)
3. **Screenshot:** Empty quota field
4. Click Save button
5. Verify saves successfully
6. Verify displays as unlimited or null

**Expected Results:**
- Empty = unlimited quota
- No validation error
- Displays appropriately

### Test 10: Update Download URL Expiry

**Steps:**
1. Locate URL & Retention Settings card
2. Find "Download URL Expiry" input
3. Change value to: 3600 (seconds = 1 hour)
4. **Screenshot:** Updated expiry
5. Click Save button
6. Verify success notification

**Expected Results:**
- Can set URL expiry time
- Seconds input works
- Setting saves

### Test 11: Update Deleted File Retention

**Steps:**
1. Find "Deleted File Retention" input
2. Change value to: 60 (days)
3. **Screenshot:** Updated retention
4. Click Save button
5. Verify success notification
6. Verify setting controls soft delete period

**Expected Results:**
- Can set retention period
- Days input works
- Affects soft delete behavior

### Test 12: Validation - URL Expiry Limits

**Steps:**
1. Enter URL expiry: 30 (below minimum)
2. Click Save
3. **Screenshot:** Validation error
4. Verify minimum is 60 seconds
5. Enter expiry: 100000 (above max)
6. Verify maximum is 86400 (24 hours)
7. Enter valid value: 3600

**Expected Results:**
- Minimum 60 seconds enforced
- Maximum 86400 seconds enforced
- Clear validation errors

### Test 13: Cancel Changes

**Steps:**
1. Make changes to multiple settings
2. **Screenshot:** Modified settings
3. Click Cancel button (if present)
4. Or navigate away and return
5. Verify original values restored

**Expected Results:**
- Can cancel without saving
- Original values remain
- No partial updates

### Test 14: Loading State

**Steps:**
1. Navigate to file settings
2. **Screenshot:** Loading state
3. Verify loading indicator while fetching
4. Wait for data
5. Verify settings load correctly

**Expected Results:**
- Loading state shown
- Data loads correctly
- No empty form flash

### Test 15: Save Loading State

**Steps:**
1. Make a change to settings
2. Click Save button
3. **Screenshot:** Save loading state
4. Verify button shows loading indicator
5. Verify inputs disabled during save
6. Wait for completion

**Expected Results:**
- Loading indicator on save
- Prevents double submission
- Completes successfully

### Test 16: Permission Check

**Steps:**
1. Log in as user without file_settings permissions
2. Attempt to navigate to `/admin/files/settings`
3. **Screenshot:** Access denied
4. Verify redirect or error message
5. Verify cannot access settings page

**Expected Results:**
- Requires file_settings:read permission
- Requires file_settings:write to edit
- Proper access control

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/files/settings` | Get current file settings |
| PUT | `/files/settings` | Update file settings |

## Request/Response Format

**Get File Settings Response:**
```json
{
  "max_file_size_bytes": 104857600,
  "max_video_size_bytes": 1073741824,
  "allowed_extensions": ["jpg", "jpeg", "png", "gif", "pdf", "doc", "docx"],
  "user_storage_quota_bytes": 10737418240,
  "org_storage_quota_bytes": 107374182400,
  "signed_url_expiry_seconds": 3600,
  "deleted_file_retention_days": 30
}
```

**Update File Settings Request:**
```json
{
  "max_file_size_bytes": 52428800,
  "max_video_size_bytes": 524288000,
  "allowed_extensions": ["jpg", "jpeg", "png", "gif", "pdf", "doc", "docx", "csv"],
  "user_storage_quota_bytes": 10737418240,
  "org_storage_quota_bytes": 107374182400,
  "signed_url_expiry_seconds": 3600,
  "deleted_file_retention_days": 60
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading')` with settings title |
| Size Limits card | Card with size limit fields |
| Max file size input | `getByLabelText(/max file size/i)` |
| Max video size input | `getByLabelText(/max video size/i)` |
| Allowed types card | Card with file types section |
| Tag input | TagInput component for extensions |
| Storage quotas card | Card with quota fields |
| User quota input | `getByLabelText(/user.*quota/i)` |
| Org quota input | `getByLabelText(/organization.*quota/i)` |
| URL settings card | Card with URL and retention fields |
| URL expiry input | `getByLabelText(/expiry|download.*url/i)` |
| Retention input | `getByLabelText(/retention/i)` |
| Save button | `getByRole('button', { name: /save/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Validation error | FormMessage components |
| Loading indicator | Spinner or skeleton |

## Success Criteria

- All settings sections accessible
- Current values pre-populated
- Size limits can be updated with validation
- File types can be added/removed
- Storage quotas can be set or cleared
- URL expiry configurable within limits
- Retention period configurable
- Validation prevents invalid values
- Loading states shown during operations
- Permission-based access enforced

## Notes

- Verify changes affect actual upload behavior
- Test byte/GB/MB conversions
- Check allowed extensions update file type validation
- Verify quota enforcement on upload
- Verify i18n for all labels
- Test with organization without any settings (defaults)
