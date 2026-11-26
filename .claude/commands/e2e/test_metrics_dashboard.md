# E2E Test: Metrics Dashboard

## Test Description
Validate that administrators can view system metrics including request rates, database stats, cache performance, and system resources with auto-refresh functionality.

## User Story
As an administrator
I want to view real-time system metrics
So that I can monitor application health and performance

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with metrics viewing permissions
- System generating metrics data

## Test Steps

### Test 1: Access Metrics Dashboard

**Steps:**
1. Login as admin user
2. Navigate to metrics page (e.g., `/admin/metrics`)
3. **Screenshot:** Metrics dashboard loaded
4. Verify page title "System Metrics" or similar
5. Verify metrics cards are displayed
6. Verify auto-refresh toggle is present
7. Verify last updated timestamp is shown

**Expected Results:**
- Admin can access metrics dashboard
- Metrics fetched from `GET /metrics`
- Multiple metric categories displayed
- Dashboard layout is organized

### Test 2: View Request Metrics

**Steps:**
1. Navigate to metrics dashboard
2. Locate "Request Metrics" card
3. **Screenshot:** Request metrics card
4. Verify displayed metrics:
   - Request Rate (per minute)
   - Average Latency (ms)
   - Error Rate (percentage)
   - Total Requests
5. Verify metrics have appropriate values (not null/undefined)
6. Verify color coding for thresholds (green/yellow/red)

**Expected Results:**
- Request metrics card displays correctly
- All metrics have valid values
- Threshold-based color coding works
- High error rates show warning colors

### Test 3: View Database Metrics

**Steps:**
1. Navigate to metrics dashboard
2. Locate "Database Metrics" card
3. **Screenshot:** Database metrics card
4. Verify displayed metrics:
   - Connection Pool Size
   - Connections In Use
   - Available Connections
5. Verify pool usage percentage calculation
6. Verify warning state when pool near capacity

**Expected Results:**
- Database metrics display correctly
- Pool usage is calculated properly
- Visual warnings for high utilization

### Test 4: View Cache Metrics

**Steps:**
1. Navigate to metrics dashboard
2. Locate "Cache Metrics" card
3. **Screenshot:** Cache metrics card
4. Verify displayed metrics:
   - Connection Status (Connected/Disconnected)
   - Hit Rate (percentage)
5. Verify connection status indicator
6. Verify hit rate shows percentage correctly

**Expected Results:**
- Cache metrics display correctly
- Connection status shows green when connected
- Hit rate percentage is accurate

### Test 5: View System Resources

**Steps:**
1. Navigate to metrics dashboard
2. Locate "System Resources" card
3. **Screenshot:** System resources card
4. Verify displayed metrics:
   - CPU Usage (percentage)
   - Memory Usage (percentage)
   - System Uptime
5. Verify progress bars or gauges for percentages
6. Verify uptime format is human-readable

**Expected Results:**
- System resources display correctly
- CPU and memory show progress indicators
- Uptime is formatted properly (e.g., "5d 3h 22m")

### Test 6: View Active Users and Jobs

**Steps:**
1. Navigate to metrics dashboard
2. Locate "Active Users" metric
3. Verify current active user count
4. Locate "Background Jobs" card
5. **Screenshot:** Background jobs metrics
6. Verify displayed job metrics:
   - Pending Jobs
   - In Progress Jobs
   - Failed Jobs
7. Verify failed jobs show warning color if > 0

**Expected Results:**
- Active users count is accurate
- Background job stats display correctly
- Failed jobs highlighted appropriately

### Test 7: Auto-Refresh Toggle

**Steps:**
1. Navigate to metrics dashboard
2. Note current "Last Updated" timestamp
3. Locate auto-refresh toggle (default: off or 10s)
4. **Screenshot:** Auto-refresh toggle
5. Enable auto-refresh
6. Wait 10-15 seconds
7. **Screenshot:** After auto-refresh
8. Verify "Last Updated" timestamp has changed
9. Verify metrics values may have updated
10. Disable auto-refresh
11. Wait 15 seconds
12. Verify timestamp does NOT change

**Expected Results:**
- Auto-refresh toggle works
- Polling interval is ~10 seconds
- Metrics update automatically when enabled
- Polling stops when disabled

### Test 8: Manual Refresh

**Steps:**
1. Navigate to metrics dashboard
2. Disable auto-refresh if enabled
3. Note current timestamp and metric values
4. Click "Refresh" button (if available) or reload page
5. **Screenshot:** After manual refresh
6. Verify timestamp updates
7. Verify metrics are re-fetched

**Expected Results:**
- Manual refresh works correctly
- New data is fetched from API
- UI updates with fresh data

### Test 9: Metric Threshold Indicators

**Steps:**
1. Navigate to metrics dashboard
2. **Screenshot:** Normal state (all green)
3. Verify color coding system:
   - Green: Normal/healthy
   - Yellow/Orange: Warning threshold
   - Red: Error/critical threshold
4. If possible, generate load to trigger warnings
5. **Screenshot:** Warning state (if achievable)
6. Verify appropriate color changes

**Expected Results:**
- Color coding reflects metric health
- Thresholds are reasonable
- Visual feedback is clear

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/metrics` | Fetch system metrics summary |

## Request/Response Format

**Get Metrics Response:**
```json
{
  "request_metrics": {
    "rate_per_minute": 150.5,
    "avg_latency_ms": 45.2,
    "error_rate": 0.02,
    "total_requests": 125000
  },
  "database_metrics": {
    "pool_size": 20,
    "connections_in_use": 5,
    "available_connections": 15
  },
  "cache_metrics": {
    "connected": true,
    "hit_rate": 0.85
  },
  "active_users": 42,
  "background_jobs": {
    "pending": 3,
    "in_progress": 2,
    "failed": 0
  },
  "system_resources": {
    "cpu_percent": 25.5,
    "memory_percent": 60.2,
    "uptime_seconds": 432000
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page title | `getByRole('heading', { name: /metrics|dashboard/i })` |
| Request metrics card | Card with "Request Metrics" heading |
| Database metrics card | Card with "Database Metrics" heading |
| Cache metrics card | Card with "Cache Metrics" heading |
| System resources card | Card with "System Resources" heading |
| Auto-refresh toggle | `getByRole('switch')` or toggle element |
| Last updated timestamp | Text showing timestamp |
| Refresh button | `getByRole('button', { name: /refresh/i })` |

## Success Criteria

- All metric categories display correctly
- Values are formatted properly (percentages, counts, durations)
- Auto-refresh works at configured interval
- Threshold color coding is accurate
- Dashboard loads quickly
- No errors when metrics unavailable

## Notes

- Test with metrics service unavailable (error handling)
- Verify polling doesn't cause memory leaks
- Test responsive layout on different screen sizes
- Verify admin-only access
- Consider testing with mock high-load data
