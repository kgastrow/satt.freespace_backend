# E2E Test: Audit Logs

## Test Description
Validate that administrators can view and filter audit logs to track system changes and user actions.

## User Story
As an administrator
I want to view audit logs
So that I can track changes to users, roles, and organizations for compliance and troubleshooting

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with audit log viewing permissions
- Audit logs exist (from previous actions on users, roles, organizations)

## Test Steps

### Test 1: Access Audit Logs Page

**Steps:**
1. Login as admin user
2. Navigate to audit logs page (e.g., `/admin/audit-logs`)
3. **Screenshot:** Audit logs page loaded
4. Verify page title "Audit Logs" or similar
5. Verify audit logs table is displayed
6. Verify filter options are present
7. Verify table columns: timestamp, actor, action, resource, actions

**Expected Results:**
- Admin can access audit logs page
- Logs fetched from `GET /audit-logs`
- Table displays audit entries
- Filter controls are visible

### Test 2: View Audit Log Entries

**Steps:**
1. Navigate to audit logs page
2. **Screenshot:** Audit log entries
3. Verify entries show:
   - Timestamp (formatted date/time)
   - Actor (user email or system)
   - Action (CREATE, UPDATE, DELETE) with colored badge
   - Resource (type + name/identifier)
4. Verify entries are sorted by timestamp (newest first)

**Expected Results:**
- Entries display complete information
- Timestamps are human-readable
- Action badges have distinct colors:
  - CREATE: green/success
  - UPDATE: blue/info
  - DELETE: red/destructive

### Test 3: Filter by Resource Type

**Steps:**
1. Navigate to audit logs page
2. Locate resource type filter dropdown
3. Select "User" from dropdown
4. **Screenshot:** Filtered by User resource
5. Verify only user-related audit entries are shown
6. Select "Role" from dropdown
7. Verify only role-related entries shown
8. Select "Organization" from dropdown
9. Verify only organization-related entries shown
10. Clear filter
11. Verify all entries shown

**Expected Results:**
- Resource type filter works correctly
- API includes `resourceType` parameter
- Results update immediately
- Filter can be cleared

### Test 4: Filter by Action Type

**Steps:**
1. Navigate to audit logs page
2. Locate action filter dropdown
3. Select "CREATE" from dropdown
4. **Screenshot:** Filtered by CREATE action
5. Verify only creation entries are shown
6. Select "UPDATE" from dropdown
7. Verify only update entries shown
8. Select "DELETE" from dropdown
9. Verify only deletion entries shown
10. Clear filter
11. Verify all entries shown

**Expected Results:**
- Action filter works correctly
- Filters can be combined with resource type
- Results update immediately

### Test 5: Filter by Date Range

**Steps:**
1. Navigate to audit logs page
2. Locate date range filters (from/to)
3. Set "From Date" to 7 days ago
4. **Screenshot:** Date from filter set
5. Verify entries are from last 7 days only
6. Set "To Date" to yesterday
7. **Screenshot:** Date range filter
8. Verify entries fall within date range
9. Clear date filters
10. Verify all entries shown

**Expected Results:**
- Date range filtering works
- Both from and to dates can be set
- Dates are inclusive
- Filter can be cleared

### Test 6: View Audit Log Details

**Steps:**
1. Navigate to audit logs page
2. Find an entry (preferably an UPDATE action)
3. Click "View Details" action or expand row
4. **Screenshot:** Audit log detail dialog
5. Verify details shown:
   - Actor (email or actor_id)
   - Action performed
   - Resource type
   - Resource name/identifier
   - Changes (for UPDATE actions)
6. For UPDATE actions, verify changes show:
   - Field name
   - Old value
   - New value

**Expected Results:**
- Details dialog opens correctly
- All audit information displayed
- Changes shown in readable format
- JSON data formatted properly

### Test 7: Pagination

**Steps:**
1. Navigate to audit logs page
2. Note total count (if displayed)
3. Verify page shows limited entries (e.g., 20)
4. Scroll to bottom or click "Load More"
5. **Screenshot:** Pagination controls
6. Click next page or load more
7. Verify additional entries load
8. Navigate back to first page
9. Verify original entries shown

**Expected Results:**
- Pagination controls work
- Offset-based pagination (20 per page)
- Can navigate between pages
- Page state maintained during session

### Test 8: Combined Filters

**Steps:**
1. Navigate to audit logs page
2. Set multiple filters:
   - Resource Type: "User"
   - Action: "UPDATE"
   - Date From: 30 days ago
3. **Screenshot:** Combined filters applied
4. Verify only matching entries shown
5. Clear one filter at a time
6. Verify results update with each change

**Expected Results:**
- Multiple filters can be combined
- AND logic applied to filters
- Clearing one filter keeps others active
- Results are intersection of all filters

### Test 9: Audit Log for Recent Actions

**Steps:**
1. Perform an auditable action (e.g., update a user role)
2. Navigate to audit logs page
3. Look for the action you just performed
4. **Screenshot:** Recent action in logs
5. Verify your action appears
6. Verify details are accurate:
   - Your email as actor
   - Correct action type
   - Correct resource

**Expected Results:**
- Recent actions appear in logs
- Logs are near real-time
- Details match the action performed

### Test 10: Empty State

**Steps:**
1. Navigate to audit logs page
2. Apply filters that return no results
   (e.g., future date or non-existent combination)
3. **Screenshot:** Empty state
4. Verify empty state message displayed
5. Verify message is helpful (not just blank)

**Expected Results:**
- Empty state is handled gracefully
- Helpful message shown
- Filters can still be modified

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/audit-logs` | Fetch audit logs with filters |

## Request/Response Format

**Get Audit Logs Request (Query Params):**
```
GET /audit-logs?resourceType=User&action=UPDATE&dateFrom=2024-01-01&dateTo=2024-01-15&offset=0&limit=20
```

**Audit Logs Response:**
```json
{
  "audit_logs": [
    {
      "id": "uuid",
      "timestamp": "2024-01-15T10:30:00Z",
      "actor_id": "uuid",
      "actor_email": "admin@example.com",
      "action": "UPDATE",
      "resource_type": "User",
      "resource_id": "uuid",
      "resource_name": "john@example.com",
      "changes": {
        "role": {
          "old": "viewer",
          "new": "editor"
        }
      }
    }
  ],
  "total": 150,
  "offset": 0,
  "limit": 20
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page title | `getByRole('heading', { name: /audit logs/i })` |
| Resource type filter | `getByLabelText(/resource type/i)` or select element |
| Action filter | `getByLabelText(/action/i)` or select element |
| Date from input | Date picker for start date |
| Date to input | Date picker for end date |
| Audit logs table | Table with log entries |
| View details button | `getByRole('button', { name: /view|details/i })` |
| Action badge | Badge with action text |
| Pagination controls | Page numbers or load more button |

## Success Criteria

- Audit logs page loads with entries
- Filtering by resource type works
- Filtering by action type works
- Date range filtering works
- Combined filters work correctly
- Details view shows all information
- Pagination handles large datasets
- Recent actions appear in logs

## Notes

- Verify audit logs are immutable (read-only)
- Test with high volume of logs (performance)
- Verify sensitive data is redacted if applicable
- Test export functionality if available
- Verify admin-only access
- Consider search by actor email
