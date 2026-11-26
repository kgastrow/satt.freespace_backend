# E2E Test: Sidebar Navigation

## Test Description
Validate the main application sidebar navigation functionality.

## User Story
As a user
I want to navigate using the sidebar
So that I can access different areas of the application

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Main Sidebar

**Steps:**
1. Log in as user
2. Navigate to dashboard
3. **Screenshot:** Main sidebar
4. Verify sidebar visible (desktop)
5. Verify navigation items displayed

**Expected Results:**
- Sidebar loads with app
- Navigation items visible
- Clear visual design

### Test 2: Navigate to Dashboard

**Steps:**
1. View sidebar
2. **Screenshot:** Dashboard link
3. Click "Dashboard" link
4. Verify navigates to `/dashboard`
5. Verify Dashboard link highlighted

**Expected Results:**
- Dashboard link works
- Active state shown
- Page loads correctly

### Test 3: Navigate to Files

**Steps:**
1. Click "Files" in sidebar
2. **Screenshot:** Files page
3. Verify navigates to `/files`
4. Verify Files link highlighted
5. Verify file list loads

**Expected Results:**
- Files navigation works
- Page loads correctly
- Active state updated

### Test 4: Navigate to Notifications

**Steps:**
1. Click "Notifications" in sidebar
2. **Screenshot:** Notifications page
3. Verify navigates to notifications
4. Verify link highlighted

**Expected Results:**
- Notifications accessible
- Page loads
- Active state shown

### Test 5: Access Administration Hub

**Steps:**
1. Log in as admin user
2. **Screenshot:** Admin link visible
3. Verify "Admin" link in sidebar
4. Click "Admin" link
5. Verify navigates to `/admin`
6. Verify admin hub loads

**Expected Results:**
- Admin link visible for admins
- Navigation works
- Admin hub displays

### Test 6: Access Platform Admin Hub

**Steps:**
1. Log in as super admin
2. **Screenshot:** Platform admin link
3. Verify "Platform Admin" link visible
4. Click "Platform Admin"
5. Verify navigates to platform admin area

**Expected Results:**
- Platform admin for super admins
- Link visible only to super admin
- Navigation works

### Test 7: Permission-Based Visibility

**Steps:**
1. Log in as regular user (no admin)
2. **Screenshot:** Sidebar without admin
3. Verify "Admin" link NOT visible
4. Verify "Platform Admin" NOT visible
5. Verify only user-level items shown

**Expected Results:**
- Admin links hidden
- Regular nav visible
- Permission-based filtering

### Test 8: Sidebar Collapse (Desktop)

**Steps:**
1. View sidebar on desktop
2. Click collapse button
3. **Screenshot:** Collapsed sidebar
4. Verify sidebar minimized
5. Verify icons still visible
6. Click expand button
7. Verify sidebar expands

**Expected Results:**
- Collapse toggle works
- Icons remain visible
- Labels hidden when collapsed
- Expand restores full view

### Test 9: Collapsed State Navigation

**Steps:**
1. Collapse sidebar
2. Hover over navigation icon
3. **Screenshot:** Tooltip shown
4. Verify tooltip shows label
5. Click icon
6. Verify navigation works

**Expected Results:**
- Tooltips on collapsed state
- Click navigation works
- Consistent behavior

### Test 10: Mobile Sidebar

**Steps:**
1. View on mobile viewport
2. **Screenshot:** Mobile header
3. Verify sidebar hidden by default
4. Click hamburger menu button
5. **Screenshot:** Mobile sidebar open
6. Verify sidebar appears as sheet
7. Click outside or X to close
8. Verify sidebar closes

**Expected Results:**
- Hidden by default on mobile
- Sheet opens on trigger
- Can close sheet
- Touch-friendly

### Test 11: Mobile Navigation

**Steps:**
1. Open mobile sidebar
2. Click "Files" link
3. Verify navigates to files
4. Verify sidebar closes automatically
5. **Screenshot:** After mobile navigation

**Expected Results:**
- Navigation works on mobile
- Sidebar auto-closes
- Page loads correctly

### Test 12: User Profile Menu

**Steps:**
1. View sidebar
2. Find user avatar/name section
3. **Screenshot:** User profile area
4. Click user profile area
5. Verify dropdown menu appears
6. Verify options:
   - Settings
   - Logout

**Expected Results:**
- User info displayed
- Dropdown menu works
- Settings and logout accessible

### Test 13: Logout from Sidebar

**Steps:**
1. Open user profile menu
2. Click "Logout"
3. **Screenshot:** After logout
4. Verify logged out
5. Verify redirected to login

**Expected Results:**
- Logout works
- Session ended
- Redirect to login

### Test 14: Theme Toggle in Sidebar

**Steps:**
1. View sidebar header area
2. Find theme toggle
3. **Screenshot:** Theme toggle
4. Click to toggle theme
5. Verify theme changes (light/dark)
6. Verify persists on reload

**Expected Results:**
- Theme toggle accessible
- Theme switches
- Preference saved

### Test 15: Language Switcher in Sidebar

**Steps:**
1. View sidebar header area
2. Find language switcher
3. **Screenshot:** Language dropdown
4. Click language switcher
5. Select different language
6. Verify UI updates to new language
7. Verify sidebar labels translated

**Expected Results:**
- Language switcher accessible
- All 5 languages available
- UI updates immediately
- Sidebar labels translate

### Test 16: Keyboard Navigation

**Steps:**
1. Focus on sidebar
2. Press Tab to move through items
3. **Screenshot:** Focused item
4. Verify focus visible
5. Press Enter on focused item
6. Verify navigation occurs
7. Use arrow keys if supported

**Expected Results:**
- Tab navigation works
- Focus indicators visible
- Enter activates links
- Accessible navigation

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/auth/logout` | Logout user |
| - | - | Navigation is client-side |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Sidebar | `Sidebar` component |
| Dashboard link | Nav link to dashboard |
| Files link | Nav link to files |
| Admin link | Nav link to admin |
| Platform Admin link | Nav link to platform-admin |
| Collapse button | Sidebar collapse trigger |
| Mobile menu button | Mobile hamburger button |
| Mobile sheet | Sheet component |
| User profile area | User info section |
| Profile dropdown | Dropdown menu |
| Settings link | `getByRole('menuitem', { name: /settings/i })` |
| Logout button | `getByRole('menuitem', { name: /logout/i })` |
| Theme toggle | Theme toggle button |
| Language switcher | Language dropdown |

## Success Criteria

- All navigation links work
- Active states track correctly
- Collapse/expand works
- Mobile sidebar functions
- Permission-based visibility
- User menu works
- Theme toggle works
- Language switcher works
- Keyboard accessible
- i18n translations display

## Notes

- Test with various user permission levels
- Verify sticky/fixed positioning
- Check scroll behavior with many items
- Test impersonation mode visibility
- Verify notification badges if applicable
- Check all translations for nav items

