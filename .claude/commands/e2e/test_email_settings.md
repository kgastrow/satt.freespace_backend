# E2E Test: Email Settings

## Test Description
Validate that administrators can configure email provider settings for their organization.

## User Story
As an organization administrator
I want to configure email settings
So that my organization can send emails through our preferred provider

## Prerequisites
- Backend server running
- Frontend dev server running
- Admin user with email_settings:write permission:
  - Email: admin@example.com
  - Password: AdminPassword123!
  - Organization: test-org
- User is authenticated (use `/setup_test_auth`)

## Test Steps

### Test 1: Navigate to Email Settings Page

**Steps:**
1. Log in as admin
2. Navigate to `/admin/email/settings`
3. **Screenshot:** Email settings page
4. Verify page loads correctly
5. Verify provider selection visible

**Expected Results:**
- Page loads successfully
- Current configuration shown
- Provider options visible

### Test 2: View Available Providers

**Steps:**
1. Navigate to email settings
2. **Screenshot:** Provider options
3. Verify three providers available:
   - Default (platform default)
   - SMTP (custom SMTP server)
   - SendGrid (SendGrid API)
4. Verify current selection highlighted

**Expected Results:**
- All providers shown
- Current provider selected
- Descriptions for each option

### Test 3: Select Default Provider

**Steps:**
1. Select "Default" provider option
2. **Screenshot:** Default selected
3. Verify no additional fields shown
4. Click "Save Settings"
5. Verify success notification

**Expected Results:**
- Default option selectable
- No credential fields needed
- Uses platform default configuration

### Test 4: Configure SMTP Provider

**Steps:**
1. Select "SMTP" provider option
2. **Screenshot:** SMTP fields appear
3. Verify fields shown:
   - SMTP Host
   - SMTP Port
   - Username
   - Password
   - Use TLS toggle
   - Use SSL toggle
4. Fill in SMTP configuration:
   - Host: smtp.example.com
   - Port: 587
   - Username: smtp-user
   - Password: smtp-password
   - TLS: enabled
5. **Screenshot:** SMTP configured
6. Click "Save Settings"

**Expected Results:**
- SMTP fields visible
- All required fields editable
- Configuration saved

### Test 5: Configure SendGrid Provider

**Steps:**
1. Select "SendGrid" provider option
2. **Screenshot:** SendGrid fields appear
3. Verify API key field shown
4. Enter SendGrid API key
5. **Screenshot:** SendGrid configured
6. Click "Save Settings"
7. Verify success notification

**Expected Results:**
- SendGrid option selectable
- API key field shown
- Key saved successfully

### Test 6: Configure Sender Branding

**Steps:**
1. Configure any provider
2. Find sender branding section
3. **Screenshot:** Sender branding fields
4. Enter sender email: "noreply@example.com"
5. Enter sender name: "My Organization"
6. Enter reply-to email: "support@example.com"
7. Click "Save Settings"

**Expected Results:**
- Sender fields visible
- All fields editable
- Branding saved with provider

### Test 7: View Effective Configuration

**Steps:**
1. Save email settings
2. **Screenshot:** Effective configuration
3. Verify shows which provider is active
4. Verify shows sender information
5. Verify credentials masked

**Expected Results:**
- Active provider displayed
- Sender info shown
- Passwords/keys masked

### Test 8: Send Test Email

**Steps:**
1. Configure email settings
2. Save settings
3. Click "Send Test Email" button
4. **Screenshot:** Test email dialog
5. Enter test recipient email
6. Click "Send"
7. **Screenshot:** Test result
8. Verify success or error message

**Expected Results:**
- Test email button available
- Can enter recipient
- Email sent or error shown
- Clear feedback

### Test 9: Reset to Platform Default

**Steps:**
1. Configure custom email settings
2. Click "Reset to Default" button
3. **Screenshot:** Reset confirmation
4. Confirm reset
5. **Screenshot:** After reset
6. Verify settings cleared
7. Verify using platform default

**Expected Results:**
- Reset button available
- Confirmation required
- Settings reverted
- Platform default restored

### Test 10: Validation - SMTP Port Range

**Steps:**
1. Select SMTP provider
2. Enter port: 0
3. **Screenshot:** Invalid port error
4. Verify validation error
5. Enter port: 70000
6. Verify validation error
7. Enter port: 587
8. Verify accepted

**Expected Results:**
- Port 0 rejected
- Port > 65535 rejected
- Valid ports accepted
- Error messages clear

### Test 11: Validation - Required Fields

**Steps:**
1. Select SMTP provider
2. Leave Host empty
3. Click "Save Settings"
4. **Screenshot:** Validation errors
5. Verify error for required fields
6. Fill required fields
7. Verify can save

**Expected Results:**
- Required fields enforced
- Error messages shown
- Cannot save without required

### Test 12: Permission Check

**Steps:**
1. Log in as user without email_settings:write
2. Navigate to `/admin/email/settings`
3. **Screenshot:** Permission denied
4. Verify cannot access

**Expected Results:**
- Access denied
- Redirect or error page
- Settings not visible

## API Endpoints Tested

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/email-settings` | Get org email settings |
| GET | `/email-settings/effective` | Get effective configuration |
| PUT | `/email-settings` | Update email settings |
| POST | `/email-settings/test` | Send test email |
| DELETE | `/email-settings` | Reset to platform defaults |

## Request/Response Format

**Get Email Settings Response:**
```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "provider": "smtp",
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_username": "user",
  "smtp_use_tls": true,
  "smtp_use_ssl": false,
  "sender_email": "noreply@example.com",
  "sender_name": "My Organization",
  "reply_to_email": "support@example.com"
}
```

**Update Email Settings Request:**
```json
{
  "provider": "smtp",
  "smtp_host": "smtp.example.com",
  "smtp_port": 587,
  "smtp_username": "user",
  "smtp_password": "password",
  "smtp_use_tls": true,
  "smtp_use_ssl": false,
  "sender_email": "noreply@example.com",
  "sender_name": "My Organization",
  "reply_to_email": "support@example.com"
}
```

**Test Email Request:**
```json
{
  "recipient_email": "test@example.com"
}
```

## Test Selectors

| Element | Selector Strategy |
|---------|------------------|
| Page heading | `getByRole('heading', { name: /email settings/i })` |
| Provider select | Select component for provider |
| Default option | Provider option for "default" |
| SMTP option | Provider option for "smtp" |
| SendGrid option | Provider option for "sendgrid" |
| SMTP Host input | `getByLabelText(/smtp host/i)` |
| SMTP Port input | `getByLabelText(/smtp port/i)` |
| SMTP Username | `getByLabelText(/username/i)` |
| SMTP Password | `getByLabelText(/password/i)` |
| TLS toggle | Switch for smtp_use_tls |
| SSL toggle | Switch for smtp_use_ssl |
| SendGrid API key | `getByLabelText(/api key/i)` |
| Sender email | `getByLabelText(/sender email/i)` |
| Sender name | `getByLabelText(/sender name/i)` |
| Reply-to email | `getByLabelText(/reply.*to/i)` |
| Save button | `getByRole('button', { name: /save/i })` |
| Test email button | `getByRole('button', { name: /test/i })` |
| Reset button | `getByRole('button', { name: /reset/i })` |
| Success toast | Toast notification |

## Success Criteria

- Email settings page loads for authorized users
- All three providers selectable
- SMTP configuration works
- SendGrid configuration works
- Sender branding configurable
- Test email functionality works
- Reset to defaults works
- Validation prevents invalid input
- Passwords/keys are masked
- Permission check enforced

## Notes

- Credentials are masked in API responses
- Test with valid and invalid email addresses
- Verify TLS/SSL mutual exclusion if applicable
- Check i18n for all labels
- Test email may require actual SMTP/SendGrid setup
- Verify error handling for failed test emails

