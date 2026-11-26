# E2E Test: Request Logs

## Test Description
Validate that administrators can view, filter, and manage API request logs, including configuring logging settings and triggering log cleanup.

## User Story
As an administrator
I want to view API request logs
So that I can debug issues, monitor API usage, and analyze request patterns

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with request log viewing permissions
- Request logging enabled with existing log entries

## Test Steps

### Test 1: Access Request Logs Page

**Steps:**
1. Login as admin user
2. Navigate to request logs page (e.g., `/admin/request-logs`)
3. **Screenshot:** Request logs page loaded
4. Verify page title "Request Logs" or similar
5. Verify request logs table is displayed
6. Verify filter options are present
7. Verify logging settings card is present
8. Verify table columns: timestamp, method, path, status_code, duration, ip_address

**Expected Results:**
- Admin can access request logs page
- Logs fetched from `GET /request-logs`
- Table displays request entries
- Settings configuration visible

### Test 2: View Request Log Entries

**Steps:**
1. Navigate to request logs page
2. **Screenshot:** Request log entries
3. Verify entries show:
   - Timestamp (formatted)
   - HTTP Method (GET, POST, PUT, DELETE, PATCH)
   - Path (URL path, may be truncated)
   - Status Code (with colored badge)
   - Duration (ms)
   - IP Address
4. Verify method badges have colors:
   - GET: blue
   - POST: green
   - PUT/PATCH: yellow/orange
   - DELETE: red
5. Verify status code badges:
   - 2xx: green/success
   - 3xx: blue/info
   - 4xx: yellow/warning
   - 5xx: red/error

**Expected Results:**
- Entries display complete information
- Method and status badges are color-coded
- Path truncation with full path in tooltip/title

### Test 3: Filter by HTTP Method

**Steps:**
1. Navigate to request logs page
2. Locate method filter dropdown
3. Select "GET" from dropdown
4. **Screenshot:** Filtered by GET method
5. Verify only GET requests shown
6. Select "POST" from dropdown
7. Verify only POST requests shown
8. Clear filter
9. Verify all methods shown

**Expected Results:**
- Method filter works correctly
- Results update immediately
- Filter can be cleared

### Test 4: Filter by Path

**Steps:**
1. Navigate to request logs page
2. Locate path filter input
3. Enter partial path: "/api/users"
4. **Screenshot:** Filtered by path
5. Verify only matching paths shown
6. Clear path filter
7. Verify all paths shown

**Expected Results:**
- Path filter performs partial match
- Case-insensitive matching (if applicable)
- Filter can be cleared

### Test 5: Filter by Status Code Range

**Steps:**
1. Navigate to request logs page
2. Locate status code filter
3. Filter for 4xx errors (client errors)
4. **Screenshot:** Filtered by 4xx status
5. Verify only 400-499 status codes shown
6. Filter for 5xx errors (server errors)
7. Verify only 500-599 status codes shown
8. Filter for successful 2xx responses
9. Verify only 200-299 status codes shown
10. Clear filter

**Expected Results:**
- Status code range filtering works
- Can filter by specific codes or ranges
- Error logs are easily accessible

### Test 6: Filter by Date Range

**Steps:**
1. Navigate to request logs page
2. Set date range: last 24 hours
3. **Screenshot:** Date filtered logs
4. Verify entries are within date range
5. Set specific from/to dates
6. Verify entries match range
7. Clear date filters

**Expected Results:**
- Date range filtering works
- Timestamps fall within range
- Filter can be cleared

### Test 7: Filter by User Email

**Steps:**
1. Navigate to request logs page
2. Locate user email filter input
3. Enter a known user email
4. **Screenshot:** Filtered by user
5. Verify only requests from that user shown
6. Clear filter
7. Verify all users shown

**Expected Results:**
- User filter identifies requests by authenticated user
- Anonymous requests have null user
- Filter can be cleared

### Test 8: View Request Details

**Steps:**
1. Navigate to request logs page
2. Find a request entry
3. Click on row or "View Details" button
4. **Screenshot:** Request details dialog
5. Verify details shown:
   - Method and status code
   - Full path
   - Duration (ms)
   - IP address
   - Organization ID (if applicable)
   - User ID (if authenticated)
   - User Agent string
   - Request body (JSON formatted)
   - Response body (JSON formatted)
   - Error traceback (if error)

**Expected Results:**
- Details dialog opens correctly
- All request information displayed
- JSON bodies are formatted/prettified
- Error tracebacks are readable

### Test 9: View Error Request Details

**Steps:**
1. Navigate to request logs page
2. Filter for 5xx status codes
3. Click on an error entry
4. **Screenshot:** Error request details
5. Verify error_traceback is displayed
6. Verify traceback is formatted
7. Verify original request info is present

**Expected Results:**
- Error details include traceback
- Traceback is readable (formatted)
- Helpful for debugging

### Test 10: Configure Request Logging Settings

**Steps:**
1. Navigate to request logs page
2. Locate settings card/section
3. **Screenshot:** Logging settings
4. Verify settings options:
   - Enabled toggle
   - Database logging toggle
   - Max body size (1024-102400 bytes)
   - Retention days (1-365)
5. Modify max body size: 10240
6. Modify retention days: 30
7. Click "Save Settings"
8. Verify success notification
9. Refresh page
10. Verify settings persisted

**Expected Results:**
- Settings fetched from `GET /request-logs/config`
- Settings saved via `PUT /request-logs/config`
- Validation enforces min/max values
- Settings persist after save

### Test 11: Toggle Request Logging

**Steps:**
1. Navigate to request logs page
2. Locate "Enabled" toggle in settings
3. Note current state
4. Toggle to opposite state
5. Save settings
6. Verify success notification
7. Make an API request
8. Check if request is logged (or not) based on state
9. Restore original state

**Expected Results:**
- Logging can be enabled/disabled
- New requests respect logging state
- Setting is admin-configurable

### Test 12: Trigger Log Cleanup

**Steps:**
1. Navigate to request logs page
2. Locate "Cleanup" or "Purge" button
3. **Screenshot:** Cleanup option
4. Click cleanup button
5. **Screenshot:** Cleanup confirmation
6. Verify confirmation shows:
   - Retention period
   - Estimated logs to delete
7. Confirm cleanup
8. Verify success notification
9. Verify old logs are removed

**Expected Results:**
- Cleanup triggered via `POST /request-logs/cleanup`
- Confirmation shows impact
- Old logs (beyond retention) are deleted
- Recent logs preserved

### Test 13: Cursor-Based Pagination

**Steps:**
1. Navigate to request logs page with many entries
2. **Screenshot:** First page of logs
3. Note the first few entries
4. Click "Next" to load more
5. **Screenshot:** Next page
6. Verify new entries loaded
7. Click "Previous" to go back
8. Verify original entries shown
9. Click "First" to return to beginning

**Expected Results:**
- Cursor-based pagination works
- Next/Previous buttons functional
- First button returns to start
- Page state maintained

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/request-logs` | Fetch request logs with filters |
| GET | `/request-logs/config` | Get logging configuration |
| PUT | `/request-logs/config` | Update logging configuration |
| POST | `/request-logs/cleanup` | Trigger log cleanup |

## Request/Response Format

**Get Request Logs (Query Params):**
```
GET /request-logs?method=GET&path=/api/users&status_min=400&status_max=499&cursor=xyz123
```

**Request Logs Response:**
```json
{
  "logs": [
    {
      "id": "uuid",
      "timestamp": "2024-01-15T10:30:00Z",
      "method": "GET",
      "path": "/api/users/123",
      "status_code": 200,
      "duration_ms": 45,
      "ip_address": "192.168.1.100",
      "organization_id": "uuid",
      "user_id": "uuid",
      "user_agent": "Mozilla/5.0...",
      "request_body": null,
      "response_body": "{\"id\": \"123\", ...}",
      "error_traceback": null
    }
  ],
  "next_cursor": "abc456",
  "prev_cursor": null
}
```

**Logging Config Response:**
```json
{
  "enabled": true,
  "db_enabled": true,
  "max_body_size": 10240,
  "retention_days": 30
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page title | `getByRole('heading', { name: /request logs/i })` |
| Method filter | `getByLabelText(/method/i)` or select element |
| Path filter | `getByLabelText(/path/i)` or input element |
| Status filter | Status code range input or select |
| User email filter | `getByLabelText(/user|email/i)` |
| Date filters | Date picker inputs |
| Request logs table | Table with log entries |
| View details button | Row click or button |
| Settings card | Settings section with toggles |
| Enabled toggle | `getByRole('switch', { name: /enabled/i })` |
| Max body size input | `getByLabelText(/max.*body.*size/i)` |
| Retention days input | `getByLabelText(/retention/i)` |
| Save settings button | `getByRole('button', { name: /save/i })` |
| Cleanup button | `getByRole('button', { name: /cleanup|purge/i })` |
| Pagination buttons | First, Previous, Next buttons |

## Success Criteria

- Request logs page loads with entries
- Method, path, status, date filters work
- User email filter works
- Details view shows complete request info
- Error tracebacks displayed for errors
- Settings configuration works
- Logging can be enabled/disabled
- Log cleanup works correctly
- Cursor-based pagination works

## Notes

- Verify sensitive data is redacted (passwords, tokens)
- Test with high volume of logs (performance)
- Verify request/response body truncation at max_body_size
- Consider export functionality
- Verify admin-only access
- Test with various content types (JSON, form data, etc.)
