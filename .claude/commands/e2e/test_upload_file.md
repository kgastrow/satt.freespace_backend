# E2E Test: Upload File

## Test Description
Validate that users can upload files via drag-and-drop or file picker with progress tracking.

## User Story
As a user
I want to upload files to my account
So that I can store and manage my documents and media

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with storage quota available:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Test files available for upload
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Upload Dialog

**Steps:**
1. Navigate to `/files`
2. Click "Upload File" button
3. **Screenshot:** Upload dialog open
4. Verify dialog title "Upload Files"
5. Verify drag-and-drop zone displayed
6. Verify click-to-browse text visible

**Expected Results:**
- Dialog opens on button click
- Drag-drop zone visible
- Instructions clear

### Test 2: Upload via File Picker

**Steps:**
1. Open upload dialog
2. Click on the drop zone area
3. Select a test file from file picker
4. **Screenshot:** File selected
5. Observe upload progress bar
6. Wait for upload to complete
7. **Screenshot:** Upload success
8. Verify success indicator (checkmark)
9. Verify file appears in files list

**Expected Results:**
- File picker opens on click
- Progress shown during upload
- Success indicator displayed
- File added to list

### Test 3: Drag-and-Drop Upload

**Steps:**
1. Open upload dialog
2. Prepare a test file for dragging
3. Drag file over drop zone
4. **Screenshot:** Drag active state (highlighted border)
5. Drop the file
6. Observe upload progress
7. Wait for completion
8. **Screenshot:** Upload complete
9. Verify success

**Expected Results:**
- Drop zone highlights on drag
- File uploads after drop
- Progress and success shown

### Test 4: Upload Multiple Files

**Steps:**
1. Open upload dialog
2. Select multiple files (2-3 files)
3. **Screenshot:** Multiple files queued
4. Observe progress for each file
5. Wait for all uploads to complete
6. **Screenshot:** All uploads complete
7. Close dialog
8. Verify all files in list

**Expected Results:**
- Multiple files can be selected
- Each file shows progress
- All files upload successfully

### Test 5: Upload Progress Display

**Steps:**
1. Open upload dialog
2. Upload a larger file (several MB)
3. **Screenshot:** Progress bar during upload
4. Verify progress bar animates
5. Verify percentage or visual progress
6. Verify file shows "uploading" state
7. Wait for completion
8. Verify progress completes to 100%

**Expected Results:**
- Progress bar visible during upload
- Progress updates visually
- Completes when done

### Test 6: Upload Success Indicator

**Steps:**
1. Upload a file
2. Wait for completion
3. **Screenshot:** Success state
4. Verify green checkmark or success icon
5. Verify "Upload successful" message
6. Observe auto-removal after 2 seconds
7. Verify file removed from upload list

**Expected Results:**
- Success icon (CheckCircle) shown
- Success state visible briefly
- File auto-clears from upload queue

### Test 7: Invalid File Type Rejection

**Steps:**
1. Open upload dialog
2. Try to select a file with disallowed extension
3. **Screenshot:** File rejected
4. Verify rejection message
5. Verify file not added to upload queue
6. Verify drop zone shows reject state (if dragging)

**Expected Results:**
- Invalid files rejected
- Clear error message
- Reject visual state on drag

### Test 8: File Size Limit Exceeded

**Steps:**
1. Open upload dialog
2. Try to upload file exceeding max size (default 100MB)
3. **Screenshot:** Size limit error
4. Verify error message about file size
5. Verify file not uploaded

**Expected Results:**
- Large files rejected
- Clear size limit message
- Upload prevented

### Test 9: Upload Error Handling

**Steps:**
1. Open upload dialog
2. Simulate network error or API failure
3. Attempt file upload
4. **Screenshot:** Upload error state
5. Verify error message displayed
6. Verify X button to remove from list
7. Click X to remove failed file
8. Verify file removed from queue

**Expected Results:**
- Error state shown
- Error message displayed
- Can remove failed files

### Test 10: Cancel Upload Dialog

**Steps:**
1. Open upload dialog
2. Add a file (but don't wait for completion)
3. Click close/X button on dialog
4. **Screenshot:** Dialog closed
5. Verify dialog closes
6. Verify no partial uploads in list

**Expected Results:**
- Can close dialog
- Uploads may complete in background
- UI handles gracefully

### Test 11: Storage Quota Update

**Steps:**
1. Note current storage usage
2. Upload a new file
3. Wait for upload complete
4. **Screenshot:** Updated storage usage
5. Verify storage bar/number updated
6. Verify usage increased appropriately

**Expected Results:**
- Storage usage updates after upload
- Numbers reflect new total
- Visual indicator updates

### Test 12: Drop Zone Visual States

**Steps:**
1. Open upload dialog
2. **Screenshot:** Idle state
3. Drag file over drop zone
4. **Screenshot:** Active state (highlighted)
5. Drag invalid file over zone
6. **Screenshot:** Reject state (red highlight)
7. Drop valid file
8. Verify upload starts

**Expected Results:**
- Idle: Default border
- Active: Primary color highlight
- Reject: Destructive red highlight

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/files/upload` | Direct file upload |
| POST | `/files/upload-url` | Get presigned upload URL |
| POST | `/files/upload-complete` | Confirm multipart upload |
| GET | `/files/usage` | Get updated storage usage |

## Request/Response Format

**Upload File (FormData):**
```
POST /files/upload
Content-Type: multipart/form-data

file: <binary data>
```

**Upload Response:**
```json
{
  "id": "new-file-uuid",
  "original_filename": "document.pdf",
  "content_type": "application/pdf",
  "size_bytes": 1048576,
  "status": "uploaded",
  "created_time": "2024-01-21T10:00:00Z"
}
```

**Error Response (Size Limit):**
```json
{
  "detail": "File size exceeds maximum allowed (100MB)"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Upload button (page) | `getByRole('button', { name: /upload/i })` |
| Upload dialog | Dialog component |
| Dialog title | `getByRole('heading', { name: /upload files/i })` |
| Drop zone | FileUploader component |
| Drop zone text | Text with "drag" or "drop" |
| File input | Hidden file input in drop zone |
| Progress bar | Progress component |
| Success icon | CheckCircle icon (green) |
| Error message | Text with error details |
| Remove button (X) | Button to remove failed file |
| Close dialog | Dialog close button |
| Storage usage | StorageUsageBar component |

## Success Criteria

- Upload dialog opens correctly
- Files can be selected via picker
- Drag-and-drop works with visual feedback
- Multiple files can be uploaded
- Progress bar shows during upload
- Success indicator shown on completion
- Invalid files rejected with message
- Size limits enforced
- Errors handled gracefully
- Storage usage updates after upload

## Notes

- Verify max file size from settings (default 100MB)
- Test with various file types (images, PDFs, videos)
- Check video size limit separately (may be larger)
- Verify i18n for upload messages
- Test upload cancellation if supported
- Check upload progress accuracy
