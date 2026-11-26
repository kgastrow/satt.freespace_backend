# E2E Test: List Files

## Test Description
Validate that users can view their files with grid/list view toggle, filtering, and pagination.

## User Story
As a user
I want to view and browse my files
So that I can find and manage my uploaded content

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user with uploaded files:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- Multiple files of various types exist (images, videos, documents)
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Files Page

**Steps:**
1. Log in as test user
2. Navigate to `/files`
3. Wait for page to load
4. **Screenshot:** Files page initial view
5. Verify page header shows "My Files"
6. Verify Upload button visible
7. Verify storage usage card displayed

**Expected Results:**
- Files page loads successfully
- Header and upload button visible
- Storage usage shown

### Test 2: Grid View Display (Default)

**Steps:**
1. Navigate to `/files`
2. Wait for files to load
3. **Screenshot:** Grid view
4. Verify files displayed in grid layout
5. Verify file cards show:
   - Thumbnail (for images) or file icon
   - Filename (truncated if long)
6. Verify grid is responsive
7. Verify grid icon is selected in toggle

**Expected Results:**
- Default is grid view
- Cards display file info
- Responsive grid layout

### Test 3: Switch to List View

**Steps:**
1. Navigate to files page in grid view
2. Locate view toggle buttons
3. **Screenshot:** Grid/List toggle
4. Click List view icon button
5. Wait for view to change
6. **Screenshot:** List view
7. Verify table layout displayed
8. Verify columns: Filename, Size, Date
9. Verify list icon now selected

**Expected Results:**
- View switches to list
- Table shows file details
- Toggle state updates

### Test 4: Switch Back to Grid View

**Steps:**
1. From list view, click Grid icon
2. **Screenshot:** Back to grid view
3. Verify grid layout restored
4. Verify grid icon selected

**Expected Results:**
- Toggle works both ways
- View state preserved

### Test 5: Filter by Category - Images

**Steps:**
1. Navigate to `/files`
2. Locate category filter tabs
3. **Screenshot:** All files tab selected
4. Click "Images" tab
5. Wait for filter to apply
6. **Screenshot:** Images only
7. Verify only image files displayed
8. Verify file count/display reflects filter

**Expected Results:**
- Filter tabs visible
- Images tab shows only images
- Other file types hidden

### Test 6: Filter by Category - Documents

**Steps:**
1. Click "Documents" tab
2. Wait for filter
3. **Screenshot:** Documents only
4. Verify only documents shown (PDFs, DOCs, etc.)
5. Verify image/video files hidden

**Expected Results:**
- Documents filter works
- Only documents displayed

### Test 7: Filter by Category - Videos

**Steps:**
1. Click "Videos" tab
2. Wait for filter
3. **Screenshot:** Videos only
4. Verify only video files shown
5. Verify appropriate icons for video files

**Expected Results:**
- Videos filter works
- Only videos displayed

### Test 8: Search Files

**Steps:**
1. Navigate to `/files` with multiple files
2. Locate search input
3. **Screenshot:** Search input
4. Enter search term matching a filename
5. Wait for filter
6. **Screenshot:** Search results
7. Verify only matching files shown
8. Clear search
9. Verify all files return

**Expected Results:**
- Search input works
- Files filtered by name
- Clear restores all files

### Test 9: Pagination

**Steps:**
1. Navigate to `/files` with many files (50+)
2. **Screenshot:** First page
3. Verify pagination controls visible
4. Note files on first page
5. Click page 2 or Next
6. **Screenshot:** Second page
7. Verify different files shown
8. Click Previous or page 1
9. Verify original files shown

**Expected Results:**
- Pagination works
- Different files per page
- Navigation controls functional

### Test 10: Loading State

**Steps:**
1. Navigate to `/files`
2. **Screenshot:** Loading state
3. Observe loading indicator/skeleton
4. Wait for files to load
5. Verify smooth transition to content

**Expected Results:**
- Loading indicator shown
- Smooth transition to files
- No empty flash

### Test 11: Empty State

**Steps:**
1. Set up user with no files
2. Navigate to `/files`
3. **Screenshot:** Empty state
4. Verify empty state message: "No files found"
5. Verify upload call-to-action
6. Verify upload button still visible

**Expected Results:**
- Empty state displays
- Clear message shown
- Can still upload

### Test 12: File Action Dropdown

**Steps:**
1. Navigate to `/files` with files
2. Hover over or click a file card
3. Click actions dropdown (three dots)
4. **Screenshot:** Actions dropdown
5. Verify options:
   - Download
   - Delete
6. Close dropdown

**Expected Results:**
- Dropdown accessible
- Download option present
- Delete option present

### Test 13: Image Preview

**Steps:**
1. Navigate to `/files` with image files
2. Click on an image file card
3. **Screenshot:** Image preview dialog
4. Verify image displayed in full size
5. Verify dialog can be closed
6. Close dialog

**Expected Results:**
- Image preview works
- Full-size image displayed
- Can close preview

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/files?limit=50&offset=0` | List files with pagination |
| GET | `/files?category=image` | Filter by category |
| GET | `/files/usage` | Get storage usage |

## Request/Response Format

**List Files Response:**
```json
{
  "items": [
    {
      "id": "file-uuid",
      "original_filename": "document.pdf",
      "content_type": "application/pdf",
      "file_extension": "pdf",
      "size_bytes": 1048576,
      "category": "document",
      "status": "uploaded",
      "created_time": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 100,
  "limit": 50,
  "offset": 0
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page header | `getByRole('heading', { name: /my files/i })` |
| Upload button | `getByRole('button', { name: /upload/i })` |
| Grid toggle | Button with Grid icon |
| List toggle | Button with List icon |
| Category tabs | Tab components (All, Images, Videos, Documents, Other) |
| Images tab | `getByRole('tab', { name: /images/i })` |
| Search input | `getByPlaceholder(/search/i)` |
| File cards | Card components in grid |
| File rows | Row components in list |
| Actions dropdown | DropdownMenu trigger |
| Download option | `getByRole('menuitem', { name: /download/i })` |
| Delete option | `getByRole('menuitem', { name: /delete/i })` |
| Pagination | Pagination component |
| Empty state | Text with "No files found" |
| Preview dialog | Dialog component with image |

## Success Criteria

- Files page loads with grid view default
- View toggle switches between grid and list
- Category filters work correctly
- Search filters by filename
- Pagination works for many files
- Loading state displayed
- Empty state handled
- File actions dropdown accessible
- Image preview works

## Notes

- Test with various file types (images, PDFs, videos)
- Verify thumbnails load lazily
- Check responsive grid on mobile
- Verify i18n for all text
- Test with very long filenames
- Check file size formatting
