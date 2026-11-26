# Super Admin User Impersonation (Frontend)

Allows super admins to view the application as a specific user would see it.

## Key Files

| File | Purpose |
|------|---------|
| `src/features/impersonation/impersonationApi.ts` | RTK Query endpoints |
| `src/features/impersonation/impersonationSlice.ts` | Redux state |
| `src/features/impersonation/impersonationSelectors.ts` | Memoized selectors |
| `src/hooks/useImpersonation.ts` | Main hook for start/end operations |
| `src/hooks/usePermissions.ts` | Permission checks (includes `isSuperAdmin` with impersonation awareness) |
| `src/components/ImpersonationBanner.tsx` | Yellow banner during impersonation |

## API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /admin/impersonate/{userId}` | Start impersonation |
| `POST /admin/impersonate/end` | End impersonation |
| `POST /admin/impersonate/resume` | Resume after page refresh |
| `GET /admin/impersonate/session` | Check active session status |

## Redux State

Tokens are stored **in-memory only** (Redux). Refresh tokens use httpOnly cookies.

```typescript
interface ImpersonationState {
  isImpersonating: boolean
  sessionId: string | null
  sessionStartedAt: string | null
  // Legacy fields (not used for storage):
  originalUser: User | null
  targetUser: User | null
  originalToken: string | null
  originalRefreshToken: string | null
}
```

**Note**: During impersonation, `targetUser` is derived from `auth.user` (the impersonated user's data), not stored separately.

## useImpersonation Hook

```typescript
const {
  isImpersonating, targetUser, sessionId, sessionStartedAt,
  startImpersonation, endImpersonation,
  isStarting, isEnding, startError, endError
} = useImpersonation()
```

## Flows

### Starting Impersonation

1. `POST /admin/impersonate/{userId}` returns impersonation token
2. `setCredentials({ token: impersonation_token })`
3. Invalidate `['User', 'UserPermissions']` tags
4. `refetchCurrentUser()` and `refetchPermissions()` in parallel

### Ending Impersonation

1. `POST /admin/impersonate/end` returns admin's access token
2. `setCredentials({ token: access_token })`
3. `clearImpersonation()`
4. Invalidate `['User', 'UserPermissions']` tags
5. `refetchCurrentUser()` and `refetchPermissions()` in parallel
6. Navigate to `/dashboard`

**CRITICAL**: Token must be updated BEFORE cache invalidation to avoid race conditions.

### Page Refresh Resume

1. AuthProvider calls `/auth/refresh` (admin's httpOnly cookie)
2. `fetchCurrentSession()` checks for active impersonation
3. If active: `resumeImpersonation()` gets new impersonation token
4. Re-fetch user data for impersonated user

## UI Behavior

### Admin Access Blocking

Super admin access is blocked during impersonation via `usePermissions` hook:

```typescript
const isSuperAdmin = user?.is_admin === true && !isImpersonating
```

Components using this pattern:
- `useNavigation` hook (filters admin nav sections)
- `PermissionGate` (super admin bypass disabled)
- `SuperAdminGuard` (blocks admin-only routes)

### Visual Indicators

- `ImpersonationBanner`: Fixed yellow banner at top with "End Impersonation" button
- `RootLayout`: Yellow ring border around viewport (`ring-4 ring-yellow-500`)

### RTK Query Cache

- `startImpersonation`: Has `invalidatesTags: ['User', 'UserPermissions']`
- `endImpersonation`: NO `invalidatesTags` - handled manually in hook to avoid race condition

## Troubleshooting

| Issue | Checks |
|-------|--------|
| Admin nav showing during impersonation | `isImpersonating` true in Redux? `usePermissions().isSuperAdmin` returns false? |
| Still impersonated user after ending | Token updated before cache invalidation? `refetchCurrentUser()` called? |
| Impersonation state lost on refresh | `/admin/impersonate/session` returns active? `resumeImpersonation` called? |

## Testing

```typescript
const store = createTestStore({
  impersonation: { isImpersonating: true, sessionId: 'test-session' },
  auth: { user: targetUser }
})
```

Test files:
- `src/tests/ImpersonationBanner.test.tsx`
- `src/tests/impersonationSlice.test.tsx`
- `src/tests/impersonation.integration.test.tsx`
