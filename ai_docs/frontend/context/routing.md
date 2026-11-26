# React Router Patterns

React Router v7 with layout-based architecture. Routes defined in `app/frontend/src/router.tsx`.

**CRITICAL: Routes must be REGISTERED, not just defined.** Routes must be explicitly added to `createBrowserRouter()` in `router.tsx`.

## RouteConfig System

The app uses a config-driven route system for admin routes. This decouples route definitions from permission checks.

**Files:**
- `config/routes.ts` - Route metadata (path, component, permissions, title)
- `lib/route-generator.tsx` - Converts config to React Router RouteObjects

### RouteConfig Interface

```typescript
interface RouteConfig {
  path: string                    // Route path (e.g., '/admin/users')
  component: ComponentType        // Lazy-loaded component
  permissions?: string[]          // Required permissions (OR logic by default)
  requireAll?: boolean            // If true, requires ALL permissions
  requireAuth?: boolean           // If true, requires authentication
  guestOnly?: boolean             // If true, redirects authenticated users
  layout?: 'root' | 'dashboard' | 'admin' | 'platform-admin'
  title?: string                  // i18n key for page title
  breadcrumb?: string             // i18n key for breadcrumb
}
```

### Route Generation

`generateRoutes()` converts RouteConfig arrays to React Router RouteObjects, auto-wrapping with guards:

```typescript
// config/routes.ts
export const adminRoutes: RouteConfig[] = [
  {
    path: '/admin/users',
    component: UsersPage,
    requireAuth: true,
    permissions: ['users:read', 'users:write'],
    title: 'admin:users.title',
  },
]

// router.tsx - Usage
import { adminRoutes } from '@/config/routes'
import { generateRoutes } from '@/lib/route-generator'

{
  path: 'admin',
  element: <AdminLayout />,
  children: [
    ...generateRoutes(adminRoutes).map((route) => ({
      path: route.path?.replace(/^\/admin\//, ''),  // Strip prefix
      element: route.element,
    })),
  ],
}
```

**Guard wrapping order:** AuthGuard -> PermissionGate -> Suspense -> Component

### lazyNamed Helper

For components using named exports (not `export default`):

```typescript
const lazyNamed = <T extends ComponentType>(
  importFn: () => Promise<Record<string, T>>,
  name: string
) => lazy(() => importFn().then((m) => ({ default: m[name] as T })))

// Usage
const UsersPage = lazyNamed(() => import('@/pages/admin/UsersPage'), 'UsersPage')
```

## Navigation

| Method | Use Case |
|--------|----------|
| `Link` | Standard navigation: `<Link to="/dashboard">` |
| `NavLink` | Menu with active styling: `className={({ isActive }) => ...}` |
| `useNavigate` | Programmatic: `navigate('/dashboard')`, `navigate(-1)` |

## Route Parameters

```typescript
// URL params: /users/:id
const { id } = useParams<{ id: string }>()

// Query params: ?page=1&search=foo
const [searchParams, setSearchParams] = useSearchParams()
const page = parseInt(searchParams.get('page') || '1')
```

## Route Guards

Location: `app/frontend/src/components/`

| Guard | Purpose | Props |
|-------|---------|-------|
| `AuthGuard` | Authentication | `requireAuth` (default true), `redirectTo` |
| `PermissionGate` | Permission-based access | `permission`, `requireAll`, `redirectTo`, `fallback` |
| `SuperAdminGuard` | Super admin only | `redirectTo` (default '/dashboard') |

**IMPORTANT: Always use `PermissionGate` for admin routes - never check roles directly (roles are dynamic).**

### AuthGuard

```typescript
// Protected route (default)
<AuthGuard><DashboardPage /></AuthGuard>

// Guest-only route
<AuthGuard requireAuth={false} redirectTo="/dashboard"><LoginPage /></AuthGuard>
```

### PermissionGate

```typescript
// Route-level with redirect
<PermissionGate permission="users:read" redirectTo="/dashboard">
  <UsersPage />
</PermissionGate>

// Multiple permissions (ANY by default, ALL with requireAll)
<PermissionGate permission={['users:read', 'users:write']} requireAll redirectTo="/dashboard">
  <EditUserPage />
</PermissionGate>

// Inline use (hide UI element)
<PermissionGate permission="users:write" fallback={null}>
  <CreateUserButton />
</PermissionGate>
```

### Impersonation Behavior

All route guards respect impersonation state:
- **PermissionGate**: Super admin bypass disabled during impersonation
- **SuperAdminGuard**: Blocks access during impersonation
- **Navigation**: Admin items hidden based on impersonated user's permissions

## Layout Pattern

Layouts use `<Outlet />` to render children:

```typescript
export function DashboardLayout() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-6"><Outlet /></main>
    </div>
  )
}
```

### Self-Guarding Layouts

**`PlatformAdminLayout` includes `SuperAdminGuard` internally.** Do NOT wrap it in additional guards:

```typescript
// CORRECT - Layout handles its own guard
{ path: 'platform-admin', element: <PlatformAdminLayout />, children: [...] }

// WRONG - Redundant guard
{ path: 'platform-admin', element: <SuperAdminGuard><PlatformAdminLayout /></SuperAdminGuard> }
```

**Note:** `AdminLayout` does NOT include its own guard. Admin routes use `PermissionGate` via `generateRoutes()`.

## Route Organization

| File | Purpose |
|------|---------|
| `router.tsx` | Main route definitions, lazy imports |
| `routes/settingsRoutes.tsx` | Settings pages (spread into router) |
| `config/routes.ts` | Admin route configuration with metadata |
| `lib/route-generator.tsx` | Generates RouteObjects from config |

## Best Practices

- Use layouts with nested `<Outlet />` for shared UI
- Centralize routes in `router.tsx`
- Use `Link`/`NavLink` for internal links, never `<a>`
- Type params: `useParams<{ id: string }>()`
- Include `path: '*'` catch-all route for 404
- Lazy load all page components with `React.lazy()`
- Prefer RTK Query hooks over React Router loaders for data fetching
- Add new admin routes to `config/routes.ts` (not directly to router.tsx)
