# E2E Test: Admin Hub Navigation

## Test Description
Validate that the admin hub navigation works correctly with proper permission gating. Verify that users can navigate to admin functions through the hub pages and that the hub pages show only permitted functions.

## Prerequisites
- Backend server running
- Frontend dev server running
- Test users with different permission sets

## Test Steps

### Test 1: Admin Hub with Admin Permissions

**Setup:**
- User with admin permissions (e.g., users:read, users:write, api_keys:read)

**Steps:**
1. Login as user with admin permissions
2. Verify admin hub menu item is visible in sidebar
3. Click "Administration" in sidebar
4. **Screenshot:** Admin hub page showing visible cards
5. Verify only cards for granted permissions are visible
6. Click on one of the admin function cards (e.g., Users)
7. **Screenshot:** Users admin page
8. Verify navigation to the correct detail page
9. Click browser back button
10. Verify back on admin hub page

**Expected Results:**
- Admin hub menu item visible in sidebar
- Admin hub shows only cards for permissions user has
- Clicking a card navigates to the correct admin detail page
- Back button returns to hub

### Test 2: Admin Hub Empty State

**Setup:**
- User with no admin permissions

**Steps:**
1. Login as user without any admin permissions
2. Navigate to `/admin` directly via URL
3. **Screenshot:** Admin hub empty state
4. Verify empty state message is displayed
5. Verify admin hub menu item is NOT visible in sidebar

**Expected Results:**
- Empty state message: "You don't have access to any admin functions."
- No admin hub menu item in sidebar
- No admin function cards visible

### Test 3: Platform Admin Hub

**Setup:**
- Super admin user (is_admin=true)

**Steps:**
1. Login as super admin
2. Verify both "Administration" and "Platform Administration" menu items are visible in sidebar
3. Verify "Platform Administration" has red styling
4. Click "Platform Administration" in sidebar
5. **Screenshot:** Platform admin hub page with red accent
6. Verify all 10 platform admin cards are visible
7. Verify cards have red border styling
8. Click on one of the platform admin cards (e.g., Organizations)
9. **Screenshot:** Organizations admin page
10. Verify navigation to the correct detail page

**Expected Results:**
- Both hub menu items visible
- Platform admin hub has red danger styling
- All 10 platform admin cards visible with red accents
- Cards link to correct pages

### Test 4: Non-Super-Admin Cannot Access Platform Admin

**Setup:**
- Regular user with admin permissions (not super admin)

**Steps:**
1. Login as regular admin user
2. Verify "Platform Administration" menu item is NOT visible in sidebar
3. Navigate to `/platform-admin` directly via URL
4. **Screenshot:** Redirect or guard screen
5. Verify user is redirected to dashboard
6. Verify platform admin page is not accessible

**Expected Results:**
- Platform admin menu item not visible
- Direct URL access blocked by SuperAdminGuard
- User redirected to dashboard

### Test 5: Sidebar Navigation Consolidation

**Setup:**
- Super admin user

**Steps:**
1. Login as super admin
2. **Screenshot:** Sidebar showing consolidated navigation
3. Count sidebar menu items in admin section
4. Verify only 1 "Administration" menu item (not 12+)
5. Verify only 1 "Platform Administration" menu item (not 10+)
6. Verify total reduction from 22+ items to 2 items

**Expected Results:**
- Sidebar shows only 2 admin menu items (down from 22+)
- Clean, uncluttered navigation
- Clear visual hierarchy with red styling for platform admin

### Test 6: Mobile Responsiveness

**Setup:**
- Super admin user
- Mobile viewport (375x667)

**Steps:**
1. Set browser to mobile viewport
2. Login as super admin
3. Navigate to admin hub
4. **Screenshot:** Admin hub on mobile
5. Verify cards stack in single column
6. Navigate to platform admin hub
7. **Screenshot:** Platform admin hub on mobile
8. Verify cards stack properly
9. Click a card and verify navigation works

**Expected Results:**
- Grid layout responsive on mobile
- Cards stack in single column
- Touch navigation works correctly

## Test Data Requirements

**Admin User:**
- Email: admin@example.com
- Permissions: users:read, users:write, api_keys:read, notifications:read

**Regular User:**
- Email: user@example.com
- Permissions: [] (no admin permissions)

**Super Admin:**
- Email: superadmin@example.com
- is_admin: true

## Success Criteria

- All admin functions accessible through hub pages
- Permission gating works correctly (only permitted cards shown)
- Empty state displays for users with no admin permissions
- Platform admin hub properly restricted to super admins
- Red danger styling applied correctly to platform admin hub
- Sidebar navigation reduced from 22+ items to 2 hub items
- Mobile responsive layout works on small viewports
- All card links navigate to correct detail pages

## Notes

- Test on multiple browsers (Chrome, Firefox, Safari)
- Verify i18n translations display correctly for all locales
- Check that impersonation properly hides admin/platform admin hubs
- Ensure hub pages work with dark mode
