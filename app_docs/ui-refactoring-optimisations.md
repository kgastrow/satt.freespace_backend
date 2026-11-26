# UI Refactoring Optimisations

**ADW ID:** 20260120110510-d2a599e6 | **Date:** 2026-01-20 | **Spec:** specs/multi-phase/issue-192-adw-20260120110510-d2a599e6-multi-phase.md

## Overview

Centralizes permission checking, navigation, routes, auth state, and styles via data-driven configuration. Improves UI changeability by replacing scattered patterns with consistent abstractions while maintaining backward compatibility.

## Implementation

**6 Phases:**
1. Permission service (centralized with `hasPermission()`, `hasAnyPermission()`, `hasAllPermissions()`, `canAccess()`, `isSuperAdmin()`, `isImpersonating()`)
2. Auth abstraction (camelCase properties with backward-compatible snake_case)
3. Style presets (semantic Tailwind utilities)
4. Navigation configuration (data-driven with permission filtering)
5. Navigation renderer (AppSidebar refactored; AdminSidebar, PlatformAdminSidebar pending)
6. Route configuration (admin routes from config with auto-wrapping of AuthGuard, PermissionGate, Suspense)

### Files Created

- `app/frontend/src/lib/permissions.ts` - Permission service
- `app/frontend/src/hooks/usePermissions.ts` - Permission hook wrapper
- `app/frontend/src/hooks/useCurrentUser.ts` - User access hook
- `app/frontend/src/lib/styles.ts` - Style presets (layout, text, interactive, animation)
- `app/frontend/src/config/navigation.ts` - Navigation for main/admin/platform-admin
- `app/frontend/src/hooks/useNavigation.ts` - Permission-filtered navigation hook
- `app/frontend/src/config/routes.ts` - Route metadata with permissions
- `app/frontend/src/lib/route-generator.tsx` - Route generation utilities
- `app/frontend/src/lib/index.ts` - Central exports

### Files Modified

- `app/frontend/src/hooks/useAuth.ts` - Added camelCase + computed properties
- `app/frontend/src/hooks/usePermission.ts` - Uses permission service
- `app/frontend/src/hooks/index.ts` - New hook exports
- `app/frontend/src/components/AppSidebar.tsx` - Data-driven navigation
- `app/frontend/src/router.tsx` - Admin routes from config

## Usage

### Permission Checking
```typescript
import { usePermissions } from '@/hooks'

const { hasPermission, hasAnyPermission, hasAllPermissions, canAccess, isSuperAdmin } = usePermissions()

if (hasPermission('users:write')) { /* show edit button */ }
if (hasAnyPermission(['users:read', 'users:write'])) { /* show section */ }
if (hasAllPermissions(['api_keys:read', 'api_keys:write'])) { /* show API keys */ }
if (canAccess(['admin:access'], { requireAll: false })) { /* show admin link */ }
```

### Auth State
```typescript
import { useAuth, useCurrentUser } from '@/hooks'

const { user, isAuthenticated } = useAuth()
console.log(user?.fullName, user?.isAdmin, user?.organizationId) // camelCase + computed

const currentUser = useCurrentUser() // Simplified access
```

### Navigation Configuration
```typescript
// config/navigation.ts
export const mainNavigation: NavSection[] = [{
  id: 'main',
  title: 'common:sidebar.navigation',
  items: [
    { id: 'dashboard', title: 'common:navigation.dashboard', url: '/dashboard', icon: LayoutDashboard },
    { id: 'reports', title: 'common:navigation.reports', url: '/reports', icon: FileText, permissions: ['reports:read'] }
  ]
}]

// In components
const { sections, isSuperAdmin } = useNavigation('main') // Pre-filtered by permissions
```

### Route Configuration
```typescript
// config/routes.ts
export const adminRoutes: RouteConfig[] = [{
  path: 'users',
  component: lazy(() => import('@/pages/admin/UsersPage')),
  permissions: ['users:read', 'users:write', 'users:delete'],
  requireAll: false,
  requireAuth: true,
  layout: 'admin',
  title: 'admin:users.title'
}]

// router.tsx
const router = createBrowserRouter([{
  path: 'admin',
  element: <AdminLayout />,
  children: generateRoutes(adminRoutes)
}])
```

### Style Utilities
```typescript
import { layout, text, interactive } from '@/lib/styles'

<div className={layout.page}>
  <h1 className={text.h1}>Title</h1>
  <button className={interactive.button}>Click</button>
</div>

// Presets: layout (flexCenter, flexBetween, flexCol, stack, row, grid, page, section, card, panel)
// text (h1-h4, body, muted, label, error) | interactive (clickable, focusRing, disabled) | animation (fadeIn, slideIn)
```

## Configuration

No environment variables required. Works with existing auth/permission state.

### Extending Navigation
```typescript
export const mainNavigation: NavSection[] = [{
  id: 'main',
  items: [{
    id: 'new-feature',
    title: 'common:navigation.newFeature',
    url: '/new-feature',
    icon: NewIcon,
    permissions: ['feature:access'],
    badge: 'notification-count'
  }]
}]
```

### Adding Routes
```typescript
export const adminRoutes: RouteConfig[] = [
  ...existingRoutes,
  {
    path: 'new-page',
    component: lazy(() => import('@/pages/admin/NewPage')),
    permissions: ['permission:required'],
    requireAuth: true,
    layout: 'admin',
    title: 'admin:newPage.title'
  }
]
```

## Testing
```bash
cd app/frontend
npm run test && npm run lint && npm run build:only
```

**Manual Checklist:** Permission checks (role-based show/hide) | Navigation filtering (items per permissions) | Auth state (camelCase + backward compat) | Route access (unauthorized redirect) | Impersonation (super admin disabled) | Style presets (light/dark modes)

## Status & Notes

**Completed:** Phases 1-4, 6 (Phase 5 partially complete - AppSidebar done, AdminSidebar/PlatformAdminSidebar pending)

**Remaining:** Migrate AdminSidebar/PlatformAdminSidebar, remaining route groups (settings, platform admin), i18n keys for navigation, NavRenderer component

**Backward Compatibility:** Old `usePermission` hook works, snake_case auth properties available, hardcoded navigation works, old routes functional

**Incremental Adoption:** Style presets alongside inline Tailwind, navigation/routes/permission checks migratable per section

**Performance:** Navigation filtering memoized, permission service uses Redux selectors, route generation at definition-time, style strings static for Tailwind JIT

**Architecture Benefits:** Single source of truth | Type-safe | Unit-testable pure functions | Discoverable config files | Config-based maintenance | Consistent patterns | Extensible (badges, dividers, external links)
