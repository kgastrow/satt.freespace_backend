# Frontend Security

## Critical Rules

| NEVER | ALWAYS |
|-------|--------|
| Store auth tokens in localStorage/sessionStorage | Use httpOnly cookies for refresh tokens, Redux for access tokens |
| Log credentials/tokens to console | Validate forms with Zod schemas |
| Trust user input without validation | Use `useAuth` hook for auth operations |
| Skip route protection for authenticated pages | Use `AuthGuard` for protected routes |
| Use `dangerouslySetInnerHTML` without DOMPurify | Sanitize HTML with strict DOMPurify config |
| Store passwords for "remember me" | Handle errors with `getErrorMessage(error, t)` |
| Pass tokens in URL query parameters | Send WebSocket auth tokens in first message |
| Open external URLs without validation | Use `safeOpenDownloadUrl()` for S3/external URLs |

## Token Storage (SEC-F-001)

| Token | Storage | Reason |
|-------|---------|--------|
| Access Token | Redux state (in-memory) | Never persisted, cleared on page refresh |
| Refresh Token | httpOnly cookie | Invisible to JavaScript, immune to XSS theft |

- Cookie set by backend: `httponly`, `secure`, `samesite=lax`, path `/api/v1/auth`
- `baseQueryWithReauth` in `@/store/api.ts` handles 401 refresh transparently
- `AuthProvider` validates tokens and resumes sessions on app load

## Content Security Policy (SEC-F-007)

CSP configured via meta tag in `index.html`:

```html
<meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self' data:; connect-src 'self' wss: ws: https:; frame-ancestors 'none'; base-uri 'self'; form-action 'self';" />
```

**Key directives:**
- `frame-ancestors 'none'` - prevents clickjacking
- `connect-src 'self' wss: ws: https:` - allows WebSocket and API calls
- `img-src 'self' data: blob: https:` - allows external images over HTTPS (deliberate choice for user avatars, external content)

**Production CSP Migration:**
Meta tags have limitations vs HTTP headers:
- Cannot use nonces (requires server-side generation per request)
- `report-uri`/`report-to` directives are ignored
- Some browsers may not support all directives

For production, move CSP to HTTP headers (nginx/reverse proxy) to enable nonce-based script validation and CSP violation reporting.

## Error Handling

```typescript
import { getErrorMessage, isApiError } from '@/types/api'

// With i18n support (recommended)
const { t } = useTranslation(['backend'])
const errorMsg = getErrorMessage(error, t)  // Uses detail_code for translation

// Without i18n
const errorMsg = getErrorMessage(error)  // Falls back to English detail
```

Global `ErrorBoundary` catches unhandled errors with retry and reload options.

## Security Checklists

### Auth-Protected Features
- Wrap route with `AuthGuard`
- Handle `isLoading` state and unauthenticated redirect
- Test with expired token scenario

### Auth Forms
- Zod schema matching backend validation
- Disable form during submission + loading state on button
- Show errors via toast, never log credentials
- Use proper `autoComplete` attributes

### Sensitive Data
- Never store passwords, don't expose tokens in URLs
- Clear sensitive data on logout

## XSS / CSRF Prevention

| Attack | Prevention |
|--------|------------|
| XSS | Avoid `dangerouslySetInnerHTML`. If needed, sanitize with DOMPurify. React escapes by default. |
| CSRF | JWT in Authorization header (not cookies) - inherently CSRF-resistant. Refresh tokens use `samesite=lax` cookies. |

### DOMPurify Configuration (SEC-F-006)

```typescript
import DOMPurify from 'dompurify'

// Add hook for safe external links
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A' && node.getAttribute('target') === '_blank') {
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

const sanitized = DOMPurify.sanitize(rawHtml, {
  ADD_ATTR: ['target'],
  ALLOW_DATA_ATTR: false,
})

DOMPurify.removeHook('afterSanitizeAttributes')  // Clean up after use
```

**Never allow:** `iframe`, `allow`, `allowfullscreen`, `frameborder` attributes in user content.

## URL Validation (SEC-F-004, SEC-F-011)

Utilities in `@/lib/url-validation.ts`:

### Redirect Path Validation (Two-Tier Approach)

```typescript
import { getSafeRedirectPath, isValidRedirectPath, isAllowedRedirectPath } from '@/lib/url-validation'

// Tier 1: Basic validation - accepts any safe relative path
isValidRedirectPath('/any/internal/path')  // true - just validates format

// Tier 2: Strict validation - only allows paths in ALLOWED_REDIRECT_PATHS whitelist
isAllowedRedirectPath('/dashboard')  // true - in whitelist
isAllowedRedirectPath('/random/path')  // false - not in whitelist

// Helper that falls back to default on invalid
const returnUrl = getSafeRedirectPath(storedReturnUrl, '/dashboard')
```

**When to use which:**
- `isValidRedirectPath`: General navigation, any internal path is acceptable
- `isAllowedRedirectPath`: Post-auth redirects where you want to restrict to known sections (`/dashboard`, `/settings`, `/admin`, `/profile`, `/files`, `/notifications`, `/help`)

Format checks: starts with `/`, not `//`, no protocol, no encoded traversal (`%2f`, `%5c`, `%00`), no backslashes.

### Download URL Validation

```typescript
import { safeOpenDownloadUrl, isValidDownloadUrl } from '@/lib/url-validation'

if (!safeOpenDownloadUrl(downloadUrl)) {
  toast.error('Invalid download URL')
}
```

Checks: HTTPS only (except localhost), same-origin or allowed S3 domains (`*.s3.amazonaws.com`, `*.s3.*.amazonaws.com`), blocks `javascript:`, `data:`, `vbscript:` protocols.

## WebSocket Security (SEC-F-005)

Tokens sent in first message after connection, **not** in URL query parameter:

```typescript
// WRONG - exposes token in browser history and logs
const ws = new WebSocket(`${WS_URL}?token=${token}`)

// CORRECT - see useWebSocket.ts
const ws = new WebSocket(wsUrl)
ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }))
// Wait for { type: 'auth_success' } before fully connected
```

## External Links (SEC-F-008)

All external links must use `noopener,noreferrer`:

```typescript
<a href={url} target="_blank" rel="noopener noreferrer">

window.open(url, '_blank', 'noopener,noreferrer')
```

Prevents reverse tabnabbing and referer header exposure.

## localStorage Usage

**Safe uses (non-sensitive data):**
- `i18nextLng` - User's language preference
- Onboarding dismissal flags
- UI preferences (theme, sidebar state)

**Never store:** Auth tokens, session data, PII, or anything that could be exploited via XSS.
