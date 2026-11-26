# E2E Test: Impersonation

## Test Description
Validate that super admins can impersonate other users to view the application from their perspective, and can safely end impersonation.

## User Story
As a super admin
I want to impersonate other users
So that I can troubleshoot issues and see the application from their perspective

## Prerequisites
- Backend server running
- Frontend dev server running
- Super admin user (is_admin: true):
  - Email: superadmin@example.com
  - Password: SuperAdminPassword123!
  - Organization: test-org
- Regular test user to impersonate:
  - Email: regularuser@example.com
- User is authenticated as super admin (use `/setup_test_auth`)

## Test Steps

### Test 1: Start Impersonation from User List

**Steps:**
1. Log in as super admin
2. Navigate to `/admin/users`
3. Wait for user list to load
4. Find a regular user (not admin, not self)
5. Click actions dropdown for that user
6. **Screenshot:** Actions showing impersonate option
7. Click "Impersonate" option
8. Wait for impersonation to start
9. **Screenshot:** Impersonation banner visible
10. Verify impersonation banner/header appears
11. Verify UI shows impersonated user's data
12. Verify header shows impersonated user's name

**Expected Results:**
- Impersonate option visible to super admins
- Impersonation starts successfully
- Visual indicator of active impersonation
- Application shows target user's perspective

### Test 2: Impersonation Banner Display

**Steps:**
1. Start impersonation (Test 1)
2. **Screenshot:** Full impersonation banner
3. Verify banner contains:
   - Clear indication of impersonation mode
   - Impersonated user's name/email
   - "End Impersonation" button
4. Verify banner is persistent across navigation
5. Navigate to different pages
6. Verify banner remains visible

**Expected Results:**
- Banner clearly visible at all times
- Shows who is being impersonated
- End option always accessible
- Banner style indicates special mode (red/warning)

### Test 3: View Application as Impersonated User

**Steps:**
1. Start impersonating a regular user
2. Navigate to `/dashboard`
3. **Screenshot:** Dashboard as impersonated user
4. Verify data shown is for impersonated user
5. Navigate to `/settings/account/profile`
6. **Screenshot:** Profile page showing impersonated user
7. Verify profile shows impersonated user's info
8. Navigate to `/files`
9. Verify files shown are impersonated user's files

**Expected Results:**
- All pages show impersonated user's data
- Admin features may be hidden
- User-specific content displayed
- Permissions reflect target user

### Test 4: End Impersonation

**Steps:**
1. Start impersonation
2. Verify impersonation banner visible
3. **Screenshot:** Before ending impersonation
4. Click "End Impersonation" button in banner
5. Wait for impersonation to end
6. **Screenshot:** After ending impersonation
7. Verify impersonation banner disappears
8. Verify admin user data restored
9. Verify admin features accessible again

**Expected Results:**
- End button terminates impersonation
- Admin session fully restored
- No impersonation artifacts remain
- Admin permissions restored

### Test 5: Cannot Impersonate Admin Users

**Steps:**
1. Log in as super admin
2. Navigate to `/admin/users`
3. Find another admin user (is_admin: true)
4. Click actions dropdown
5. **Screenshot:** Actions for admin user
6. Verify "Impersonate" option is:
   - Not present, OR
   - Disabled with tooltip

**Expected Results:**
- Cannot impersonate other admins
- Clear restriction in UI
- Security boundary enforced

### Test 6: Cannot Impersonate Self

**Steps:**
1. Navigate to `/admin/users`
2. Find own user (super admin) in list
3. Click actions dropdown
4. **Screenshot:** Actions for self
5. Verify "Impersonate" option not available for self

**Expected Results:**
- Cannot impersonate own account
- Option hidden or disabled for self

### Test 7: Impersonation Persists Across Refresh

**Steps:**
1. Start impersonation
2. Verify impersonation active
3. **Screenshot:** Before refresh
4. Refresh the browser page
5. Wait for page to load
6. **Screenshot:** After refresh
7. Verify impersonation still active
8. Verify banner still visible
9. Verify still viewing as impersonated user

**Expected Results:**
- Impersonation survives page refresh
- Session state preserved
- Banner reappears after refresh
- User data still from impersonated user

### Test 8: Impersonation History Available to Impersonated User

**Steps:**
1. Impersonate a user
2. End impersonation
3. Log out as super admin
4. Log in as the user who was impersonated
5. Navigate to `/settings/account/profile`
6. **Screenshot:** Impersonation history section
7. Verify impersonation history shows the session
8. Verify shows super admin's info, timestamps, duration

**Expected Results:**
- Users can see who impersonated them
- History shows impersonator details
- Start time, end time, duration recorded

### Test 9: Regular Admin Cannot Impersonate

**Steps:**
1. Log in as regular admin (not super admin)
2. Navigate to `/admin/users`
3. Find any user in list
4. Click actions dropdown
5. **Screenshot:** Actions without impersonate (regular admin)
6. Verify "Impersonate" option not present

**Expected Results:**
- Impersonation restricted to super admins
- Option not shown to regular admins
- No way to impersonate without is_admin: true

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/admin/impersonate/{user_id}` | Start impersonation |
| POST | `/admin/impersonate/end` | End impersonation |
| GET | `/admin/impersonate/session` | Get current session status |
| GET | `/impersonate/my-history` | Get impersonation history (user view) |

## Request/Response Format

**Start Impersonation Response:**
```json
{
  "access_token": "impersonation-token",
  "user": {
    "id": "user-uuid",
    "email": "regularuser@example.com",
    "first_name": "Regular",
    "last_name": "User"
  },
  "session_id": "session-uuid"
}
```

**End Impersonation Response:**
```json
{
  "message": "Impersonation ended successfully",
  "session_id": "session-uuid"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Actions dropdown | DropdownMenu trigger in user row |
| Impersonate option | `getByRole('menuitem', { name: /impersonate/i })` |
| Impersonation banner | Banner component with impersonation warning |
| End impersonation button | `getByRole('button', { name: /end impersonation/i })` |
| Impersonated user name | Text in banner showing user being impersonated |
| ImpersonationButton component | Component from ImpersonationButton.tsx |

## Success Criteria

- Super admins can impersonate regular users
- Impersonation banner clearly visible
- Application shows target user's data/permissions
- Can end impersonation and restore admin session
- Cannot impersonate admins or self
- Impersonation persists across refresh
- History available to impersonated users
- Regular admins cannot access impersonation

## Notes

- Verify audit log records all impersonation sessions
- Test impersonation with users in different states (active, suspended)
- Verify original admin tokens restored correctly
- Check that sensitive admin actions are blocked while impersonating
- Test impersonation with users having various permission sets
- Verify i18n for impersonation banner text
- Check impersonation timeout handling if implemented
