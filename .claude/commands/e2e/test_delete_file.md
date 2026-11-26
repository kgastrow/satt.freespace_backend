# E2E Test: Delete File

## Test Description
Validate that users can delete their files with confirmation dialog.

## User Story
As a user
I want to delete files I no longer need
So that I can manage my storage and remove unwanted content

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with uploaded files:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- At least one deletable file exists
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Open Delete Confirmation

**Steps:**
1. Navigate to `/files`
2. Find a file to delete
3. Click actions dropdown (three dots)
4. Click "Delete" option
5. **Screenshot:** Delete confirmation dialog
6. Verify dialog title: "Delete File"
7. Verify filename shown in message
8. Verify warning about permanent deletion

**Expected Results:**
- Confirmation dialog opens
- File name clearly shown
- Warning message displayed

### Test 2: Confirm Delete File

**Steps:**
1. Open delete confirmation for a file
2. Note the filename
3. **Screenshot:** Before confirming delete
4. Click "Delete" or "Confirm" button
5. Wait for API response
6. **Screenshot:** After deletion
7. Verify success toast: "File deleted successfully"
8. Verify file removed from list
9. Verify file count/storage updated

**Expected Results:**
- File deleted on confirm
- Success notification shown
- File no longer in list

### Test 3: Cancel Delete

**Steps:**
1. Open delete confirmation for a file
2. Note the file in list
3. **Screenshot:** Confirmation dialog
4. Click "Cancel" button
5. Verify dialog closes
6. Verify file still in list
7. Verify no notification

**Expected Results:**
- Cancel closes dialog
- File preserved
- No deletion occurs

### Test 4: Close Dialog via X Button

**Steps:**
1. Open delete confirmation
2. Click X button in dialog header
3. Verify dialog closes
4. Verify file still in list

**Expected Results:**
- X button closes dialog
- Same behavior as Cancel

### Test 5: Delete from List View

**Steps:**
1. Switch to list view
2. Find a file to delete
3. Click actions dropdown for that row
4. Click "Delete" option
5. **Screenshot:** List view delete confirmation
6. Confirm deletion
7. Verify file removed from list

**Expected Results:**
- Delete works in list view
- Same confirmation flow
- File removed after confirm

### Test 6: Loading State During Delete

**Steps:**
1. Open delete confirmation
2. Click "Delete" button
3. **Screenshot:** Loading state
4. Verify button shows loading indicator
5. Verify button disabled
6. Verify Cancel may be disabled
7. Wait for completion

**Expected Results:**
- Loading indicator shown
- Prevents double-click
- Completes successfully

### Test 7: Delete Error Handling

**Steps:**
1. Simulate network error
2. Attempt to delete a file
3. **Screenshot:** Error state
4. Verify error toast: "Failed to delete file"
5. Verify dialog closes or shows error
6. Verify file still in list

**Expected Results:**
- Error message displayed
- File not deleted on error
- Can retry

### Test 8: Delete Updates Storage Usage

**Steps:**
1. Note current storage usage
2. Note file size to be deleted
3. Delete the file
4. **Screenshot:** Updated storage
5. Verify storage usage decreased
6. Verify decrease matches file size

**Expected Results:**
- Storage usage updates
- Correct amount freed
- Visual indicator updates

### Test 9: Delete Multiple Files in Sequence

**Steps:**
1. Delete first file, confirm
2. Verify first deletion succeeds
3. Delete second file, confirm
4. **Screenshot:** After multiple deletions
5. Verify both files removed
6. Verify storage updated for both

**Expected Results:**
- Can delete multiple files
- Each deletion independent
- Storage updates correctly

### Test 10: Soft Delete Verification

**Steps:**
1. Note a file's ID before deletion
2. Delete the file
3. Verify file removed from list
4. Check API/database (if possible)
5. Verify file marked as deleted (not hard deleted)
6. Verify within retention period

**Expected Results:**
- Soft delete used (not permanent)
- File record preserved with deleted flag
- Can be recovered within retention

### Test 11: Keyboard Interaction

**Steps:**
1. Open delete confirmation
2. Verify focus on dialog
3. Press Escape key
4. Verify dialog closes
5. Reopen dialog
6. Press Enter (if focused on Delete)
7. Verify deletion proceeds

**Expected Results:**
- Escape closes dialog
- Enter can confirm (if focused)
- Keyboard accessible

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| DELETE | `/files/{id}` | Delete file (soft delete) |
| GET | `/files/usage` | Get updated storage usage |

## Request/Response Format

**Delete File Response (Success):**
```json
{
  "message": "File deleted successfully",
  "id": "file-uuid"
}
```

**Delete File Response (Error):**
```json
{
  "detail": "File not found"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in file card/row |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Confirmation dialog | ConfirmDialog component |
| Dialog title | `getByRole('heading', { name: /delete file/i })` |
| Filename in message | Text containing the file name |
| Delete button | `getByRole('button', { name: /delete/i })` with destructive variant |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Close (X) button | Dialog close button |
| Loading indicator | Spinner within delete button |
| Success toast | Toast with success message |
| Error toast | Toast with error message |
| Storage usage | StorageUsageBar component |

## Success Criteria

- Delete requires confirmation dialog
- Filename shown in confirmation
- File removed from list after deletion
- Cancel preserves the file
- Loading state prevents double-click
- Storage usage updates after deletion
- Errors handled with toast messages
- Soft delete preserves file record
- Works in both grid and list views

## Notes

- Verify audit log records deletion
- Test with files shared with others (if applicable)
- Check deleted file retention period
- Verify i18n for dialog text
- Test with special characters in filename
- Check if admin can recover deleted files
