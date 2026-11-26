# E2E Test: Data Export

## Test Description
Validate that authenticated users can request an export of their personal data, view export history, and download completed exports.

## User Story
As an authenticated user
I want to export my personal data
So that I can have a copy of all my information stored in the system

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)
- User has some data to export (profile, files, etc.)

## Test Steps

### Test 1: Request Data Export

**Steps:**
1. Navigate to `/settings/security/export`
2. Wait for data export page to load
3. **Screenshot:** Data export page
4. Verify page title and description about data export
5. Locate "Request Export" or "Export My Data" button
6. Click the export request button
7. Wait for request to be submitted
8. **Screenshot:** After request submitted
9. Verify success notification
10. Verify new export appears in history with "Pending" status

**Expected Results:**
- Export request submitted successfully
- Success notification displayed
- Export appears in history immediately
- Status shows as pending/processing

### Test 2: View Export History

**Steps:**
1. Navigate to `/settings/security/export`
2. Wait for export history to load
3. **Screenshot:** Export history table
4. Verify table displays:
   - Status badge (pending, processing, completed, failed, expired)
   - Creation date
   - File size (when completed)
   - Download count
   - Expiration date
   - Download button (when completed)
5. Verify pagination if multiple exports exist

**Expected Results:**
- Export history displays all past exports
- Columns show relevant information
- Status badges color-coded appropriately
- Completed exports show download option

### Test 3: Download Completed Export

**Steps:**
1. Navigate to `/settings/security/export`
2. Wait for a completed export to appear (may need to wait or use existing)
3. **Screenshot:** Completed export with download button
4. Verify export status is "Completed"
5. Click "Download" button
6. Verify download starts (file or new tab)
7. **Screenshot:** Download initiated
8. Verify file is a ZIP archive
9. Verify download count increments

**Expected Results:**
- Download button enabled for completed exports
- File downloads successfully
- ZIP file contains user data
- Download count tracked

### Test 4: Export Status Progression

**Steps:**
1. Request a new data export
2. **Screenshot:** Pending status
3. Wait and refresh periodically
4. Observe status change to "Processing"
5. **Screenshot:** Processing status
6. Wait for completion
7. **Screenshot:** Completed status
8. Verify file size appears when completed
9. Verify expiration date is set

**Expected Results:**
- Status progresses: Pending → Processing → Completed
- Status updates visible on refresh
- Completed exports have size and expiration
- Processing may show progress (if implemented)

### Test 5: Export Expiration

**Steps:**
1. Navigate to `/settings/security/export`
2. Find an export with expiration date
3. **Screenshot:** Export with expiration info
4. Verify expiration date is displayed
5. If expired export exists:
   - Verify status shows "Expired"
   - Verify download button is disabled
   - **Screenshot:** Expired export

**Expected Results:**
- Expiration date clearly shown
- Expired exports cannot be downloaded
- Visual indication of expired status

### Test 6: Multiple Export Requests

**Steps:**
1. Navigate to `/settings/security/export`
2. Request a new export
3. Immediately request another export
4. **Screenshot:** Multiple pending exports or rate limit message
5. Verify system behavior (queue or rate limit)
6. Verify all requested exports appear in history

**Expected Results:**
- Multiple exports handled appropriately
- Rate limiting prevents abuse (if implemented)
- All valid requests tracked in history

### Test 7: Export Content Verification

**Steps:**
1. Download a completed export
2. Extract the ZIP file
3. **Screenshot:** ZIP contents
4. Verify export contains:
   - User profile data (JSON or CSV)
   - Uploaded files (if any)
   - Activity/audit data (if included)
   - Export metadata
5. Verify data matches actual user data

**Expected Results:**
- ZIP contains structured data files
- Profile information accurate
- Files included if user has uploads
- No other users' data included

### Test 8: Failed Export Handling

**Steps:**
1. Simulate a failed export (if possible via test setup)
2. Navigate to `/settings/security/export`
3. **Screenshot:** Failed export status
4. Verify status shows "Failed"
5. Verify error information displayed (if available)
6. Verify can request new export after failure

**Expected Results:**
- Failed status clearly indicated
- Error information helpful
- System doesn't block new requests after failure

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/me/export` | Request new data export |
| GET | `/users/me/exports` | List export history |
| GET | `/users/me/exports/{exportId}/download` | Get download URL |

## Request/Response Format

**Request Export Response:**
```json
{
  "id": "export-uuid",
  "status": "pending",
  "created_time": "2024-01-01T00:00:00Z",
  "message": "Export request submitted successfully"
}
```

**List Exports Response:**
```json
{
  "exports": [
    {
      "id": "export-uuid",
      "status": "completed",
      "created_time": "2024-01-01T00:00:00Z",
      "completed_time": "2024-01-01T00:05:00Z",
      "file_size_bytes": 1048576,
      "download_count": 2,
      "expires_at": "2024-01-08T00:00:00Z"
    }
  ],
  "total": 1
}
```

**Download Export Response:**
```json
{
  "download_url": "https://storage.example.com/exports/uuid.zip?token=...",
  "expires_in": 3600
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Request export button | `getByRole('button', { name: /request export|export my data/i })` |
| Export history table | DataTable component |
| Status badge | Badge component with status text |
| Download button | `getByRole('button', { name: /download/i })` |
| File size text | Cell showing file size |
| Expiration date | Cell showing expiration |
| Download count | Cell showing download count |

## Success Criteria

- Export request submitted successfully
- History shows all exports with correct status
- Completed exports can be downloaded
- Downloaded ZIP contains user's data
- Status progression works correctly
- Expired exports handled appropriately
- Failed exports don't block system

## Notes

- Verify export includes all GDPR-required data
- Test with users having various amounts of data
- Verify large exports handle well (progress indication)
- Check download works with both direct and signed URLs
- Verify email notification when export ready
- Test download on different browsers
- Verify i18n for status labels and messages
