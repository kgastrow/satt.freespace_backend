# E2E Test: View Profile

## Test Description
Validate that authenticated users can view their profile information including personal details, avatar, organization info, roles, and account metadata.

## User Story
As an authenticated user
I want to view my profile information
So that I can see my account details and verify my information is correct

## Prerequisites
- Backend server running
- Frontend dev server running
- Test user exists with verified email:
  - Email: test@example.com
  - Password: TestPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: View Profile Page Loads Successfully

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for page to load
3. **Screenshot:** Profile page loaded
4. Verify page title "Profile" is displayed
5. Verify profile information card is visible
6. Verify account information card is visible

**Expected Results:**
- Profile page loads without errors
- User information is displayed correctly
- No loading spinners stuck on screen

### Test 2: Verify Personal Information Display

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for data to load
3. **Screenshot:** Personal information section
4. Verify first name field displays user's first name
5. Verify last name field displays user's last name
6. Verify email field displays user's email
7. Verify phone field displays user's phone (if set)

**Expected Results:**
- All personal information fields are populated
- Fields match the authenticated user's data
- Email field shows verified user's email

### Test 3: Verify Avatar Display

**Steps:**
1. Navigate to `/settings/account/profile`
2. Wait for profile to load
3. **Screenshot:** Avatar section
4. Verify avatar element is visible (data-testid="profile-avatar")
5. If user has no avatar, verify initials fallback is shown
6. If user has avatar, verify image is loaded

**Expected Results:**
- Avatar or initials placeholder is displayed
- Avatar image loads without errors (if present)
- Initials derived from user's name (if no avatar)

### Test 4: Verify Account Information Display

**Steps:**
1. Navigate to `/settings/account/profile`
2. Scroll to account information section
3. **Screenshot:** Account information section
4. Verify organization name is displayed
5. Verify user roles are displayed (as badges)
6. Verify account created date is shown

**Expected Results:**
- Organization name matches user's organization
- User roles displayed as badge components
- Account creation date formatted correctly

### Test 5: Verify Impersonation History Section (Conditional)

**Steps:**
1. Navigate to `/settings/account/profile`
2. Check if user has impersonation history
3. **Screenshot:** Impersonation history section (if visible)
4. If history exists, verify table displays:
   - Impersonator name/email
   - Start time
   - End time
   - Duration

**Expected Results:**
- Impersonation history section only shows if user has been impersonated
- Table data is formatted correctly
- Section hidden if no impersonation history

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/user/me` | Fetch current user profile |
| GET | `/user/permissions` | Fetch user permissions |
| GET | `/impersonate/my-history` | Fetch impersonation history |

## Request/Response Format

**Get User Response:**
```json
{
  "id": "uuid",
  "email": "test@example.com",
  "first_name": "Test",
  "last_name": "User",
  "phone": "+1234567890",
  "organization_id": "uuid",
  "is_admin": false,
  "avatar_url": "https://...",
  "created_time": "2024-01-01T00:00:00Z"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Profile avatar | `data-testid="profile-avatar"` |
| First name field | `input[name="firstName"]` or `getByLabelText(/first name/i)` |
| Last name field | `input[name="lastName"]` or `getByLabelText(/last name/i)` |
| Email field | `input[name="email"]` or `getByLabelText(/email/i)` |
| Phone field | `input[name="phone"]` or `getByLabelText(/phone/i)` |
| Role badges | `[class*="badge"]` within roles section |

## Success Criteria

- Profile page loads and displays user information
- All personal information fields show correct data
- Avatar displays correctly (image or initials)
- Account metadata (organization, roles, dates) is accurate
- Page is accessible and responsive
- Impersonation history shows only when applicable

## Notes

- Test with users that have and don't have avatars
- Verify i18n translations display correctly
- Check responsive layout on mobile viewport
- Ensure sensitive data is not exposed inappropriately
