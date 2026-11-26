# E2E Test: 404 Not Found Page

## Test Description
Validate that the 404 Not Found page displays correctly when users navigate to non-existent routes, with proper messaging and navigation options.

## User Story
As a user
I want to see a helpful error page when I navigate to a non-existent page
So that I understand the page doesn't exist and can easily navigate back

## Prerequisites
- Backend server running
- Frontend dev server running
- Authenticated user session (for protected routes)

## Test Steps

### Test 1: Navigate to Non-Existent Route

**Steps:**
1. Login as user
2. Navigate to a non-existent route: `/this-page-does-not-exist`
3. **Screenshot:** 404 page displayed
4. Verify 404 page is shown
5. Verify "404" heading is displayed
6. Verify error description is shown
7. Verify page has proper styling

**Expected Results:**
- 404 page displays for non-existent routes
- "404" text is prominent
- User-friendly error message shown
- Page is properly styled

### Test 2: 404 Page Content

**Steps:**
1. Navigate to non-existent route
2. **Screenshot:** 404 page content
3. Verify page displays:
   - "404" number prominently
   - Title text (e.g., "Page Not Found")
   - Description text explaining the error
   - Navigation buttons
4. Verify text is translated (i18n)

**Expected Results:**
- All content elements present
- Text is clear and helpful
- Proper i18n translations used
- Translation keys: `errors:notFound.title`, `errors:notFound.description`

### Test 3: "Go Home" Button

**Steps:**
1. Navigate to non-existent route
2. Locate "Go Home" button
3. **Screenshot:** Go Home button
4. Click "Go Home" button
5. Verify redirect to home/dashboard (`/`)
6. **Screenshot:** Home page after redirect
7. Verify navigation works correctly

**Expected Results:**
- "Go Home" button is visible
- Click navigates to root path
- User lands on appropriate page
- No errors during navigation

### Test 4: "Go Back" Button

**Steps:**
1. Navigate to dashboard
2. Navigate to a non-existent route
3. Locate "Go Back" button
4. **Screenshot:** Go Back button
5. Click "Go Back" button
6. Verify redirect to previous page (dashboard)
7. **Screenshot:** Previous page after redirect
8. Verify browser history navigation works

**Expected Results:**
- "Go Back" button is visible
- Click navigates to previous page
- Uses browser history (`navigate(-1)`)
- Works correctly with history

### Test 5: Direct URL Access to 404

**Steps:**
1. Copy a non-existent URL
2. Open new browser tab
3. Paste and navigate directly to non-existent URL
4. **Screenshot:** 404 on direct access
5. Verify 404 page displays
6. Verify "Go Back" works (may behave differently with no history)
7. Verify "Go Home" works

**Expected Results:**
- Direct URL access shows 404
- Page works without history
- Navigation options still functional

### Test 6: 404 for Authenticated Routes (Unauthenticated)

**Steps:**
1. Logout or use incognito browser
2. Navigate to a protected but non-existent route
3. **Screenshot:** Behavior for unauthenticated user
4. Verify appropriate response:
   - Either 404 page
   - Or redirect to login first
5. Verify no sensitive information exposed

**Expected Results:**
- Unauthenticated users handled appropriately
- May redirect to login for protected routes
- No information leakage

### Test 7: 404 with Query Parameters

**Steps:**
1. Navigate to non-existent route with query params: `/not-found?param=value`
2. **Screenshot:** 404 with query params
3. Verify 404 page displays
4. Verify query parameters don't cause issues
5. Verify "Go Home" still works

**Expected Results:**
- Query parameters don't break 404 handling
- Page displays correctly
- Navigation still works

### Test 8: 404 with Special Characters in URL

**Steps:**
1. Navigate to URL with special characters: `/page/with spaces and special@chars!`
2. **Screenshot:** 404 with special characters
3. Verify 404 page displays
4. Verify page handles URL encoding correctly
5. Verify no JavaScript errors

**Expected Results:**
- Special characters handled gracefully
- No errors or crashes
- 404 page still displays

### Test 9: 404 Page Accessibility

**Steps:**
1. Navigate to 404 page
2. Check page with accessibility tools
3. **Screenshot:** Accessibility check
4. Verify:
   - Heading hierarchy is correct
   - Buttons are focusable
   - Keyboard navigation works
   - Screen reader friendly
5. Tab through page elements
6. Verify focus order is logical

**Expected Results:**
- Page meets accessibility standards
- Keyboard navigation works
- Screen reader can read content
- Focus management is correct

### Test 10: 404 Page on Mobile

**Steps:**
1. Set viewport to mobile size
2. Navigate to non-existent route
3. **Screenshot:** Mobile 404 page
4. Verify page is responsive
5. Verify buttons are touchable (min 44px)
6. Verify text is readable
7. Verify no horizontal scroll

**Expected Results:**
- 404 page is mobile responsive
- All elements properly sized
- Touch targets adequate
- Layout adapts to small screen

### Test 11: Nested Non-Existent Route

**Steps:**
1. Navigate to deeply nested non-existent route: `/admin/settings/this/does/not/exist`
2. **Screenshot:** Nested 404
3. Verify 404 page displays
4. Verify same 404 handling regardless of depth
5. Verify navigation buttons work

**Expected Results:**
- Deep routes handled correctly
- Same 404 experience
- Routing catches all undefined paths

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| - | - | No API calls for 404 page (client-side routing) |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| 404 heading | `getByRole('heading', { name: /404/i })` |
| Page title | `getByRole('heading', { name: /not found|page not found/i })` |
| Description | `getByText(/page.*exist|couldn't find/i)` |
| Go Home button | `getByRole('button', { name: /go home/i })` or `getByRole('link', { name: /go home/i })` |
| Go Back button | `getByRole('button', { name: /go back/i })` |

## Success Criteria

- 404 page displays for all non-existent routes
- "404" is prominently displayed
- Error message is clear and helpful
- "Go Home" navigates to root
- "Go Back" navigates to previous page
- Page is properly translated (i18n)
- Page is accessible
- Page is responsive on mobile
- No errors with special characters in URL

## Notes

- Verify catch-all route is configured in router
- Test with React Router error boundaries if applicable
- Verify 404 doesn't expose sensitive route information
- Consider adding "Report broken link" option
- Verify page title updates for SEO/bookmarks
- Test with browser extensions that might interfere
