# Google SSO Configuration Guide

This guide provides step-by-step instructions for configuring Google Single Sign-On (SSO) authentication in your application.

## Prerequisites

- Google Cloud Platform account
- Super admin access to your application
- Access to your application's backend configuration

## Google Cloud Console Setup

### 1. Create OAuth 2.0 Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create a project
3. Navigate to **APIs & Services** → **Credentials**
4. Click **Create Credentials** → **OAuth client ID**
5. Configure the OAuth consent screen if prompted:
   - User Type: External (for testing) or Internal (for organization-only access)
   - Application name: Your application name
   - User support email: Your support email
   - Authorized domains: Your application domain
   - Developer contact information: Your email

### 2. Configure OAuth Client

1. Application type: **Web application**
2. Name: `[Your App Name] - Production` (or environment-specific name)
3. **Authorized JavaScript origins:**
   - `https://yourdomain.com` (production)
   - `http://localhost:5173` (local development)
4. **Authorized redirect URIs:**
   - `https://yourdomain.com/oauth/callback` (production)
   - `http://localhost:5173/oauth/callback` (local development)
5. Click **Create**
6. Copy the **Client ID** and **Client Secret** - you'll need these for configuration

### 3. Enable Google+ API (Optional)

While not strictly required, enabling the Google+ API provides richer user profile data:
1. Navigate to **APIs & Services** → **Library**
2. Search for "Google+ API"
3. Click **Enable**

## Backend Configuration

Add the following environment variables to your backend configuration:

### Using config.json

Add to your `config.json`:

```json
{
  "sso": {
    "google_client_id": "your-client-id.apps.googleusercontent.com",
    "google_client_secret": "your-client-secret",
    "google_redirect_uri": "http://localhost:5173/oauth/callback"
  }
}
```

### Using Environment Variables

Alternatively, set these environment variables:

```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5173/oauth/callback
```

**Note:** The redirect URI must exactly match one of the authorized redirect URIs configured in Google Cloud Console.

## Enable SSO for Your Organization

As a super admin, enable Google SSO for your organization:

### Via API

```bash
curl -X PUT https://your-api.com/api/organization-sso-settings \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "google_enabled": true,
    "google_client_id": "your-client-id.apps.googleusercontent.com",
    "google_client_secret": "your-client-secret"
  }'
```

### Via Admin UI

SSO configuration uses a two-tier permission system:

#### Step 1: Super Admin - Allow SSO for Organization

1. Navigate to Super Admin → Organizations (`/admin/organizations`)
2. Find the organization in the table
3. Toggle the "SSO Allowed" switch to enable SSO for that organization

#### Step 2: Org Admin - Configure SSO Provider

Once SSO is allowed for the organization:

1. Navigate to Administration → SSO Settings (`/admin/sso/settings`)
2. Toggle "Enable Google SSO"
3. Enter Client ID and Client Secret
4. Click "Save Settings"

**Note:** Organization owners and admins can only configure SSO if a super admin has first allowed SSO for their organization.

## Testing Locally

### 1. Start the Backend

```bash
cd app/backend
make dev
```

Backend should be running on `http://localhost:8000`

### 2. Start the Frontend

```bash
cd app/frontend
npm run dev
```

Frontend should be running on `http://localhost:5173`

### 3. Test the Login Flow

1. Navigate to `http://localhost:5173/login`
2. You should see a "Sign in with Google" button
3. Click the button
4. Select a Google account
5. Grant permissions
6. You should be redirected back and logged in

### Expected Behavior

**New Users:**
- User account created automatically using Google email
- Email is marked as verified
- User is added to your organization
- JWT tokens issued

**Existing Users:**
- If email matches existing user in your organization, that user is logged in
- If email exists in another organization, login fails (users cannot belong to multiple organizations)

## Production Deployment

### 1. Update Redirect URI

Update your backend configuration for production:

```json
{
  "sso": {
    "google_redirect_uri": "https://yourdomain.com/oauth/callback"
  }
}
```

### 2. Update Google Cloud Console

Add production redirect URI to authorized redirect URIs:
- `https://yourdomain.com/oauth/callback`

### 3. Security Considerations

**HTTPS Required:**
- Google OAuth requires HTTPS in production
- Use valid SSL certificates
- Ensure redirect URIs use `https://`

**Client Secret Security:**
- Store client secrets securely (use environment variables or secrets management)
- Never commit secrets to version control
- Rotate credentials periodically
- Consider using encrypted database storage for per-organization credentials

**CSRF Protection:**
- The OAuth state parameter is automatically handled for CSRF protection
- State includes the organization context to ensure proper tenant isolation

### 4. Rate Limiting

All SSO endpoints (`/sso/{provider}/authorize`, `/sso/{provider}/callback` and
`POST /auth/sso/link`) carry `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` -
`100/minute` by default, per client IP as resolved by `src/core/client_ip.py`.
Adjust it under `rate_limit.default` in `config.json`.

The password proof on `POST /auth/sso/link` carries its own, much tighter caps on
top: 5 guesses per link token, 10 per target account per 15 minutes, plus the
shared per-IP block. Over the cap it answers `429 sso.link_attempts_exceeded`
(or `auth.ip_blocked`) without burning the link token.

## Troubleshooting

### "Redirect URI mismatch" Error

**Cause:** The redirect URI in your request doesn't match Google Cloud Console configuration.

**Solution:**
1. Check the redirect URI in backend config matches exactly (including protocol and port)
2. Ensure the URI is added to "Authorized redirect URIs" in Google Cloud Console
3. No trailing slashes - `http://localhost:5173/oauth/callback` not `/oauth/callback/`

### Google Button Not Appearing

**Cause:** SSO is not enabled for the organization or backend configuration is missing.

**Solution:**
1. Verify backend configuration has Google credentials
2. Verify super admin has enabled Google SSO for the organization
3. Check browser console for API errors when fetching enabled providers

### "User already exists in another organization"

**Cause:** The Google email matches a user in a different organization.

**Solution:**
- This is expected behavior for multi-tenancy
- Users can only belong to one organization
- User must use traditional login or contact support to move organizations

### OAuth Consent Screen Warnings

**Cause:** Your OAuth app is not verified by Google.

**Solution:**
1. For testing: Use "Test users" in OAuth consent screen (up to 100 users)
2. For production: Submit your app for verification if you need public access
3. For internal use: Set User Type to "Internal" (Google Workspace only)

## Multiple Environments

For managing multiple environments (dev, staging, production):

### Approach 1: Separate OAuth Clients

Create separate OAuth clients for each environment:
- `[App] - Development`
- `[App] - Staging`
- `[App] - Production`

Each with environment-specific redirect URIs.

### Approach 2: Single OAuth Client

Use one OAuth client with all redirect URIs:
- `http://localhost:5173/oauth/callback`
- `https://staging.yourdomain.com/oauth/callback`
- `https://yourdomain.com/oauth/callback`

**Note:** Approach 1 is recommended for better security and credential isolation.

## Next Steps

- Review the SSO architecture documentation in `ai_docs/backend/context/sso.md`
- Learn about adding additional SSO providers (Microsoft, GitHub, etc.)
- Configure organization-specific SSO settings via the admin UI
- Set up audit logging for SSO login events

## Additional Resources

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Google OAuth Scopes](https://developers.google.com/identity/protocols/oauth2/scopes)
- Backend SSO Implementation: `ai_docs/backend/context/sso.md`
- Frontend SSO Implementation: `ai_docs/frontend/context/sso.md`
