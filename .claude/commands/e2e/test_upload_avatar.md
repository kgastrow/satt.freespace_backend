# E2E Test: Upload Avatar

## Test Description
Validate that authenticated users can upload, preview, and delete their profile avatar image.

## User Story
As an authenticated user
I want to upload and manage my profile avatar
So that my account has a personalized visual identity

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)
- Test image files available:
  - Valid: `test-avatar.jpg` (100KB, 200x200px)
  - Invalid size: `large-image.jpg` (>5MB)
  - Invalid type: `document.pdf`

## Test Steps

### Test 1: Upload Valid Avatar Image

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile page to load
3. **Screenshot:** Initial avatar state (initials or existing image)
4. Locate the avatar file input (data-testid="avatar-file-input")
5. Upload a valid image file (test-avatar.jpg)
6. Wait for upload to process
7. **Screenshot:** Preview of uploaded image
8. Verify image preview is displayed
9. Click "Save" or "Upload" to confirm
10. Wait for upload to complete
11. **Screenshot:** Avatar after successful upload
12. Verify success toast notification
13. Refresh the page
14. Verify avatar image persists

**Expected Results:**
- File input accepts valid image formats
- Preview shows uploaded image before confirmation
- Upload completes successfully
- New avatar displayed after save
- Avatar persists after page refresh

### Test 2: Avatar Image Validation - File Type

**Steps:**
1. Navigate to `/settings/account/profile`
2. Locate the avatar file input
3. Attempt to upload an invalid file type (document.pdf)
4. **Screenshot:** File type error message
5. Verify error message about invalid file type
6. Verify upload is rejected

**Expected Results:**
- System rejects non-image file types
- Clear error message displayed
- Only accepts: JPEG, PNG, GIF, WebP

### Test 3: Avatar Image Validation - File Size

**Steps:**
1. Navigate to `/settings/account/profile`
2. Locate the avatar file input
3. Attempt to upload an oversized image (>5MB)
4. **Screenshot:** File size error message
5. Verify error message about file size limit
6. Verify upload is rejected

**Expected Results:**
- System rejects files larger than 5MB
- Clear error message with size limit displayed
- User informed of maximum allowed size

### Test 4: Cancel Avatar Upload

**Steps:**
1. Navigate to `/settings/account/profile`
2. Upload a valid image file
3. Wait for preview to appear
4. **Screenshot:** Preview with cancel option
5. Click "Cancel" button
6. Verify preview is removed
7. Verify original avatar (or initials) is restored

**Expected Results:**
- Cancel action removes pending upload
- No changes made to existing avatar
- UI returns to initial state

### Test 5: Delete Existing Avatar

**Steps:**
1. Navigate to `/settings/account/profile` (user must have avatar)
2. **Screenshot:** Existing avatar displayed
3. Locate delete avatar button/icon
4. Click delete button
5. Verify confirmation dialog appears (if applicable)
6. Confirm deletion
7. Wait for delete operation
8. **Screenshot:** Avatar after deletion
9. Verify avatar removed, initials fallback shown
10. Verify success notification

**Expected Results:**
- Avatar can be deleted via UI action
- Confirmation prevents accidental deletion
- After deletion, initials fallback is shown
- Delete operation reflected immediately

### Test 6: Avatar Display in Different Sizes

**Steps:**
1. Upload a new avatar image
2. Navigate to `/settings/account/profile`
3. **Screenshot:** Avatar on profile page
4. Navigate to dashboard or header area
5. **Screenshot:** Avatar in header/navigation
6. Verify avatar displays correctly in all locations

**Expected Results:**
- Avatar scales correctly for different display sizes
- Image quality maintained at various sizes
- No distortion or cropping issues

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/user/me/avatar` | Upload avatar image |
| DELETE | `/user/me/avatar` | Delete avatar image |
| GET | `/user/me` | Get user profile with avatar URL |

## Request/Response Format

**Upload Avatar Request:**
```
POST /user/me/avatar
Content-Type: multipart/form-data

file: [binary image data]
```

**Upload Avatar Response:**
```json
{
  "avatar_url": "https://storage.example.com/avatars/uuid.jpg",
  "message": "Avatar uploaded successfully"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Avatar display | `data-testid="profile-avatar"` |
| File input | `data-testid="avatar-file-input"` |
| Upload button | `getByRole('button', { name: /upload|change/i })` |
| Delete button | `getByRole('button', { name: /delete|remove/i })` |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Preview image | Avatar container with new image src |
| Error message | Toast or inline error text |

## Success Criteria

- Valid images can be uploaded successfully
- Invalid file types are rejected with clear error
- Oversized files are rejected with size limit info
- Upload preview allows confirmation or cancellation
- Existing avatars can be deleted
- Avatar displays correctly across the application
- Operations provide appropriate feedback (loading, success, error)

## Notes

- Test with various image formats: JPG, PNG, GIF, WebP
- Test with transparent PNG images
- Verify avatar URL updates in auth state
- Check CDN/storage integration if applicable
- Test upload progress indicator if implemented
- Verify EXIF rotation handling for mobile photos
