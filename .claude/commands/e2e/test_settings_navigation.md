# E2E Test: Settings Navigation

## Test Description
Validate navigation through all settings pages and categories.

## User Story
As a user
I want to navigate through settings pages
So that I can access and configure my preferences

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Access Settings Page

**Steps:**
1. Log in as user
2. Click on user avatar/menu
3. Click "Settings" link
4. **Screenshot:** Settings landing page
5. Verify settings layout loads
6. Verify sidebar visible (desktop)

**Expected Results:**
- Settings page loads
- Sidebar shows all categories
- Default section displayed

### Test 2: View Settings Sidebar Categories

**Steps:**
1. Navigate to settings page
2. **Screenshot:** Settings sidebar
3. Verify all categories visible:
   - Account
   - Preferences
   - Privacy & Security
   - App Settings
   - Support
   - Danger Zone
4. Verify categories are collapsible

**Expected Results:**
- All 6 categories shown
- Categories expandable/collapsible
- Clear visual hierarchy

### Test 3: Navigate Account Section

**Steps:**
1. Expand Account category (if collapsed)
2. **Screenshot:** Account section expanded
3. Click "Profile Information"
4. Verify profile page loads
5. Click "Connected Accounts"
6. Verify connected accounts page loads
7. Click "Session Management"
8. Verify sessions page loads

**Expected Results:**
- All account items accessible
- Pages load correctly
- Active item highlighted

### Test 4: Navigate Preferences Section

**Steps:**
1. Expand Preferences category
2. **Screenshot:** Preferences section
3. Click "Notifications"
4. Verify notification preferences page
5. Click "Language & Region"
6. Verify language page loads
7. Click "Appearance"
8. Verify appearance page loads

**Expected Results:**
- Preferences items accessible
- All pages functional
- Sidebar tracks active page

### Test 5: Navigate Privacy & Security Section

**Steps:**
1. Expand Privacy & Security category
2. **Screenshot:** Security section
3. Click "Password"
4. Verify password change page
5. Click "Change Email"
6. Verify email change page
7. Click "Two-Factor Authentication"
8. Verify 2FA settings page
9. Click "Privacy Settings"
10. Verify privacy page
11. Click "Data Export"
12. Verify export page

**Expected Results:**
- All security items accessible
- Each page loads correctly
- Forms functional

### Test 6: Navigate App Settings Section

**Steps:**
1. Expand App Settings category
2. **Screenshot:** App settings section
3. Click "Keyboard Shortcuts"
4. Verify shortcuts page
5. Click "Advanced"
6. Verify advanced settings page

**Expected Results:**
- App settings accessible
- Pages load
- Settings configurable

### Test 7: Navigate Support Section

**Steps:**
1. Expand Support category
2. **Screenshot:** Support section
3. Click "Feedback"
4. Verify feedback page
5. Click "About"
6. Verify about page with version info

**Expected Results:**
- Support items accessible
- Feedback form available
- About shows app info

### Test 8: Navigate Danger Zone

**Steps:**
1. Expand Danger Zone category
2. **Screenshot:** Danger zone section
3. Verify visual warning styling (red)
4. Click "Delete Account"
5. Verify delete account page
6. Verify confirmation requirements

**Expected Results:**
- Danger zone clearly marked
- Delete account accessible
- Safety warnings shown

### Test 9: Sidebar Collapse/Expand

**Steps:**
1. View settings with all categories expanded
2. Click on "Account" header to collapse
3. **Screenshot:** Account collapsed
4. Verify items hidden
5. Click again to expand
6. Verify items visible again

**Expected Results:**
- Categories collapsible
- State toggles correctly
- Smooth transition

### Test 10: Active State Tracking

**Steps:**
1. Navigate to Profile page
2. **Screenshot:** Profile active
3. Verify "Profile Information" highlighted
4. Navigate to Notifications
5. Verify "Notifications" highlighted
6. Verify previous selection unhighlighted

**Expected Results:**
- Active page highlighted
- Only one item active at a time
- Visual feedback clear

### Test 11: Mobile Settings Navigation

**Steps:**
1. View on mobile viewport
2. **Screenshot:** Mobile settings
3. Verify sidebar hidden by default
4. Click menu button
5. **Screenshot:** Mobile menu open
6. Verify sidebar appears in sheet
7. Click a settings item
8. Verify page navigates
9. Verify sheet closes

**Expected Results:**
- Mobile responsive
- Sheet navigation works
- Auto-closes on selection

### Test 12: Direct URL Navigation

**Steps:**
1. Navigate directly to `/settings/security/2fa`
2. **Screenshot:** Direct navigation
3. Verify 2FA page loads
4. Verify sidebar shows correct active state
5. Verify correct category expanded

**Expected Results:**
- Direct URLs work
- Sidebar syncs with URL
- Category auto-expands

### Test 13: External Link in Navigation

**Steps:**
1. Navigate to Account section
2. Find "My Files" link
3. **Screenshot:** External link indicator
4. Click "My Files"
5. Verify navigates to `/files`
6. Verify leaves settings area

**Expected Results:**
- External links marked
- Navigation works
- Exits settings properly

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| - | - | Navigation is client-side only |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Settings page | Main settings layout |
| Sidebar | Settings sidebar component |
| Category header | Collapsible category trigger |
| Category chevron | Expand/collapse icon |
| Nav item | Navigation link |
| Active indicator | Active styling class |
| Mobile menu button | Menu trigger button |
| Mobile sheet | Sheet component |
| Page header | `getByRole('heading')` |

## Success Criteria

- All settings categories visible
- All navigation items work
- Categories collapse/expand
- Active state tracks correctly
- Mobile navigation works
- Direct URLs function
- External links work
- i18n labels display correctly

## Notes

- Test with various screen sizes
- Verify keyboard navigation (Tab, Enter)
- Check that scroll position maintained
- Test with different user permissions
- Some items may be hidden based on features
- Verify all translations work

