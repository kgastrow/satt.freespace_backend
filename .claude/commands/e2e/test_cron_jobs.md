# E2E Test: Cron Jobs Management

## Test Description
Validate that administrators can create, edit, delete, enable/disable, and manually trigger cron jobs, as well as view execution history.

## User Story
As an administrator
I want to manage scheduled cron jobs
So that I can automate recurring tasks and monitor their execution

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated admin user with cron job management permissions
- At least one existing cron job for testing

## Test Steps

### Test 1: Access Cron Jobs Page

**Steps:**
1. Login as admin user
2. Navigate to cron jobs page (e.g., `/admin/cron-jobs`)
3. **Screenshot:** Cron jobs page loaded
4. Verify page title "Cron Jobs" or similar
5. Verify cron jobs table is displayed
6. Verify "Create" button is present
7. Verify table columns: name, code, schedule, status, last_run, next_run, actions

**Expected Results:**
- Admin can access cron jobs management
- Jobs fetched from `GET /cron-jobs`
- Table displays all scheduled jobs
- Create button is visible

### Test 2: Create New Cron Job

**Steps:**
1. Navigate to cron jobs page
2. Click "Create" button
3. **Screenshot:** Create cron job dialog/form
4. Fill in details:
   - Name: "Test Cleanup Job"
   - Code: "test_cleanup" (unique identifier)
   - Schedule: "0 0 * * *" (daily at midnight)
   - Description: "Test job for cleanup tasks"
5. **Screenshot:** Filled form
6. Click "Save" or "Create" button
7. Wait for success response
8. **Screenshot:** Success state
9. Verify success toast notification
10. Verify new job appears in table
11. Verify schedule shows human-readable format in tooltip

**Expected Results:**
- Create dialog opens with form fields
- Cron expression validation works
- Job created via `POST /cron-jobs`
- Success notification displayed
- Job appears in list

### Test 3: Cron Expression Validation

**Steps:**
1. Click "Create" button
2. Enter invalid cron expression: "invalid cron"
3. Try to save
4. **Screenshot:** Validation error
5. Verify cron expression validation error displayed
6. Enter valid expression: "*/5 * * * *" (every 5 minutes)
7. Verify validation passes
8. Hover over schedule cell
9. **Screenshot:** Schedule tooltip with human-readable format
10. Verify tooltip shows "Every 5 minutes"

**Expected Results:**
- Invalid cron expressions are rejected
- Validation message is clear
- Valid expressions are accepted
- Human-readable format shown in tooltip

### Test 4: Edit Existing Cron Job

**Steps:**
1. Navigate to cron jobs page
2. Find an existing cron job
3. Click "Edit" action button
4. **Screenshot:** Edit dialog with pre-filled data
5. Verify form is pre-filled with existing data
6. Modify schedule: "0 */2 * * *" (every 2 hours)
7. Modify description: "Updated description"
8. **Screenshot:** Modified form
9. Click "Save" button
10. Verify success notification
11. Verify table shows updated schedule

**Expected Results:**
- Edit dialog opens with existing data
- Changes are saved via `PUT /cron-jobs/{id}`
- Table reflects updates
- Success notification shown

### Test 5: Enable/Disable Cron Job

**Steps:**
1. Navigate to cron jobs page
2. Find a cron job that is enabled (status: active)
3. Click toggle/switch to disable
4. **Screenshot:** Disable confirmation (if any)
5. Confirm disable action
6. Verify success notification
7. Verify status changes to "disabled" or "inactive"
8. Click toggle again to enable
9. Verify status changes back to "enabled" or "active"

**Expected Results:**
- Toggle calls `PATCH /cron-jobs/{id}/toggle`
- Status updates immediately in UI
- Disabled jobs won't run on schedule
- Enable/disable is reversible

### Test 6: Manually Trigger Cron Job

**Steps:**
1. Navigate to cron jobs page
2. Find an enabled cron job
3. Click "Run Now" or trigger action button
4. **Screenshot:** Trigger confirmation
5. Confirm trigger action
6. Verify success notification "Job triggered"
7. **Screenshot:** After trigger
8. Verify "last_run" column updates
9. Check execution history (if visible)

**Expected Results:**
- Manual trigger calls `POST /cron-jobs/{id}/trigger`
- Job executes immediately
- Last run timestamp updates
- Execution logged in history

### Test 7: View Execution History

**Steps:**
1. Navigate to cron jobs page
2. Find a cron job with execution history
3. Click "View History" or expand row
4. **Screenshot:** Execution history dialog/panel
5. Verify history shows:
   - Execution timestamp (started_at)
   - Completion timestamp (completed_at)
   - Status (success/failed)
   - Duration
   - Error message (if failed)
   - Result JSON (if available)
6. Find a failed execution
7. **Screenshot:** Failed execution details
8. Verify error message is displayed

**Expected Results:**
- History fetched from `GET /cron-jobs/{id}/executions`
- All executions are listed
- Failed executions show error details
- Success executions show result

### Test 8: Delete Cron Job

**Steps:**
1. Navigate to cron jobs page
2. Find a cron job to delete (preferably test job)
3. Click "Delete" action button
4. **Screenshot:** Delete confirmation dialog
5. Verify confirmation dialog shows job name
6. Click "Confirm Delete"
7. Verify success notification
8. **Screenshot:** After deletion
9. Verify job is removed from table

**Expected Results:**
- Delete requires confirmation
- Job deleted via `DELETE /cron-jobs/{id}`
- Success notification shown
- Job removed from list

### Test 9: Cron Job Configuration

**Steps:**
1. Navigate to cron jobs page
2. Look for "Settings" or "Configuration" option
3. **Screenshot:** Cron job global config
4. Verify configuration options:
   - Enable/disable all jobs
   - Default timeout
   - Retry settings
5. Modify a setting
6. Save configuration
7. Verify success notification

**Expected Results:**
- Global configuration accessible
- Settings saved via `PUT /cron-jobs/config`
- Changes affect all jobs

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/cron-jobs` | List all cron jobs |
| POST | `/cron-jobs` | Create new cron job |
| PUT | `/cron-jobs/{id}` | Update cron job |
| DELETE | `/cron-jobs/{id}` | Delete cron job |
| PATCH | `/cron-jobs/{id}/toggle` | Enable/disable job |
| POST | `/cron-jobs/{id}/trigger` | Manually trigger job |
| GET | `/cron-jobs/{id}/executions` | Get execution history |
| GET | `/cron-jobs/config` | Get global config |
| PUT | `/cron-jobs/config` | Update global config |

## Request/Response Format

**Create Cron Job Request:**
```json
{
  "name": "Test Cleanup Job",
  "code": "test_cleanup",
  "schedule": "0 0 * * *",
  "description": "Test job for cleanup tasks",
  "enabled": true
}
```

**Cron Job Response:**
```json
{
  "id": "uuid",
  "name": "Test Cleanup Job",
  "code": "test_cleanup",
  "schedule": "0 0 * * *",
  "description": "Test job for cleanup tasks",
  "enabled": true,
  "last_run": "2024-01-15T00:00:00Z",
  "next_run": "2024-01-16T00:00:00Z",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Execution History Response:**
```json
{
  "executions": [
    {
      "id": "uuid",
      "status": "success",
      "started_at": "2024-01-15T00:00:00Z",
      "completed_at": "2024-01-15T00:00:05Z",
      "duration_ms": 5000,
      "result": { "processed": 100 },
      "error": null
    }
  ]
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Create button | `getByRole('button', { name: /create|add/i })` |
| Cron jobs table | Table with job rows |
| Name input | `getByLabelText(/name/i)` |
| Code input | `getByLabelText(/code/i)` |
| Schedule input | `getByLabelText(/schedule|cron/i)` |
| Enable toggle | Switch/toggle per job row |
| Run Now button | `getByRole('button', { name: /run|trigger/i })` |
| Edit button | `getByRole('button', { name: /edit/i })` |
| Delete button | `getByRole('button', { name: /delete/i })` |
| History button | `getByRole('button', { name: /history/i })` |

## Success Criteria

- CRUD operations work correctly
- Cron expression validation is accurate
- Enable/disable toggle works
- Manual trigger executes job
- Execution history is accessible
- Delete requires confirmation
- All changes persist

## Notes

- Verify cron expression format matches backend expectations
- Test with various cron schedules
- Verify timezone handling
- Test job execution timeout scenarios
- Verify admin-only access
