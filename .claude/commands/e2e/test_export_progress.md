# E2E Test: Export Progress (Real-Time)

## Test Description
Validate that users receive real-time progress updates for data export operations via WebSocket.

## User Story
As a user
I want to see real-time progress of my data export
So that I know how long to wait and can track the export status

## Prerequisites
- Backend server running with WebSocket support
- Frontend dev server running
- Authenticated user session with WebSocket connected
- Export functionality available (user data export or report export)

## Test Steps

### Test 1: Initiate Export and Receive Progress Updates

**Steps:**
1. Login as user
2. Verify WebSocket is connected
3. Navigate to export functionality (e.g., Settings > Data Export)
4. Click "Export My Data" or similar button
5. **Screenshot:** Export initiated state
6. Verify progress indicator appears
7. Watch for progress updates
8. **Screenshot:** Progress update (e.g., 25%)
9. **Screenshot:** Progress update (e.g., 75%)
10. Verify progress updates in real-time
11. Wait for completion
12. **Screenshot:** Export complete

**Expected Results:**
- Export starts and progress tracking begins
- Progress updates received via WebSocket
- Progress indicator updates in real-time
- No page refresh needed to see updates

### Test 2: Progress Indicator Display

**Steps:**
1. Initiate an export
2. Observe progress indicator
3. **Screenshot:** Progress bar/indicator
4. Verify progress indicator shows:
   - Percentage complete
   - Progress bar visualization
   - Current step/phase (if applicable)
5. Verify indicator updates smoothly

**Expected Results:**
- Clear progress visualization
- Percentage displayed numerically
- Progress bar matches percentage
- Updates are smooth, not jumpy

### Test 3: Export Phases/Steps Display

**Steps:**
1. Initiate an export
2. Observe progress updates
3. **Screenshot:** Different export phases
4. Verify phases are shown (if implemented):
   - "Gathering data..."
   - "Processing records..."
   - "Generating file..."
   - "Preparing download..."
5. Verify current phase is highlighted

**Expected Results:**
- Export phases are communicated
- Current phase is clear
- User understands what's happening

### Test 4: Export Completion Notification

**Steps:**
1. Initiate an export
2. Wait for export to complete
3. **Screenshot:** Export complete notification
4. Verify completion notification:
   - Success message displayed
   - Download link/button available
   - File size shown (if applicable)
5. Click download link
6. Verify file downloads correctly

**Expected Results:**
- Clear completion notification
- Download immediately available
- File downloads successfully
- Notification via WebSocket

### Test 5: Export Error Handling

**Steps:**
1. Initiate an export that may fail (or simulate failure)
2. Wait for progress updates
3. **Screenshot:** Export error state
4. Verify error notification:
   - Error message displayed
   - Reason for failure (if available)
   - Option to retry
5. Click retry button (if available)
6. Verify retry initiates new export

**Expected Results:**
- Error communicated via WebSocket
- Clear error message to user
- Retry option available
- User not left in limbo

### Test 6: Cancel Export in Progress

**Steps:**
1. Initiate an export
2. While progress is updating, click "Cancel" button
3. **Screenshot:** Cancel confirmation (if any)
4. Confirm cancellation
5. **Screenshot:** Export cancelled state
6. Verify export is cancelled
7. Verify progress updates stop
8. Verify cancellation message shown

**Expected Results:**
- Cancel button available during export
- Export can be cancelled
- Progress updates stop
- Clear cancellation feedback

### Test 7: Progress Persists Across Page Navigation

**Steps:**
1. Initiate an export
2. Verify progress is showing (e.g., 30%)
3. Navigate away to another page
4. Navigate back to export page
5. **Screenshot:** Progress restored
6. Verify progress indicator still shows
7. Verify updates continue

**Expected Results:**
- Progress state persists
- Can navigate away and return
- Updates resume on return
- Export continues in background

### Test 8: Progress on Page Refresh

**Steps:**
1. Initiate an export
2. Verify progress is showing (e.g., 50%)
3. Refresh the browser page
4. **Screenshot:** Progress after refresh
5. Verify progress indicator restored
6. Verify current progress is accurate
7. Verify updates continue

**Expected Results:**
- Progress survives page refresh
- State fetched from server
- Export continues regardless
- WebSocket reconnects and resumes

### Test 9: Multiple Concurrent Exports (if supported)

**Steps:**
1. Initiate first export
2. Verify progress starts
3. Initiate second export (if allowed)
4. **Screenshot:** Multiple export progress
5. Verify both exports tracked
6. Verify separate progress for each
7. Wait for completions
8. Verify both downloads available

**Expected Results:**
- Multiple exports handled (if supported)
- Separate progress tracking
- No interference between exports
- Both complete successfully

### Test 10: Large Export Progress

**Steps:**
1. Request a large data export (maximum allowed data)
2. Verify progress starts
3. **Screenshot:** Large export progress
4. Verify progress updates are frequent enough
5. Verify estimated time shown (if implemented)
6. Wait for completion (may take time)
7. Verify large file downloads correctly

**Expected Results:**
- Large exports work correctly
- Progress updates at reasonable intervals
- Estimated time helpful for long exports
- File downloads completely

### Test 11: Export Progress in Notification Area

**Steps:**
1. Initiate an export
2. Check notification bell/area
3. **Screenshot:** Export notification in bell
4. Verify export progress appears as notification
5. Minimize or navigate away from export page
6. Verify notification updates with progress
7. Click notification to go to export

**Expected Results:**
- Export tracked in notifications
- Progress visible in notification area
- Can monitor without staying on page
- Click navigates to export

### Test 12: WebSocket Disconnect During Export

**Steps:**
1. Initiate an export
2. Verify progress is updating
3. Simulate network disconnect (DevTools Offline)
4. Wait a few seconds
5. Restore network connection
6. **Screenshot:** Reconnection and progress recovery
7. Verify WebSocket reconnects
8. Verify progress updates resume
9. Verify export completes

**Expected Results:**
- Export continues on server despite disconnect
- WebSocket reconnects
- Progress syncs after reconnect
- Export not lost due to disconnect

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/users/me/export` | Initiate data export |
| GET | `/exports/{id}/status` | Check export status (fallback) |
| WS | `/ws` | Real-time progress updates |

## WebSocket Message Format

**Export Started:**
```json
{
  "type": "export_progress",
  "payload": {
    "export_id": "uuid",
    "status": "started",
    "progress": 0,
    "phase": "Gathering data"
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Export Progress Update:**
```json
{
  "type": "export_progress",
  "payload": {
    "export_id": "uuid",
    "status": "in_progress",
    "progress": 45,
    "phase": "Processing records",
    "records_processed": 4500,
    "total_records": 10000
  },
  "timestamp": "2024-01-15T10:00:30Z"
}
```

**Export Complete:**
```json
{
  "type": "export_progress",
  "payload": {
    "export_id": "uuid",
    "status": "completed",
    "progress": 100,
    "download_url": "/exports/uuid/download",
    "file_size": 2456789,
    "filename": "user_export_2024-01-15.zip"
  },
  "timestamp": "2024-01-15T10:02:00Z"
}
```

**Export Failed:**
```json
{
  "type": "export_progress",
  "payload": {
    "export_id": "uuid",
    "status": "failed",
    "error": "Export exceeded maximum size limit"
  },
  "timestamp": "2024-01-15T10:01:30Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Export button | `getByRole('button', { name: /export/i })` |
| Progress bar | Progress bar element |
| Progress percentage | Text showing percentage |
| Phase/step text | Text showing current phase |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Download button | `getByRole('button', { name: /download/i })` |
| Retry button | `getByRole('button', { name: /retry/i })` |
| Success message | Alert or toast with success |
| Error message | Alert or toast with error |

## Success Criteria

- Export initiates and progress tracking starts
- Progress updates delivered via WebSocket
- Progress indicator updates in real-time
- Phases/steps communicated clearly
- Completion notification with download
- Error handling with retry option
- Cancel functionality works
- Progress persists across navigation/refresh
- WebSocket reconnection recovers progress
- Download works correctly

## Notes

- Test with various export sizes
- Verify file integrity after download
- Test concurrent exports behavior
- Monitor server performance during exports
- Verify export timeout handling
- Test with slow network conditions
- Consider export queuing if server busy
