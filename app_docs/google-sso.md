# Google SSO with Extensible Provider Architecture

**ADW ID:** 20260109151928-0378ff45 | **Date:** 2026-01-09 | **Specification:** specs/multi-phase/issue-94-adw-20260109151928-0378ff45-multi-phase.md

Adds Google SSO with extensible provider architecture for easy integration of future providers. Super admins enable/disable SSO per organization; frontend dynamically renders enabled provider buttons.

## Technical Implementation

### Backend Files

**Models & CRUD:**
- `app/backend/src/models/organization_sso_settings.py`: OrganizationSSOSettings model with one-to-one relationship to Organization
- `app/backend/alembic/versions/d22e02935a16_add_organizationssosettings_model.py`: Database migration
- `app/backend/src/crud/organization_sso_settings.py`: CRUD operations with multi-tenancy support
- `app/backend/src/serialisers/organization_sso_settings.py`: Pydantic serializers

**Services:**
- `app/backend/src/services/sso/base.py`: Abstract BaseSSOProvider class with three required methods: `get_authorization_url()`, `exchange_code_for_tokens()`, `get_user_info()`
- `app/backend/src/services/sso/google.py`: Google OAuth 2.0 implementation
- `app/backend/src/services/sso/factory.py`: Factory pattern for provider instantiation
- `app/backend/src/core/config.py`: SSO configuration variables

**API:**
- `app/backend/src/api/sso.py`: OAuth authorization and callback endpoints
- `app/backend/src/api/organization_sso_settings.py`: Settings management endpoints

**Tests:**
- `app/backend/tests/unit_tests/test_organization_sso_settings.py`: Model and CRUD tests
- `app/backend/tests/service_tests/test_sso_service.py`: OAuth flow tests with mocked HTTP
- `app/backend/tests/api_tests/test_sso.py`: Endpoint tests
- `app/backend/tests/api_tests/test_organization_sso_settings.py`: Settings API tests

### Frontend Files

**State & API:**
- `app/frontend/src/features/auth/ssoApi.ts`: RTK Query endpoints
- `app/frontend/src/features/auth/authSlice.ts`: Auth state with SSO login flow
- `app/frontend/src/types/sso.ts`: SSO TypeScript types

**Components & Pages:**
- `app/frontend/src/components/sso/GoogleLoginButton.tsx`: Google-branded button
- `app/frontend/src/components/sso/SSOButtonGroup.tsx`: Dynamic provider button container
- `app/frontend/src/components/login-form.tsx`: Integrated SSO buttons
- `app/frontend/src/pages/OAuthCallback.tsx`: OAuth callback handler
- `app/frontend/src/router.tsx`: `/oauth/callback` route

**Tests:**
- `app/frontend/src/tests/SSOButtonGroup.test.tsx`: Component rendering tests
- `app/frontend/src/tests/ssoApi.test.tsx`: RTK Query integration tests

### Documentation
- `docs/sso-configuration.md`: Google SSO setup guide
- `ai_docs/backend/context/sso.md`: Backend architecture
- `ai_docs/frontend/context/sso.md`: Frontend patterns

## Key Architecture Decisions

**Extensible Provider Pattern**: BaseSSOProvider abstract class allows new providers by implementing three methods. New providers (Microsoft, GitHub, SAML) require minimal changes.

**Multi-Tenant Integration**: SSO settings scoped per organization. OAuth state parameter encodes organization context for CSRF protection and tenant routing. Automatic user provisioning: creates new users if email doesn't exist, links to existing users in same organization. SSO users get `email_verified` flag and generated secure password.

**Dynamic UI**: Frontend fetches enabled providers and conditionally renders buttons. Login form only shows SSO section when providers available.

**Security**: CSRF protection via cryptographically secure state token (JWT-encoded, 10-minute expiration). Rate limiting on SSO endpoints. Production requires HTTPS and encrypted client secret storage.

## Usage

### End Users
1. Click "Sign in with Google" on login page (if enabled)
2. Authenticate with Google account
3. Auto-login (new users auto-provisioned with Google email)

### Super Admins
Enable Google SSO via API:
```bash
curl -X PUT https://your-api.com/api/organization-sso-settings \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "google_enabled": true,
    "google_client_id": "your-client-id.apps.googleusercontent.com",
    "google_client_secret": "your-client-secret"
  }'
```

Get enabled providers:
```bash
curl https://your-api.com/api/organization-sso-settings \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Developers
Implement BaseSSOProvider for new providers:
```python
from src.services.sso.base import BaseSSOProvider

class MicrosoftSSOProvider(BaseSSOProvider):
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        # Generate Microsoft OAuth URL
        pass

    async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        # Exchange code for tokens
        pass

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        # Get user profile
        pass
```

Then register in factory pattern.

## Configuration

### Environment Variables
```bash
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REDIRECT_URI=http://localhost:5173/oauth/callback
```

Or via `config.json`:
```json
{
  "sso": {
    "google_client_id": "your-client-id.apps.googleusercontent.com",
    "google_client_secret": "your-client-secret",
    "google_redirect_uri": "http://localhost:5173/oauth/callback"
  }
}
```

### Google Cloud Console
1. Create OAuth 2.0 credentials
2. Configure authorized redirect URIs:
   - Dev: `http://localhost:5173/oauth/callback`
   - Prod: `https://yourdomain.com/oauth/callback`
3. Copy Client ID and Secret to backend config

See `docs/sso-configuration.md` for detailed setup.

## Testing

**Backend:**
```bash
cd app/backend && make test
```
Coverage: Model/CRUD unit tests, OAuth flow service tests, API endpoint tests, multi-tenancy isolation tests.

**Frontend:**
```bash
cd app/frontend && npm run test
```
Coverage: RTK Query integration, component rendering, OAuth callback handling.

**Manual E2E:**
1. `cd app/backend && make dev`
2. `cd app/frontend && npm run dev`
3. Enable Google SSO via API
4. Test login flow and token storage

## Future Enhancements

- SAML-based SSO for enterprise customers
- Admin UI for SSO settings management
- Audit logging for SSO login events
- Multiple SSO providers per organization
- JIT user provisioning with custom attribute mapping
- SSO-specific user roles and permissions
