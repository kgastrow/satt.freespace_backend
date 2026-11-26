# Frontend Authentication

JWT-based auth with automatic token refresh, route protection, 2FA, SSO, and email verification.

## Key Files

| File | Purpose |
|------|---------|
| `src/components/AuthGuard.tsx` | Route protection component |
| `src/components/AuthProvider.tsx` | Auth bootstrap on app load |
| `src/features/auth/authSlice.ts` | Redux slice for auth state |
| `src/features/auth/authApi.ts` | RTK Query auth endpoints |
| `src/features/auth/authSelectors.ts` | Memoized auth selectors |
| `src/features/auth/ssoApi.ts` | RTK Query SSO endpoints |
| `src/hooks/useAuth.ts` | Auth hook for components |
| `src/types/auth.ts` | Auth TypeScript types |
| `src/store/authMiddleware.ts` | Logout side effects |
| `src/store/api.ts` | Base query with token refresh |
| `src/pages/OAuthCallback.tsx` | OAuth callback handler |

## Token Storage (SEC-F-001)

| Token | Storage | Reason |
|-------|---------|--------|
| Access Token | Redux state (in-memory only) | Never persisted, cleared on page refresh, immune to XSS |
| Refresh Token | httpOnly cookie | Invisible to JavaScript, set by backend with secure flags |

**Cookie configuration:**
- `httponly`: JavaScript cannot read it
- `secure`: HTTPS only (configurable for dev)
- `samesite=lax`: CSRF protection
- `path=/api/v1/auth`: Only sent to auth endpoints

**No storage keys** - tokens are not stored in localStorage/sessionStorage.

## Auth State Structure

```typescript
interface AuthState {
  user: User | null
  token: string | null           // Access token (in-memory only)
  isAuthenticated: boolean
  isLoading: boolean
  twoFactor: {
    required: boolean      // True when 2FA verification needed
    token: string | null   // Temporary token for 2FA verification
  }
  twoFactorSetupRequired: boolean  // True when user must set up 2FA
  enforcementActive: boolean       // True when org enforces 2FA
  sso: {
    isLoading: boolean
    error: string | null
    selectedProvider: string | null
  }
}

interface User {
  id: string
  email: string
  first_name: string
  last_name: string
  organization_id: string
  is_admin: boolean
  avatar_url?: string | null
  full_avatar_url?: string | null
  roles?: string[]
  permissions?: string[]
}
```

## Components

### AuthGuard

Protects routes based on authentication status.

```typescript
// Protected route (requires auth)
<AuthGuard>
  <DashboardPage />
</AuthGuard>

// Guest-only route (redirects if authenticated)
<AuthGuard requireAuth={false}>
  <LoginPage />
</AuthGuard>
```

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `requireAuth` | `boolean` | `true` | Require authentication |
| `redirectTo` | `string` | `/login` or `/` | Custom redirect path |

**HOC Wrapper**: `withAuthGuard<P>()` provides a higher-order component alternative.

### AuthProvider

Wraps app in `RootLayout.tsx`. On mount:

1. Attempts silent token refresh via httpOnly cookie
2. Validates token by fetching `/user/me`
3. Fetches user permissions from `/user/permissions`
4. Checks for active impersonation session via `/impersonation/current-session`
5. Initializes WebSocket listeners (notifications, feature flags, announcements, maintenance, exports)
6. Sets `isLoading: false` when complete
7. On error: silently clears auth state

### useAuth Hook

```typescript
const {
  user,                    // AuthUser with camelCase props (+ deprecated snake_case)
  token,
  isAuthenticated,
  isLoading,
  requiresTwoFactor,       // True when 2FA verification needed
  requiresTwoFactorSetup,  // True when user must set up 2FA
  login,                   // (credentials) => Promise
  logout,
  initAuth,
  isLoggingIn,
  isLoggingOut,
  loginError,
} = useAuth()
```

**Note:** `useAuth().user` returns `AuthUser` with both camelCase (`firstName`) and deprecated snake_case (`first_name`) properties.

## Login Flows

### Two-Step Login

1. User enters email
2. `POST /auth/check-email` returns `{ exists, auth_methods }`
3. Based on response:
   - `exists: false` -> Show "No account found"
   - `auth_methods` includes `"password"` -> Show password field
   - `auth_methods` includes SSO providers -> Show SSO buttons
   - Only SSO methods -> Show SSO with "This account uses SSO"

### Two-Factor Authentication

When 2FA is enabled, login returns a challenge:
```typescript
{ requires_2fa: true, two_factor_token: "temp-token" }
```

Flow:
1. Login with credentials
2. Server returns `requires_2fa: true` with temp token
3. Auth state sets `twoFactor.required = true`
4. UI shows 2FA form
5. User enters TOTP code
6. `authApi.verify2FA` exchanges temp token + code for JWT tokens

### SSO/OAuth Login

1. User selects SSO provider
2. `useLazyInitiateSSOLoginQuery` fetches authorization URL
3. User redirected to OAuth provider
4. Provider redirects to `/oauth/callback`
5. `OAuthCallback.tsx` extracts `code`, `state` from URL
6. Calls `/sso/{provider}/callback` to exchange for tokens
7. May return `requires_2fa` - SSO does **not** skip local 2FA. `OAuthCallback`
   checks `isSSOTwoFactorRequired()` FIRST, dispatches `set2FARequired` and
   navigates to `/login` for the code.
8. May require account linking (redirects to `/sso/confirm-link`, which asks a
   signed-out user for the existing account's password)

### Email Verification

After registration:
1. User receives verification email with OTP
2. `authApi.verifyEmailOTP` verifies code
3. Success: automatically logs user in (tokens returned)

## Automatic Token Refresh

Implemented in `src/store/api.ts`. On 401 response:

1. Check if impersonation session ended -> logout with `reason: 'impersonation-ended'`
2. Call `/auth/refresh` (cookie sent automatically)
3. Success: update token via `auth/updateToken`, retry original request
4. Failure with a **definitive** auth error (401/403, `isDefinitiveAuthFailure`):
   dispatch logout with `reason: 'session-expired'`
5. Failure with a **transient** error (network, 5xx): do NOT log out - retry the
   original request once and surface the error to the caller

## Auth Middleware

Handles logout side effects in `src/store/authMiddleware.ts`:

| Logout Reason | Behavior |
|--------------|----------|
| `'session-expired'` | Error toast, redirect to `/login` |
| `'impersonation-ended'` | Warning toast, redirect to `/login` |
| `'manual'` | No toast (component handles redirect) |
| `undefined` | Silent logout |

## Impersonation Support

Admins can impersonate users. During impersonation:
- Original admin token stored in sessionStorage (`original_token`)
- Current token is impersonated user's token
- Session restoration via cookie-based refresh + `/impersonation/current-session`
- External session end triggers `impersonation-ended` logout

**Security (SEC-F-003):** Impersonation state managed via API, original token in sessionStorage for session resume only.

## Security Rules

**Auth-protected features:**
- Wrap route with `AuthGuard`
- Handle `isLoading` state before rendering
- Test with expired token scenario

**Login/auth forms:**
- Use Zod schema matching backend validation
- Disable form during submission (`isLoggingIn`)
- Never log credentials
- Use proper `autoComplete` attributes

**Sensitive data:**
- Never store passwords or tokens in localStorage/sessionStorage
- Don't expose tokens in URLs (including WebSocket connections)
- Clear sensitive data on logout
- Validate return URLs after OAuth with `getSafeRedirectPath()` (SEC-F-004)

**Additional measures:**
- Access tokens in-memory only (Redux state)
- Refresh tokens in httpOnly cookies (invisible to JavaScript)
- Email verification enforced server-side
- 2FA token temporary storage in auth state (cleared after use)
- SSO error handling prevents token leakage
- WebSocket auth via first message, not URL query parameter

## Testing

Mock auth state via `preloadedState`:

```typescript
render(<DashboardPage />, {
  preloadedState: {
    auth: {
      user: {
        id: '1',
        email: 'test@test.com',
        first_name: 'Test',
        last_name: 'User',
        organization_id: 'org-1',
        is_admin: false,
        roles: ['user'],
        permissions: ['read:dashboard'],
      },
      token: 'test-token',
      isAuthenticated: true,
      isLoading: false,
      twoFactor: { required: false, token: null },
      twoFactorSetupRequired: false,
      enforcementActive: false,
      sso: { isLoading: false, error: null, selectedProvider: null },
    },
  },
})
```

## Troubleshooting

| Issue | Checks |
|-------|--------|
| Not authenticated after refresh | AuthProvider wrapping app? `/user/me` returning valid user? Cookie present? |
| Token refresh loop | Refresh token valid? Backend `/auth/refresh` working? |
| Login not redirecting | `useAuth().login()` awaited? `AuthGuard requireAuth={false}` on login page? |
| 2FA verification fails | Is `twoFactor.token` present? Is TOTP code correct? Check expiration. |
| SSO callback errors | Check `sso.error` state. Verify OAuth provider config. Check redirect URI. |
| Email verification fails | Is OTP expired? Check spam folder. Try `sendVerificationEmail`. |
