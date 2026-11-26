# Testing Patterns (Vitest + React Testing Library)

Vitest test runner with React Testing Library. MSW enabled globally.

## File Structure

| Location | Purpose |
|----------|---------|
| `Component.test.tsx` | Component tests (colocated with component) |
| `src/__tests__/integration/` | Integration tests (auth, tenant isolation, RBAC) |
| `src/test/utils.tsx` | Custom render, `createTestStore`, helpers |
| `src/test/setup.ts` | Global setup (MSW auto-started, mocks) |
| `src/test/server.ts` | MSW server, `setCurrentUser`, `setCurrentToken` |
| `src/test/handlers.ts` | MSW API handlers with handler state |
| `src/test/fixtures.ts` | User fixtures, `createAuthState`, test data |

## Custom Render

```typescript
import { render, screen, waitFor } from '@/test/utils'
import { createAuthState, regularUser } from '@/test/fixtures'

// Basic
const { user, store } = render(<MyComponent />)

// With auth state (use fixtures for consistency)
render(<MyComponent />, {
  preloadedState: createAuthState(regularUser),
})

// With routes (for navigation/redirect testing)
render(<MyComponent />, {
  route: '/users/123',
  routes: [
    { path: '/users/:id', element: <MyComponent /> },
    { path: '/dashboard', element: <Dashboard /> },
  ],
})
```

## MSW Handler State

MSW handlers maintain internal state to determine API responses. Use `setCurrentUser()` to control which user the API "sees":

```typescript
import { setCurrentUser } from '@/test/server'
import { adminUser, regularUser, createAuthState } from '@/test/fixtures'

it('admin sees all users', async () => {
  // setCurrentUser controls what /user/me and permission endpoints return
  // It also determines organization_id for tenant-scoped queries
  setCurrentUser(adminUser)

  // preloadedState sets Redux state (for usePermission, useAuth hooks)
  render(<UserList />, {
    preloadedState: createAuthState(adminUser),
  })
})
```

**Critical:** Components using `usePermission` need BOTH:
1. `setCurrentUser(user)` - Controls API responses (permissions endpoint returns `user.permissions`)
2. `preloadedState: createAuthState(user)` - Sets Redux state for hooks

Handler state resets automatically after each test via `resetHandlerState()` in setup.ts.

## Auth State Fixtures

Located in `src/test/fixtures.ts`:

```typescript
// Pre-configured users with different permission levels
import {
  regularUser,      // org-1, no permissions
  adminUser,        // org-1, users:read/write/delete, roles:read, etc.
  superAdminUser,   // org-1, is_admin: true (super admin)
  otherOrgUser,     // org-2, for tenant isolation tests
} from '@/test/fixtures'

// Create Redux auth state
createAuthState(regularUser)           // Authenticated with user
createAuthState(adminUser)             // Authenticated with admin
createUnauthenticatedState()           // Not authenticated
createLoadingAuthState()               // Auth loading state
```

## i18n Mock Behavior

The i18n mock in setup.ts returns **translation keys, not translations**:

```typescript
// setup.ts mocks useTranslation to return keys
t('common.save')           // Returns: 'common.save'
t('users.count', { n: 5 }) // Returns: 'users.count' (options ignored in return)

// Test assertions should check for KEYS
expect(screen.getByText('common.save')).toBeInTheDocument()  // Correct
expect(screen.getByText('Save')).toBeInTheDocument()         // Wrong - won't find it
```

## Utilities Reference

From `src/test/utils.tsx`:

| Function | Purpose |
|----------|---------|
| `render(ui, options)` | Custom render with Redux + Router |
| `createTestStore(preloadedState?)` | Create isolated Redux store |
| `waitForLoadingToComplete()` | Wait for `[class*="animate-pulse"]` elements to disappear |
| `waitForElementToBeRemoved(fn)` | Wait for element to leave DOM |
| `clearStorage()` | Clear localStorage and sessionStorage |
| `getCurrentPath()` | Get current router path (limited - check rendered content instead) |

From `src/test/server.ts`:

| Function | Purpose |
|----------|---------|
| `setCurrentUser(user)` | Set user for MSW handler responses |
| `setCurrentToken(token)` | Set auth token (null = unauthorized) |
| `resetHandlerState()` | Reset to default user/token (automatic) |
| `API_BASE` | Base URL for API (`http://localhost:8000/api/v1`) |

## Global Mocks (setup.ts)

These are mocked globally - no per-test setup needed:

| Mock | Behavior |
|------|----------|
| `localStorage` | Functional mock with `getItem`, `setItem`, `clear`, etc. Cleared between tests. |
| `sessionStorage` | Same as localStorage |
| `window.matchMedia` | Returns `{ matches: false }` for all queries |
| `ResizeObserver` | No-op mock |
| `react-i18next` | Returns translation keys (see i18n section) |
| MSW server | Auto-started, handlers reset after each test |

## Override Handlers

For specific test scenarios:
```typescript
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'

it('handles error', async () => {
  server.use(
    http.get(`${API_BASE}/files`, () => {
      return HttpResponse.json({ detail: 'Error' }, { status: 500 })
    })
  )
  // ...test error handling
})
```

## Hook Testing

```typescript
import { renderHook, waitFor } from '@testing-library/react'
import { createTestStore } from '@/test/utils'

function createWrapper() {
  const store = createTestStore()
  return ({ children }) => <Provider store={store}>{children}</Provider>
}

const { result } = renderHook(() => useMyHook(), { wrapper: createWrapper() })
await waitFor(() => expect(result.current.isSuccess).toBe(true))
```

## Query Priority

| Priority | Query | Use Case |
|----------|-------|----------|
| 1 | `getByRole` | Buttons, links, form elements |
| 2 | `getByLabelText` | Form fields |
| 3 | `getByText` | Non-interactive elements |
| 4 | `getByTestId` | Complex Radix components, dynamic content |

## Debugging

```typescript
screen.debug()                    // Print DOM
screen.logTestingPlaygroundURL()  // Get playground URL
```

## Best Practices

| Rule | Description |
|------|-------------|
| Use fixtures | Import users from `@/test/fixtures`, not inline objects |
| Match user in both places | `setCurrentUser` and `preloadedState` must use same user |
| Async with waitFor | Never use fixed timeouts |
| Test behavior | Focus on user actions, not implementation |
| Colocate tests | Keep `Component.test.tsx` next to `Component.tsx` |
| Integration tests | Put in `src/__tests__/integration/` |
| Expect i18n keys | Assertions check for translation keys, not actual text |

## Security Testing (Tenant Isolation)

Always test tenant isolation for data-scoped components:
```typescript
it('user only sees files from their organization', async () => {
  setCurrentUser(regularUser)  // org-1 user
  render(<FileList />, { preloadedState: createAuthState(regularUser) })

  await waitFor(() => expect(screen.queryByText('common.loading')).not.toBeInTheDocument())

  expect(screen.getByTestId('file-file-1')).toBeInTheDocument()      // org-1 file
  expect(screen.queryByTestId('file-file-3')).not.toBeInTheDocument() // org-2 file
})
```

## RBAC Testing

Test permission-based UI visibility:
```typescript
import { setCurrentUser } from '@/test/server'
import { adminUser, regularUser, createAuthState } from '@/test/fixtures'

it('shows delete button only for users with permission', async () => {
  // Admin has users:delete permission
  setCurrentUser(adminUser)
  render(<UserRow user={mockUser} />, {
    preloadedState: createAuthState(adminUser),
  })
  expect(screen.getByRole('button', { name: 'common.delete' })).toBeInTheDocument()
})

it('hides delete button from users without permission', async () => {
  // Regular user has no permissions
  setCurrentUser(regularUser)
  render(<UserRow user={mockUser} />, {
    preloadedState: createAuthState(regularUser),
  })
  expect(screen.queryByRole('button', { name: 'common.delete' })).not.toBeInTheDocument()
})
```
