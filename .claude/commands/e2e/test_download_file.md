# E2E Test: Download File

## Test Description
Validate that users can download their files via presigned URLs.

## User Story
As a user
I want to download my uploaded files
So that I can access them on my local device

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with uploaded files:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- At least one downloadable file exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Download from Grid View

**Steps:**
1. Navigate to `/files`
2. Verify files displayed in grid view
3. Find a file to download
4. Click actions dropdown (three dots)
5. **Screenshot:** Download option in dropdown
6. Click "Download" option
7. **Screenshot:** Download initiated
8. Verify file download starts
9. Verify no errors displayed

**Expected Results:**
- Download option in dropdown
- Click triggers download
- File downloads to device

### Test 2: Download from List View

**Steps:**
1. Navigate to `/files`
2. Switch to list view
3. Find a file to download
4. Click actions dropdown for that row
5. **Screenshot:** List view download option
6. Click "Download" option
7. Verify download starts

**Expected Results:**
- Download works in list view
- Same behavior as grid view

### Test 3: Download Image File

**Steps:**
1. Navigate to `/files`
2. Find an image file (.jpg, .png)
3. Initiate download
4. **Screenshot:** Image download
5. Verify correct filename downloaded
6. Verify file is valid image

**Expected Results:**
- Image downloads correctly
- Correct filename preserved
- File is valid

### Test 4: Download Document File

**Steps:**
1. Find a document file (.pdf, .docx)
2. Initiate download
3. **Screenshot:** Document download
4. Verify correct file downloaded
5. Verify file opens correctly

**Expected Results:**
- Documents download correctly
- File integrity preserved

### Test 5: Download Video File

**Steps:**
1. Find a video file (.mp4, .mov)
2. Initiate download
3. **Screenshot:** Video download initiated
4. Wait for download (may take longer)
5. Verify file downloaded

**Expected Results:**
- Video downloads correctly
- Larger file handled properly

### Test 6: Download URL Generation

**Steps:**
1. Find a file to download
2. Open browser developer tools (Network tab)
3. Initiate download
4. **Screenshot:** Network request
5. Verify API call to get download URL
6. Verify presigned URL returned
7. Verify redirect to S3/storage URL

**Expected Results:**
- Download URL requested first
- Presigned URL used for actual download
- Secure download process

### Test 7: Download Error Handling

**Steps:**
1. Simulate download URL generation failure
2. Attempt to download a file
3. **Screenshot:** Error message
4. Verify error toast: "Failed to get download URL"
5. Verify can retry

**Expected Results:**
- Error message displayed
- Toast notification shown
- Can attempt again

### Test 8: Download Non-Existent File

**Steps:**
1. Delete a file via API (or use invalid ID)
2. Try to download the deleted file
3. **Screenshot:** Error state
4. Verify appropriate error message
5. Verify graceful handling

**Expected Results:**
- Error for missing file
- Clear error message
- No crash or hang

### Test 9: Multiple Downloads

**Steps:**
1. Navigate to `/files` with multiple files
2. Initiate download for first file
3. Immediately initiate download for second file
4. **Screenshot:** Multiple downloads
5. Verify both downloads complete
6. Verify no conflicts

**Expected Results:**
- Can download multiple files
- Downloads don't conflict
- All files received

### Test 10: Download Updates Access Time

**Steps:**
1. Note file's last accessed time (if displayed)
2. Download the file
3. **Screenshot:** After download
4. Verify last_accessed_time updated
5. Verify download_count incremented (if shown)

**Expected Results:**
- Access time updated on download
- Download tracking works

### Test 11: Download via Direct Click (If Supported)

**Steps:**
1. Navigate to `/files`
2. Find a file card
3. Click directly on the file (not dropdown)
4. **Screenshot:** Direct click behavior
5. If preview: verify preview opens
6. If download: verify download starts
7. Document expected behavior

**Expected Results:**
- Direct click has defined behavior
- Consistent user experience

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/files/{id}/download` | Get presigned download URL |

## Request/Response Format

**Get Download URL Response:**
```json
{
  "download_url": "https://s3.amazonaws.com/bucket/file?signature=...",
  "expires_at": "2024-01-21T11:00:00Z",
  "filename": "document.pdf",
  "content_type": "application/pdf"
}
```

**Error Response:**
```json
{
  "detail": "File not found"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| File card (grid) | Card component with file info |
| File row (list) | Row in list view table |
| Actions dropdown | DropdownMenu trigger (three dots) |
| Download option | `getByRole('menuitem', { name: /download/i })` |
| Error toast | Toast notification with error message |

## Success Criteria

- Download option available in file actions
- Downloads work from both grid and list views
- All file types download correctly
- Presigned URLs used for security
- Errors handled with user feedback
- Multiple simultaneous downloads work
- Download tracking updates (if implemented)

## Notes

- Verify download URL expiry (default: 60 seconds to 24 hours)
- Test with various file sizes
- Check browser download behavior (popup blocker)
- Verify filename preservation on download
- Test with special characters in filenames
- Verify i18n for error messages
- Check download on mobile browsers
