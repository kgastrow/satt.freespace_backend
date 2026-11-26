# Frontend SSO Implementation

## Overview

Frontend SSO provides OAuth-based authentication via external providers (currently Google).

**Two-tier admin UI:**
- **Super admin**: Toggles `sso_allowed` on Organizations page (`/admin/organizations`)
- **Org admin**: Configures providers on SSO Settings page (`/admin/sso/settings`) when `sso_allowed=true`

## Key Files

```
src/
├── features/auth/ssoApi.ts       # RTK Query endpoints
├── components/sso/
│   ├── GoogleLoginButton.tsx     # Google SSO button with initiation
│   └── SSOButtonGroup.tsx        # Renders enabled provider buttons
├── pages/
│   ├── OAuthCallback.tsx         # Handles OAuth redirect + linking detection
│   ├── SSOConfirmLinkPage.tsx    # Account linking confirmation UI
│   └── admin/SSOSettingsPage.tsx # Org admin configuration
└── types/sso.ts                  # SSO types (re-exports from generated + manual types)
```

## Session Storage Keys

SSO uses sessionStorage to persist state across OAuth redirects:

| Key | Purpose | Set By | Cleared By |
|-----|---------|--------|------------|
| `sso_provider` | Provider name (e.g., `'google'`) | `GoogleLoginButton` before redirect | `OAuthCallback` after callback |
| `sso_return_url` | Return URL after login (validated) | `GoogleLoginButton` if AuthGuard provided `from` | `OAuthCallback` after reading |
| `sso_link_token` | Link token for account linking | `OAuthCallback` when linking required | `SSOConfirmLinkPage` after linking |

## Types

Types re-exported from generated OpenAPI: `OrganizationSSOSettings`, `UpdateOrganizationSSOSettingsRequest`, `EnabledProvidersResponse`, `SetSSOAllowedRequest`.

Manual types in `src/types/sso.ts`:

```typescript
export type SSOProvider = 'google'

export interface SSOAuthorizationResponse {
  authorization_url: string
}

export interface SSOCallbackSuccessResponse {
  access_token: string  // Refresh token is in httpOnly cookie, not in response
}

export interface SSOLinkingRequiredResponse {
  requires_linking: true
  link_token: string
  email: string
  provider: string
}

export interface SSOCallback2FARequiredResponse {
  requires_2fa: true
  two_factor_token: string
}

export type SSOCallbackResponse =
  | SSOCallbackSuccessResponse
  | SSOLinkingRequiredResponse
  | SSOCallback2FARequiredResponse

// Generated from the OpenAPI schema, NOT hand-written:
// export type ConfirmLinkRequest = components['schemas']['ConfirmLinkRequest']
//   -> { link_token: string; password?: string | null }

// Type guards. Check 2FA FIRST - see below.
export function isSSOTwoFactorRequired(response: SSOCallbackResponse): response is SSOCallback2FARequiredResponse
export function isSSOLinkingRequired(response: SSOCallbackResponse): response is SSOLinkingRequiredResponse
```

### Type Guard Usage

Use `isSSOLinkingRequired()` to discriminate the union type after callback:

```typescript
import { isSSOLinkingRequired } from '@/types/sso'

const result = await handleCallback({ provider, code, state }).unwrap()

if (isSSOLinkingRequired(result)) {
  // TypeScript knows: result is SSOLinkingRequiredResponse
  sessionStorage.setItem('sso_link_token', result.link_token)
  navigate('/sso/confirm-link', {
    state: { email: result.email, provider: result.provider },
  })
  return
}

// TypeScript knows: result is SSOCallbackSuccessResponse
dispatch(setCredentials({ token: result.access_token }))
```

## RTK Query API

**Endpoints in `src/features/auth/ssoApi.ts`:**

| Hook | Purpose | Key Parameters |
|------|---------|----------------|
| `useGetSSOSettingsQuery` | Current org's SSO settings | none |
| `useUpdateSSOSettingsMutation` | Update org's SSO settings | `UpdateOrganizationSSOSettingsRequest` |
| `useGetEnabledSSOProvidersQuery` | Get enabled providers for login | `{ orgSlug: string }` |
| `useLazyInitiateSSOLoginQuery` | Get authorization URL (lazy) | `{ provider: SSOProvider, orgSlug: string }` |
| `useLazyHandleSSOCallbackQuery` | Exchange code for tokens (lazy) | `{ provider: SSOProvider, code: string, state: string }` |
| `useConfirmAccountLinkMutation` | Confirm SSO account linking | `ConfirmLinkRequest` - `{ link_token, password? }`. `password` is omitted when the user is already authenticated (the bearer token is the proof) and required when they are not. |
| `useGetOrgSSOSettingsQuery` | Get any org's settings (super admin) | `{ organizationId: string }` |
| `useSetSSOAllowedMutation` | Toggle `sso_allowed` (super admin) | `{ organizationId: string, ssoAllowed: boolean }` |

**Endpoint URLs with orgSlug:**

```typescript
// Get enabled providers - requires orgSlug
getEnabledSSOProviders: builder.query<EnabledProvidersResponse, { orgSlug: string }>({
  query: ({ orgSlug }) => ({
    url: '/organization-sso-settings/enabled-providers',
    params: { org_slug: orgSlug },
  }),
})

// Initiate SSO login - requires orgSlug
initiateSSOLogin: builder.query<SSOAuthorizationResponse, { provider: SSOProvider; orgSlug: string }>({
  query: ({ provider, orgSlug }) => ({
    url: `/sso/${provider}/authorize`,
    params: { org_slug: orgSlug },
  }),
})
```

**Note:** `initiateSSOLogin` and `handleSSOCallback` use lazy variants since they trigger redirects.

## OAuth Flow

### Standard Flow
1. User clicks "Continue with Google" on login page
2. `GoogleLoginButton` stores provider in sessionStorage, validates/stores return URL if from AuthGuard
3. Backend returns `authorization_url`, browser redirects to Google
4. Google redirects to `/oauth/callback?code=X&state=Y`
5. `OAuthCallback` retrieves provider from sessionStorage, exchanges code for tokens
6. **`isSSOTwoFactorRequired(result)` is checked FIRST.** SSO does not skip local
   2FA: a 2FA-enrolled account gets `{ requires_2fa: true, two_factor_token }`,
   which dispatches `set2FARequired` and navigates to `/login` to collect the
   code. Skipping this check stores an `undefined` token and signs the user
   out - unrecoverable for an SSO-only account.
7. Otherwise `isSSOLinkingRequired(result)` -> the linking flow below
8. Otherwise: access token stored in Redux via `setCredentials`, refresh token in
   httpOnly cookie
9. Navigate to validated return URL (default: `/dashboard`)

### Account Linking Flow (SSO email matches existing user)
1. Steps 1-5 same as standard flow
2. Backend returns `{ requires_linking: true, link_token, email, provider }`
3. `OAuthCallback` stores `link_token` in sessionStorage, navigates to `/sso/confirm-link`
4. `SSOConfirmLinkPage` shows the email/provider and, when the user is **not**
   already signed in, a required password field - the backend needs proof of the
   existing account, not just the link token
5. On confirm, calls `useConfirmAccountLinkMutation` with `{ link_token }` when
   authenticated (the bearer token is the proof) or `{ link_token, password }`
   when signed out
6. Backend creates identity link, returns tokens; navigate to `/dashboard`

**Note:** Link tokens expire in 5 minutes and are single-use. A rejected password
does **not** consume the token, so the user can retype it - but guesses are
capped (see Troubleshooting).

## Component Patterns

### SSOButtonGroup
- Takes `organizationSlug` prop, fetches enabled providers
- Returns `null` if no providers enabled, shows `Skeleton` during loading

### GoogleLoginButton
- Takes `organizationSlug` prop, uses `useLazyInitiateSSOLoginQuery`
- Stores provider in sessionStorage before redirect
- Validates return URL with `getSafeRedirectPath()` before storing

### OAuthCallback
- Retrieves provider from sessionStorage (not URL params)
- Uses `isSSOLinkingRequired()` type guard to check response
- Validates return URL with `getSafeRedirectPath()` before navigation

### SSOConfirmLinkPage

Handles account linking confirmation when SSO email matches existing user:

```typescript
// Reads link token from sessionStorage (set by OAuthCallback)
const linkToken = sessionStorage.getItem('sso_link_token')

// Gets email/provider from navigation state (passed by OAuthCallback)
const state = location.state as { email?: string; provider?: string } | null

// Redirect to login if no link token (page refreshed, etc.)
useEffect(() => {
  if (!linkToken) navigate('/login')
}, [linkToken, navigate])

// A signed-in caller proves control with their bearer token, so the password
// field is only rendered (and only sent) when `isAuthenticated` is false.
const isAuthenticated = useAppSelector((s) => s.auth.isAuthenticated)

// On confirm, call mutation and handle success
const handleConfirmLink = async () => {
  const payload: ConfirmLinkRequest = isAuthenticated
    ? { link_token: linkToken }
    : { link_token: linkToken, password }
  const result = await confirmLink(payload).unwrap()
  sessionStorage.removeItem('sso_link_token')
  sessionStorage.removeItem('sso_provider')
  dispatch(setCredentials({ token: result.access_token }))
  // Fetch user data, then navigate to /dashboard
}

// On cancel, clear storage and return to login
const handleCancel = () => {
  sessionStorage.removeItem('sso_link_token')
  sessionStorage.removeItem('sso_provider')
  navigate('/login')
}
```

### SSOSettingsPage
- Checks `sso_allowed` first - shows alert if disabled
- Uses `usePermission('organization')` for write access
- Client secret field clears after save (never displays existing)

## Error Handling

Use `getErrorMessage()` from `@/types/api` for safe, i18n-aware error messages:

```typescript
import { getErrorMessage } from '@/types/api'
import { useTranslation } from 'react-i18next'

const { t } = useTranslation(['backend'])

try {
  await confirmLink({ link_token: linkToken }).unwrap()
} catch (error) {
  // Safe extraction with i18n support
  const errorMsg = getErrorMessage(error, t)
  setError(errorMsg)
  // Or use toast: toast.error(errorMsg, { category: 'auth' })
}
```

`getErrorMessage()` handles:
- API errors with `detail_code` (translated via backend namespace)
- Validation error arrays (HTTP 422)
- String detail messages
- Non-API errors (Error instances, unknown)

## Security Requirements

1. **State validation**: Backend handles CSRF state - frontend just passes through
2. **Token storage**: Access token in Redux (in-memory), refresh token in httpOnly cookie
3. **Redirect URI**: Backend controls redirect URI - never construct OAuth URLs client-side
4. **Error messages**: Use `getErrorMessage()` for safe user-facing messages
5. **Return URL validation (SEC-F-004)**: Use `getSafeRedirectPath()` from `@/lib/url-validation` to validate any stored return URLs before redirecting after OAuth

```typescript
// In OAuthCallback.tsx
import { getSafeRedirectPath } from '@/lib/url-validation'

const storedReturnUrl = sessionStorage.getItem('sso_return_url')
sessionStorage.removeItem('sso_return_url')
const returnUrl = getSafeRedirectPath(storedReturnUrl, '/dashboard')
navigate(returnUrl)
```

## Adding a New Provider

1. Add to `SSOProvider` type in `src/types/sso.ts`
2. Create `<Provider>LoginButton.tsx` component with provider branding
3. Add conditional render in `SSOButtonGroup.tsx`
4. Backend must support the provider endpoint

## Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| "SSO not enabled" | Provider not enabled for org | Check super admin enabled SSO, verify org slug |
| Infinite redirect | Callback processing failure | Check code/state extraction, verify redirect URI |
| "Invalid state" | State expired/malformed | State expires in 10min, check for double URL-encoding |
| Buttons not showing | No enabled providers | Check network for API response, verify org has SSO |
| 404 on settings | SSO not configured | Super admin must enable SSO first |
| "Link token expired" | User took >5min to confirm | Restart SSO flow from login |
| "Link token already used" | Token was already consumed | Restart SSO flow from login |
| Missing link_token | sessionStorage cleared | User refreshed page during linking flow |
| 403 `auth.invalid_password` | Password proof rejected | Retype the password; the link token is still valid |
| 401 `sso.link_proof_required` | No proof sent (stale client, or SSO-only account with no password) | Sign in to the existing account first, then link |
| 429 `sso.link_attempts_exceeded` / `auth.ip_blocked` | Too many wrong passwords for this token/account/IP | Restart the SSO flow, or sign in normally and link from the app |
| 503 `sso.link_verification_unavailable` | Redis unavailable - the replay guard fails closed | Retry; escalate if it persists |
| Session expired message | Provider not in sessionStorage | User opened callback URL directly or refreshed |

## Best Practices

- Use RTK Query hooks for all SSO API calls
- Always check `sso_allowed` before showing provider config
- Provider is stored in sessionStorage, not passed in URL
- Navigate to `/dashboard` after successful SSO (not `/`)
- Use `getErrorMessage(error, t)` for all user-facing error messages
- Always pass `orgSlug` to SSO endpoints that require it
