# E2E Test: Freespace Sites

## Test Description
Validate the Sites section of the back office: list, create, settings, zones, message templates, ingest keys, and read-only access for Viewer/Operator users.

## User Story
As an administrator
I want to configure Freespace sites
So that the backend sends the right parking advisories for each site

## Prerequisites
- Backend server running, database seeded (roles Administrator, Operator, Viewer exist)
- Frontend dev server running
- An administrator user (holds `sites:read`, `sites:write`, `site_keys:write`) and a viewer user (holds `sites:read`)
- At least one site with one zone exists, or create them in Test 1

## Test Steps

### Test 1: Create a Site
1. Login as administrator, navigate to `/admin/sites`
2. **Screenshot:** sites list (name, site id, mode badge, listed badge)
3. Click "Create site", enter name "E2E Site" and site id "e2e-site", submit
4. Verify redirect to `/admin/sites/{id}` with tabs Overview, Settings, Zones, Messages, Ingest keys
5. Verify the site id field is read-only and the badge says "Shadow"

**Expected:** `POST /admin/sites` returns 201; site is unmanaged and unlisted.

### Test 2: Managed Toggle Confirmation
1. On the overview tab switch "Managed" on
2. **Screenshot:** confirmation naming that pushes will be sent and the legacy ParkIT notifier must be off
3. Cancel; verify the switch is still off. Switch on again and confirm; verify the badge says "Managed"

### Test 3: Settings Validation
1. Open the Settings tab
2. Set "Reset occupancy" to the same value as "Trigger occupancy", click Save
3. Verify the inline message that reset must be lower than trigger and that no request was sent
4. Add a notification window with start 22:00, end 02:00; verify the "start must be before the end" message
5. Fix the values (reset 80, window 06:00-10:00), Save, verify success toast; reload and verify values persist
6. Remove all windows, Save; verify "No window set" text (any time)

### Test 4: Zones
1. Open the Zones tab, click "Add zone", enter name "Basement 9", zone id "b9", Save
2. Verify the zone appears in display order
3. Edit it: set advisory percentage 90, save; verify "90%" shown
4. For a discovered zone (created by an ingest), verify the "New - needs review" badge and click "Mark reviewed"; verify the badge disappears
5. Delete the zone via the confirmation dialog

### Test 5: Message Templates
1. Open the Messages tab
2. In the "Parking filling up" editor click the `{occupancyPct}` placeholder; verify it is inserted and the preview shows "92"
3. Type `{fullZone}` into the body; verify the "Placeholder not available" warning and Save disabled
4. Remove it, Save, verify success; click "Reset to default", confirm, verify default wording returns

### Test 6: Ingest Keys
1. Open the Ingest keys tab; verify the rotation explanation is shown
2. Click "Create key", name "E2E key", submit
3. **Screenshot:** dialog showing the key once with a Copy button; click Copy and verify the toast
4. Close; verify the key appears with its hint and status "Active", last used "Never used"
5. Click Revoke, confirm; verify status "Revoked" and no Revoke button on that row

### Test 7: Read-only for Viewer
1. Login as viewer; navigate to `/admin/sites` and open a site
2. Verify no "Create site", Save, Delete, "Add zone", Revoke or "Create key" controls exist on any tab and inputs are disabled

### Test 8: App Keys (super admin)
1. Login as super admin, navigate to `/platform-admin/app-keys`
2. Create a key "E2E app key"; verify it is shown once; revoke it
3. As an administrator who is not a super admin, verify `/platform-admin/app-keys` redirects away

## Success Criteria
- All steps behave as described; validation errors are shown inline; server errors (`detail_code`) are shown translated
