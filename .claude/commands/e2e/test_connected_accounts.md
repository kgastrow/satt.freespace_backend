# E2E Test: Connected Accounts

## Test Description
Validate the connected accounts page for viewing and managing SSO connections.

## User Story
As a user
I want to view my connected third-party accounts
So that I can manage my SSO authentication methods

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user:
  - Email: user@example.com
  - Password: UserPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Connected Accounts Page

**Steps:**
1. Log in as user
2. Navigate to `/settings/account/connected`
3. **Screenshot:** Connected accounts page
4. Verify page loads correctly
5. Verify page title displayed

**Expected Results:**
- Page loads successfully
- Page accessible from settings
- Title shows "Connected Accounts"

### Test 2: View Coming Soon State

**Steps:**
1. Navigate to connected accounts page
2. **Screenshot:** Coming soon placeholder
3. Verify placeholder message displayed
4. Verify indicates feature under development

**Expected Results:**
- Coming soon message visible
- Professional placeholder design
- Clear communication of future feature

### Test 3: Navigate via Settings Sidebar

**Steps:**
1. Go to Settings page
2. **Screenshot:** Settings sidebar
3. Click on "Connected Accounts" in Account section
4. Verify navigation to correct page
5. Verify sidebar shows active state

**Expected Results:**
- Link visible in sidebar
- Navigation works
- Active state indicated

### Test 4: Mobile Navigation

**Steps:**
1. View on mobile viewport
2. Open settings menu
3. **Screenshot:** Mobile settings menu
4. Navigate to Connected Accounts
5. Verify page loads on mobile

**Expected Results:**
- Accessible on mobile
- Menu navigation works
- Page responsive

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/sso/connections` | Get user's SSO connections (future) |

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page heading | `getByRole('heading', { name: /connected accounts/i })` |
| Coming soon message | Placeholder text element |
| Settings sidebar | Navigation component |
| Account section | Settings category |
| Connected accounts link | Navigation link |

## Success Criteria

- Page loads without errors
- Coming soon placeholder displayed
- Navigation from settings works
- Mobile responsive
- i18n translations work

## Notes

- Feature is currently a placeholder ("Coming Soon")
- Future implementation will include:
  - List of connected SSO providers
  - Connect/disconnect functionality
  - Provider icons and status
- Test will need expansion when feature is implemented
- Verify placeholder is properly translated

