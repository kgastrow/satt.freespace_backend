# E2E Test: Delete Organization

## Test Description
Validate the organization deletion workflow including soft delete requests, cancellation, and hard delete for super admins.

## User Story
As an organization owner or super admin
I want to request deletion of an organization
So that I can remove organizations that are no longer needed

## Prerequisites
- Backend server running
- Frontend dev server running
- Organization owner user:
  - Email: owner@example.com
  - Password: OwnerPassword123!
- Super admin user:
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
- At least one organization available for deletion testing
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Owner Request Deletion

**Steps:**
1. Log in as organization owner
2. Navigate to `/admin/organization`
3. Scroll to Danger Zone section
4. **Screenshot:** Request deletion button
5. Click "Request Deletion" button
6. Verify confirmation dialog appears
7. **Screenshot:** Deletion confirmation dialog
8. Read warning about deletion consequences
9. Click "Confirm" button
10. Wait for API response
11. **Screenshot:** After deletion request
12. Verify success notification
13. Verify deletion pending status shown

**Expected Results:**
- Owner can request deletion
- Confirmation dialog explains consequences
- Status changes to pending deletion
- Retention period notice shown

### Test 2: View Deletion Pending Status

**Steps:**
1. Log in as owner of organization with pending deletion
2. Navigate to `/admin/organization`
3. **Screenshot:** Pending deletion status
4. Verify displayed information:
   - Deletion requested indicator
   - Deletion request date
   - Retention period notice
   - Cancel deletion button
5. Verify Request Deletion button hidden

**Expected Results:**
- Pending status clearly shown
- Request date displayed
- Retention period explained
- Cancel option available

### Test 3: Cancel Deletion Request (Owner)

**Steps:**
1. Log in as owner with pending deletion
2. Navigate to `/admin/organization`
3. Locate Cancel Deletion button
4. **Screenshot:** Cancel deletion button
5. Click "Cancel Deletion" button
6. Verify confirmation dialog
7. Click "Confirm" to cancel deletion
8. Wait for API response
9. **Screenshot:** After cancellation
10. Verify success notification
11. Verify organization no longer pending deletion

**Expected Results:**
- Owner can cancel deletion
- Confirmation required
- Status reverts to normal
- Request Deletion button returns

### Test 4: Super Admin Soft Delete

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find an active organization
4. Click actions dropdown
5. **Screenshot:** Soft delete option
6. Click "Soft Delete" or "Request Deletion"
7. Verify confirmation dialog
8. **Screenshot:** Soft delete confirmation
9. Click "Confirm"
10. Wait for response
11. Verify organization marked as pending deletion

**Expected Results:**
- Super admin can soft delete any org
- Confirmation required
- Organization marked for deletion
- Still visible in list with pending status

### Test 5: Super Admin Cancel Deletion

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find organization with pending deletion
4. Click actions dropdown
5. **Screenshot:** Cancel deletion option
6. Click "Cancel Deletion"
7. Confirm action
8. **Screenshot:** After cancellation
9. Verify deletion cancelled
10. Verify organization status restored

**Expected Results:**
- Super admin can cancel any deletion
- Organization restored to normal state
- Status badge updates

### Test 6: Check Hard Delete Eligibility

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find organization with pending deletion
4. Click actions dropdown
5. **Screenshot:** Hard delete option status
6. If retention period not passed:
   - Verify "Permanently Delete" disabled or shows tooltip
   - Note remaining time in retention period
7. If retention passed:
   - Verify "Permanently Delete" enabled

**Expected Results:**
- Hard delete blocked during retention
- Clear indication of eligibility
- Retention period enforced

### Test 7: Super Admin Hard Delete

**Steps:**
1. Set up organization past retention period
2. Log in as super admin
3. Navigate to `/platform-admin/organizations`
4. Find eligible organization
5. Click actions dropdown
6. **Screenshot:** Hard delete option enabled
7. Click "Permanently Delete"
8. Verify strong warning dialog
9. **Screenshot:** Hard delete confirmation
10. Enter confirmation text if required
11. Click "Delete Permanently"
12. Wait for response
13. **Screenshot:** After hard delete
14. Verify organization removed from list

**Expected Results:**
- Hard delete requires extra confirmation
- Strong warning about permanent action
- Organization completely removed
- Cannot be recovered

### Test 8: Cannot Hard Delete Active Organization

**Steps:**
1. Log in as super admin
2. Navigate to `/platform-admin/organizations`
3. Find an active organization (no deletion requested)
4. Click actions dropdown
5. **Screenshot:** Actions for active org
6. Verify "Permanently Delete" option:
   - Not present, OR
   - Disabled

**Expected Results:**
- Must soft delete first
- Hard delete only for pending orgs
- Proper workflow enforced

### Test 9: Loading States

**Steps:**
1. Initiate deletion request
2. **Screenshot:** Loading during request
3. Verify button shows loading indicator
4. Verify UI disabled during operation
5. Wait for completion
6. Verify loading state clears

**Expected Results:**
- Loading indicator during API call
- Prevents double submission
- Clear completion state

### Test 10: Error Handling

**Steps:**
1. Attempt deletion with network error
2. **Screenshot:** Error state
3. Verify error notification
4. Verify organization unchanged
5. Restore network
6. Retry operation
7. Verify succeeds

**Expected Results:**
- Error message displayed
- Organization not affected on error
- Can retry after error

### Test 11: Non-Owner Cannot Request Deletion

**Steps:**
1. Log in as organization admin (not owner)
2. Navigate to `/admin/organization`
3. Scroll to Danger Zone
4. **Screenshot:** Restricted view
5. Verify "Request Deletion" button:
   - Not visible, OR
   - Disabled with explanation

**Expected Results:**
- Only owners can request deletion
- Clear permission indication
- Admins cannot delete

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/organizations/{id}/request-deletion` | Request soft delete |
| DELETE | `/organizations/{id}/request-deletion` | Cancel deletion request |
| GET | `/organizations/{id}/hard-delete-status` | Check hard delete eligibility |
| DELETE | `/organizations/{id}/hard-delete` | Permanently delete organization |

## Request/Response Format

**Request Deletion Response:**
```json
{
  "message": "Deletion request submitted",
  "organization_id": "org-uuid",
  "deletion_requested_time": "2024-01-21T10:00:00Z"
}
```

**Cancel Deletion Response:**
```json
{
  "message": "Deletion request cancelled",
  "organization_id": "org-uuid"
}
```

**Hard Delete Status Response:**
```json
{
  "can_hard_delete": true,
  "deletion_requested_time": "2024-01-01T10:00:00Z",
  "retention_period_days": 30,
  "retention_ends": "2024-01-31T10:00:00Z"
}
```

**Hard Delete Response:**
```json
{
  "message": "Organization permanently deleted",
  "organization_id": "org-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Danger Zone section | Section with deletion options |
| Request Deletion button | `getByRole('button', { name: /request deletion/i })` |
| Cancel Deletion button | `getByRole('button', { name: /cancel deletion/i })` |
| Confirmation dialog | ConfirmDialog component |
| Confirm button | `getByRole('button', { name: /confirm/i })` with destructive variant |
| Cancel button | `getByRole('button', { name: /cancel/i })` |
| Deletion status notice | Alert or banner showing pending status |
| Retention period text | Text showing deletion timeline |
| Actions dropdown (super admin) | DropdownMenu trigger |
| Soft Delete option | `getByRole('menuitem', { name: /soft delete|request deletion/i })` |
| Hard Delete option | `getByRole('menuitem', { name: /permanently delete/i })` |
| Loading indicator | Spinner within button |

## Success Criteria

- Owners can request organization deletion
- Deletion pending status clearly displayed
- Owners can cancel deletion request
- Super admins can soft delete any organization
- Super admins can cancel any deletion
- Hard delete blocked during retention period
- Hard delete available after retention period
- Strong warnings for permanent deletion
- Loading states prevent double submission
- Errors handled gracefully
- Non-owners cannot request deletion

## Notes

- Verify retention period is configurable
- Test with organizations that have users/files
- Check cascade effects on related data
- Verify audit log records all deletion events
- Test email notifications for deletion events
- Verify i18n for all messages and warnings
- Check hard delete removes all associated data
