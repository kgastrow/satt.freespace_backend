# E2E Test: Storage Usage

## Test Description
Validate that users can view their storage usage with visual indicators and quota information.

## User Story
As a user
I want to see my storage usage and quota
So that I can manage my files and avoid exceeding limits

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with uploaded files:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User has some storage used
- User has storage quota set (if applicable)
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Storage Card

**Steps:**
1. Navigate to `/files`
2. Wait for page to load
3. **Screenshot:** Storage usage card
4. Verify storage card visible
5. Verify card shows:
   - Total storage used (formatted)
   - Storage quota (if set)
   - Progress bar
6. Verify data loads correctly

**Expected Results:**
- Storage card displayed
- Usage amount formatted (KB, MB, GB)
- Progress bar visible

### Test 2: Storage Progress Bar - Low Usage

**Steps:**
1. Set up user with low storage usage (<75% of quota)
2. Navigate to `/files`
3. **Screenshot:** Low usage progress bar
4. Verify progress bar is green
5. Verify percentage matches usage

**Expected Results:**
- Green progress bar for low usage
- Accurate percentage

### Test 3: Storage Progress Bar - Medium Usage

**Steps:**
1. Set up user with medium usage (75-90% of quota)
2. Navigate to `/files`
3. **Screenshot:** Medium usage progress bar
4. Verify progress bar is yellow/amber
5. Verify warning color indicates approaching limit

**Expected Results:**
- Yellow/amber bar for medium usage
- Visual warning of approaching limit

### Test 4: Storage Progress Bar - High Usage

**Steps:**
1. Set up user with high usage (>90% of quota)
2. Navigate to `/files`
3. **Screenshot:** High usage progress bar
4. Verify progress bar is red
5. Verify critical color indicates near limit

**Expected Results:**
- Red bar for high usage
- Critical warning visual

### Test 5: Storage Without Quota

**Steps:**
1. Set up user with no quota limit
2. Navigate to `/files`
3. **Screenshot:** Storage without quota
4. Verify usage amount shown
5. Verify appropriate indicator (no percentage, or unlimited)
6. Verify progress bar color (blue or neutral)

**Expected Results:**
- Usage shown even without quota
- No percentage (or "unlimited")
- Appropriate visual style

### Test 6: Category Breakdown

**Steps:**
1. Navigate to `/files`
2. Locate storage card
3. **Screenshot:** Category breakdown
4. Verify category badges showing:
   - Images count
   - Videos count
   - Documents count
   - Other count
5. Verify counts are accurate

**Expected Results:**
- Category badges displayed
- Counts match actual files
- All categories shown

### Test 7: Storage Updates After Upload

**Steps:**
1. Note current storage usage
2. Note file size of file to upload
3. Upload a new file
4. Wait for upload complete
5. **Screenshot:** Updated storage
6. Verify storage increased
7. Verify increase matches file size
8. Verify category count updated

**Expected Results:**
- Storage updates after upload
- Correct amount added
- Category count incremented

### Test 8: Storage Updates After Delete

**Steps:**
1. Note current storage usage
2. Note file size of file to delete
3. Delete a file
4. Wait for deletion
5. **Screenshot:** Updated storage
6. Verify storage decreased
7. Verify decrease matches file size
8. Verify category count updated

**Expected Results:**
- Storage updates after delete
- Correct amount freed
- Category count decremented

### Test 9: Admin Storage Stats

**Steps:**
1. Log in as organization admin
2. Navigate to `/admin/files`
3. **Screenshot:** Admin storage stats
4. Verify admin cards show:
   - Total files (count and user count)
   - Storage used (with org quota)
   - Quota usage percentage
5. Verify organization-wide stats

**Expected Results:**
- Admin sees org-wide stats
- Total files and users shown
- Organization quota displayed

### Test 10: Storage Loading State

**Steps:**
1. Navigate to `/files`
2. **Screenshot:** Loading state
3. Observe loading indicator for storage card
4. Wait for data to load
5. Verify smooth transition to data

**Expected Results:**
- Loading state shown
- Smooth transition
- Data displays correctly

### Test 11: Storage Quota Warning

**Steps:**
1. Approach storage quota (90%+ usage)
2. Navigate to `/files`
3. **Screenshot:** Quota warning
4. Verify warning message or visual indicator
5. Attempt to upload additional file
6. Verify warning about quota

**Expected Results:**
- Visual warning at high usage
- Upload warning if near limit
- Clear indication of quota status

### Test 12: Formatted Byte Display

**Steps:**
1. Navigate to `/files` with various usage levels
2. **Screenshot:** Byte formatting
3. Verify bytes formatted correctly:
   - Small files: KB
   - Medium files: MB
   - Large usage: GB
4. Verify decimal places appropriate

**Expected Results:**
- Human-readable formatting
- Appropriate units used
- Consistent formatting

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/files/usage` | Get user storage usage |
| GET | `/files/usage/organization` | Get org storage usage (admin) |

## Request/Response Format

**User Storage Usage Response:**
```json
{
  "total_size_bytes": 52428800,
  "total_files": 25,
  "image_count": 10,
  "video_count": 5,
  "document_count": 8,
  "other_count": 2,
  "user_quota_bytes": 104857600
}
```

**Organization Storage Usage Response:**
```json
{
  "total_files": 500,
  "user_count": 20,
  "total_size_bytes": 5368709120,
  "org_quota_bytes": 10737418240,
  "org_quota_used_percent": 50.0
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Storage card | Card component with storage info |
| Storage title | `getByText(/storage/i)` within card |
| Usage amount | Text showing formatted bytes |
| Quota amount | Text showing quota limit |
| Progress bar | Progress component |
| Percentage text | Text showing percent used |
| Category badges | Badge components for categories |
| Images count | Badge with image count |
| Videos count | Badge with video count |
| Documents count | Badge with document count |
| Other count | Badge with other count |
| Admin total files card | Card with total files stat |
| Admin storage card | Card with org storage stat |

## Success Criteria

- Storage usage displayed accurately
- Progress bar colors indicate usage level
- Category breakdown shows file counts
- Storage updates on upload/delete
- Quota shown when set
- No-quota state handled
- Admin sees organization stats
- Loading state shown during fetch
- Byte formatting is readable

## Notes

- Verify quota enforcement on upload attempt
- Test with various quota levels
- Check formatting of very large numbers
- Verify i18n for labels
- Test refresh updates data
- Check mobile display of storage card
