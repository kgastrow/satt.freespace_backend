# E2E Test: Maintenance Page Display

## Test Description
Validate that the maintenance page displays correctly when the system is in maintenance mode, showing appropriate messaging, estimated end time, and auto-refresh behavior.

## User Story
As a user
I want to see a clear maintenance page when the system is unavailable
So that I understand why I can't access the application and when it might be back

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin access to enable maintenance mode
- Note: Most tests require maintenance mode to be active

## Test Steps

### Test 1: Maintenance Page Display

**Steps:**
1. Enable maintenance mode (Admin):
   - Message: "We're updating the system to serve you better."
   - Scheduled end: 2 hours from now
2. Attempt to access application as regular user
3. **Screenshot:** Maintenance page displayed
4. Verify maintenance page is shown instead of login/dashboard
5. Verify all key elements are present

**Expected Results:**
- Maintenance page displays for all regular users
- Page replaces normal application access
- Clean, professional appearance

### Test 2: Maintenance Page Content Elements

**Steps:**
1. Access application during maintenance mode
2. **Screenshot:** All page elements
3. Verify page displays:
   - Maintenance icon (alert/warning icon)
   - Title (e.g., "Under Maintenance" or translated)
   - Custom message from admin
   - Estimated end time (if provided)
   - Auto-refresh notice
4. Verify elements are properly styled

**Expected Results:**
- Alert icon visible (CircleAlert or similar)
- Title clearly indicates maintenance
- Custom message from admin displayed
- End time shown in readable format
- All text properly translated

### Test 3: Custom Maintenance Message

**Steps:**
1. Enable maintenance with custom message:
   - "System upgrade in progress. We apologize for the inconvenience."
2. Access as regular user
3. **Screenshot:** Custom message displayed
4. Verify exact message is shown
5. Disable maintenance
6. Enable with different message
7. Verify new message is displayed

**Expected Results:**
- Custom message displays exactly as entered
- Message updates when changed
- Default message shown if none provided

### Test 4: Default Maintenance Message

**Steps:**
1. Enable maintenance without custom message
2. Access as regular user
3. **Screenshot:** Default message displayed
4. Verify default message is shown
5. Verify message is translated (i18n key: `maintenance.defaultMessage`)

**Expected Results:**
- Default message displays when none configured
- Message is properly translated
- Message is helpful and professional

### Test 5: Estimated End Time Display

**Steps:**
1. Enable maintenance with scheduled end:
   - End time: 3 hours from now
2. Access as regular user
3. **Screenshot:** End time displayed
4. Verify end time is shown
5. Verify time is formatted for user's locale
6. Verify label (e.g., "Estimated completion:")
7. Verify timezone is appropriate

**Expected Results:**
- End time displayed when provided
- Formatted with Intl.DateTimeFormat
- Shows both date and time
- Respects user's locale settings

### Test 6: No End Time Display

**Steps:**
1. Enable maintenance without scheduled end
2. Access as regular user
3. **Screenshot:** No end time shown
4. Verify estimated end section is hidden or shows "Unknown"
5. Verify page still looks complete

**Expected Results:**
- End time section handles missing data gracefully
- Page layout not broken
- User not confused

### Test 7: Auto-Refresh Notice

**Steps:**
1. Access maintenance page
2. Locate auto-refresh notice
3. **Screenshot:** Auto-refresh notice
4. Verify notice indicates automatic refresh behavior
5. Verify translation (i18n key: `maintenance.autoRefresh`)
6. Wait for page to auto-refresh (observe network or UI)
7. Verify page refreshes periodically

**Expected Results:**
- Auto-refresh notice is visible
- Notice clearly explains behavior
- Page actually refreshes periodically
- Refresh doesn't lose user's place

### Test 8: Maintenance Page Styling

**Steps:**
1. Access maintenance page
2. **Screenshot:** Page styling
3. Verify styling:
   - Centered content
   - Appropriate spacing
   - Warning/alert color scheme (yellow/orange)
   - Card or container styling
   - Readable font sizes
4. Verify consistency with application design

**Expected Results:**
- Page is visually appealing
- Styling matches application theme
- Warning nature is clear (colors)
- Professional appearance

### Test 9: Maintenance Page on Mobile

**Steps:**
1. Set viewport to mobile size
2. Access maintenance page
3. **Screenshot:** Mobile maintenance page
4. Verify responsive layout:
   - Content fits screen
   - Text is readable
   - Icon appropriately sized
   - No horizontal scroll
5. Verify touch-friendly

**Expected Results:**
- Page is mobile responsive
- All content visible without scroll issues
- Layout adapts appropriately
- Touch interactions work

### Test 10: Maintenance Page Transitions

**Steps:**
1. Be on maintenance page
2. Wait for maintenance to end (Admin disables)
3. **Screenshot:** Transition away from maintenance
4. Verify page automatically redirects when maintenance ends
5. Verify redirect goes to appropriate page
6. Verify no manual refresh needed

**Expected Results:**
- Auto-refresh detects maintenance end
- Automatic redirect to application
- Smooth transition experience

### Test 11: Direct Navigation During Maintenance

**Steps:**
1. Enable maintenance mode
2. Try to navigate directly to: `/dashboard`
3. **Screenshot:** Redirect to maintenance
4. Verify redirect to maintenance page
5. Try to navigate to: `/settings`
6. Verify still shows maintenance page
7. Try to navigate to: `/admin` (if applicable)
8. Verify behavior based on permissions

**Expected Results:**
- All routes redirect to maintenance page
- No access to regular pages
- Consistent behavior across routes

### Test 12: Maintenance Page Accessibility

**Steps:**
1. Access maintenance page
2. Run accessibility check
3. **Screenshot:** Accessibility results
4. Verify:
   - Proper heading structure
   - Alt text for icon (if img)
   - Sufficient color contrast
   - Keyboard accessible
   - Screen reader friendly
5. Navigate with keyboard only
6. Verify all content reachable

**Expected Results:**
- Page meets accessibility standards
- Content readable by screen readers
- Keyboard navigation works
- Color contrast sufficient

### Test 13: Maintenance Page Language

**Steps:**
1. Access maintenance page with English locale
2. **Screenshot:** English maintenance page
3. Verify all text in English
4. Change language preference (if possible without full app access)
5. Refresh maintenance page
6. **Screenshot:** Different language
7. Verify translations apply to maintenance page

**Expected Results:**
- Maintenance page respects language settings
- All text translated correctly
- Language can be changed (if selector available)

### Test 14: Browser Refresh Behavior

**Steps:**
1. Access maintenance page
2. Note current state
3. Press F5 or click refresh
4. **Screenshot:** After manual refresh
5. Verify page reloads correctly
6. Verify state is maintained
7. Verify no errors

**Expected Results:**
- Page handles refresh correctly
- State persists
- No caching issues

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/maintenance/status` | Check maintenance status (for auto-refresh) |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Maintenance icon | `svg` icon or `img` with alt text |
| Title | `getByRole('heading')` or `getByText(/maintenance/i)` |
| Custom message | Text content in card |
| Estimated end time | Text with time/date |
| Auto-refresh notice | Text mentioning refresh |
| Card container | Card component wrapper |

## Success Criteria

- Maintenance page displays when mode is active
- Custom message from admin is shown
- Default message displays when none configured
- Estimated end time formatted correctly
- Auto-refresh notice is present
- Page auto-refreshes periodically
- Page is responsive on mobile
- Page is accessible
- Translations work correctly
- Automatic redirect when maintenance ends

## Notes

- Test auto-refresh interval (typically 30-60 seconds)
- Verify page doesn't cause excessive server requests
- Consider adding manual refresh button
- Test with very long maintenance messages
- Verify behavior when scheduled end passes
- Consider "Notify me when back" feature
- Test with maintenance mode WebSocket updates
