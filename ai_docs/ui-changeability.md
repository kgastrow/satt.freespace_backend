# UI Changeability Guide

Guide for making radical UI changes (layout, flows, styling, components) with maximum first-pass success. Addresses architectural bottlenecks and provides refactoring strategies.

## Current Changeability Assessment

**Overall Score: 6/10** - Moderate effort required for radical changes.

| Change Type | Current Effort | After Refactoring |
|-------------|----------------|-------------------|
| Color palette/theming | Medium | Low |
| Component library swap | High | Medium |
| Layout restructure | Medium | Low |
| Navigation/flows | High | Low |
| Form patterns | High | Medium |
| State management | Very High | Medium |

---

## Bottleneck 1: Fragmented Permission Checks

### Problem

Four different patterns for checking permissions, used inconsistently across the codebase:

```typescript
// Pattern 1: Direct property check
user?.is_admin === true

// Pattern 2: String matching on permissions array
user?.permissions.includes('users:write')

// Pattern 3: Role checking
user?.roles?.includes('user_admin')

// Pattern 4: Hooks and components (preferred)
usePermission('users')
<PermissionGate permission="users:write" />
```

**Impact**: No single source of truth. Changing permission logic requires finding and updating all patterns.

### Solution: Centralize All Permission Logic

**Step 1**: Create a unified permission service.

```typescript
// src/lib/permissions.ts
import { store } from '@/store'

export type PermissionAction = 'read' | 'write' | 'delete' | 'admin'

export interface PermissionService {
  hasPermission: (permission: string) => boolean
  hasAnyPermission: (permissions: string[]) => boolean
  hasAllPermissions: (permissions: string[]) => boolean
  canAccess: (resource: string, action: PermissionAction) => boolean
  isSuperAdmin: () => boolean
  isImpersonating: () => boolean
}

function createPermissionService(): PermissionService {
  const getState = () => {
    const state = store.getState()
    return {
      user: state.auth.user,
      isImpersonating: state.impersonation?.isImpersonating ?? false,
    }
  }

  const isSuperAdmin = (): boolean => {
    const { user, isImpersonating } = getState()
    return user?.is_admin === true && !isImpersonating
  }

  const hasPermission = (permission: string): boolean => {
    if (isSuperAdmin()) return true
    const { user } = getState()
    return user?.permissions?.includes(permission) ?? false
  }

  const hasAnyPermission = (permissions: string[]): boolean => {
    if (isSuperAdmin()) return true
    return permissions.some(hasPermission)
  }

  const hasAllPermissions = (permissions: string[]): boolean => {
    if (isSuperAdmin()) return true
    return permissions.every(hasPermission)
  }

  const canAccess = (resource: string, action: PermissionAction): boolean => {
    return hasPermission(`${resource}:${action}`)
  }

  return {
    hasPermission,
    hasAnyPermission,
    hasAllPermissions,
    canAccess,
    isSuperAdmin,
    isImpersonating: () => getState().isImpersonating,
  }
}

export const permissions = createPermissionService()
```

**Step 2**: Create React hook that uses the service.

```typescript
// src/hooks/usePermissions.ts
import { useAppSelector } from '@/store/hooks'
import { useMemo } from 'react'

export function usePermissions() {
  const user = useAppSelector((state) => state.auth.user)
  const isImpersonating = useAppSelector((state) => state.impersonation?.isImpersonating ?? false)

  return useMemo(() => {
    const isSuperAdmin = user?.is_admin === true && !isImpersonating
    const userPermissions = user?.permissions ?? []

    const hasPermission = (permission: string): boolean => {
      if (isSuperAdmin) return true
      return userPermissions.includes(permission)
    }

    const hasAnyPermission = (permissions: string[]): boolean => {
      if (isSuperAdmin) return true
      return permissions.some((p) => userPermissions.includes(p))
    }

    const hasAllPermissions = (permissions: string[]): boolean => {
      if (isSuperAdmin) return true
      return permissions.every((p) => userPermissions.includes(p))
    }

    const canAccess = (resource: string, action: 'read' | 'write' | 'delete' | 'admin'): boolean => {
      return hasPermission(`${resource}:${action}`)
    }

    return {
      hasPermission,
      hasAnyPermission,
      hasAllPermissions,
      canAccess,
      isSuperAdmin,
      isImpersonating,
      permissions: userPermissions,
    }
  }, [user, isImpersonating])
}
```

**Step 3**: Migrate existing code.

```typescript
// BEFORE
if (user?.is_admin === true) { ... }
if (user?.permissions.includes('users:write')) { ... }

// AFTER
const { isSuperAdmin, hasPermission } = usePermissions()
if (isSuperAdmin) { ... }
if (hasPermission('users:write')) { ... }
```

### Migration Checklist

- [ ] Create `src/lib/permissions.ts`
- [ ] Create `src/hooks/usePermissions.ts`
- [ ] Update `PermissionGate` to use service internally
- [ ] Search and replace `user?.is_admin` patterns
- [ ] Search and replace `user?.permissions.includes` patterns
- [ ] Search and replace `user?.roles?.includes` patterns
- [ ] Update existing `usePermission` hook to use new service
- [ ] Run tests to verify no regressions

---

## Bottleneck 2: Hardcoded Navigation

### Problem

`AppSidebar`, `AdminSidebar`, and `PlatformAdminSidebar` have hardcoded menu structures with inline permission checks.

```typescript
// Current pattern - hardcoded in component
const menuItems = [
  { title: 'Dashboard', url: '/dashboard', icon: LayoutDashboard },
  { title: 'Files', url: '/files', icon: FolderOpen },
  // ... more items
]
```

**Impact**: Adding/removing/reordering navigation requires code changes. Cannot configure navigation without code modifications.

### Solution: Data-Driven Navigation

**Step 1**: Create navigation configuration.

```typescript
// src/config/navigation.ts
import {
  LayoutDashboard, FolderOpen, Settings, Users, Shield,
  Key, Bell, FileText, Activity, Flag, Clock, Building,
  type LucideIcon
} from 'lucide-react'

export interface NavItem {
  id: string
  title: string  // i18n key
  url: string
  icon: LucideIcon
  permissions?: string[]  // Empty = no permission required
  requireAll?: boolean    // Default false (any permission)
  badge?: 'notification-count' | 'pending-count'  // Dynamic badge type
  children?: NavItem[]
  dividerBefore?: boolean
  dividerAfter?: boolean
  external?: boolean
}

export interface NavSection {
  id: string
  title?: string  // i18n key, optional for untitled sections
  items: NavItem[]
}

// Main app navigation
export const mainNavigation: NavSection[] = [
  {
    id: 'main',
    items: [
      {
        id: 'dashboard',
        title: 'common:navigation.dashboard',
        url: '/dashboard',
        icon: LayoutDashboard
      },
      {
        id: 'files',
        title: 'common:navigation.files',
        url: '/files',
        icon: FolderOpen,
        permissions: ['files:read']
      },
    ],
  },
  {
    id: 'settings',
    title: 'common:navigation.settings',
    items: [
      {
        id: 'profile',
        title: 'common:navigation.profile',
        url: '/settings/profile',
        icon: Settings
      },
    ],
  },
]

// Admin navigation
export const adminNavigation: NavSection[] = [
  {
    id: 'users',
    title: 'admin:navigation.userManagement',
    items: [
      {
        id: 'users',
        title: 'admin:navigation.users',
        url: '/admin/users',
        icon: Users,
        permissions: ['users:read']
      },
      {
        id: 'roles',
        title: 'admin:navigation.roles',
        url: '/admin/roles',
        icon: Shield,
        permissions: ['roles:read']
      },
    ],
  },
  {
    id: 'system',
    title: 'admin:navigation.system',
    items: [
      {
        id: 'api-keys',
        title: 'admin:navigation.apiKeys',
        url: '/admin/api-keys',
        icon: Key,
        permissions: ['api_keys:read']
      },
      {
        id: 'audit-logs',
        title: 'admin:navigation.auditLogs',
        url: '/admin/audit-logs',
        icon: FileText,
        permissions: ['audit_logs:read']
      },
    ],
  },
]

// Platform admin navigation
export const platformAdminNavigation: NavSection[] = [
  {
    id: 'platform',
    items: [
      {
        id: 'organizations',
        title: 'admin:navigation.organizations',
        url: '/platform-admin/organizations',
        icon: Building
      },
      {
        id: 'metrics',
        title: 'admin:navigation.metrics',
        url: '/platform-admin/metrics',
        icon: Activity
      },
      {
        id: 'feature-flags',
        title: 'admin:navigation.featureFlags',
        url: '/platform-admin/feature-flags',
        icon: Flag
      },
      {
        id: 'cron-jobs',
        title: 'admin:navigation.cronJobs',
        url: '/platform-admin/cron-jobs',
        icon: Clock
      },
    ],
  },
]
```

**Step 2**: Create navigation hook.

```typescript
// src/hooks/useNavigation.ts
import { useMemo } from 'react'
import { usePermissions } from './usePermissions'
import {
  mainNavigation,
  adminNavigation,
  platformAdminNavigation,
  type NavItem,
  type NavSection
} from '@/config/navigation'

export function useNavigation(type: 'main' | 'admin' | 'platform-admin') {
  const { hasPermission, hasAnyPermission, hasAllPermissions, isSuperAdmin } = usePermissions()

  const config = useMemo(() => {
    switch (type) {
      case 'main': return mainNavigation
      case 'admin': return adminNavigation
      case 'platform-admin': return platformAdminNavigation
    }
  }, [type])

  const filteredNavigation = useMemo(() => {
    const filterItem = (item: NavItem): NavItem | null => {
      // Check permissions
      if (item.permissions && item.permissions.length > 0) {
        const hasAccess = item.requireAll
          ? hasAllPermissions(item.permissions)
          : hasAnyPermission(item.permissions)
        if (!hasAccess) return null
      }

      // Filter children recursively
      if (item.children) {
        const filteredChildren = item.children
          .map(filterItem)
          .filter((child): child is NavItem => child !== null)
        if (filteredChildren.length === 0) return null
        return { ...item, children: filteredChildren }
      }

      return item
    }

    const filterSection = (section: NavSection): NavSection | null => {
      const filteredItems = section.items
        .map(filterItem)
        .filter((item): item is NavItem => item !== null)
      if (filteredItems.length === 0) return null
      return { ...section, items: filteredItems }
    }

    return config
      .map(filterSection)
      .filter((section): section is NavSection => section !== null)
  }, [config, hasAnyPermission, hasAllPermissions])

  return {
    sections: filteredNavigation,
    isSuperAdmin,
  }
}
```

**Step 3**: Create reusable navigation renderer.

```typescript
// src/components/navigation/NavRenderer.tsx
import { useTranslation } from 'react-i18next'
import { NavLink, useLocation } from 'react-router-dom'
import { cn } from '@/lib/utils'
import type { NavItem, NavSection } from '@/config/navigation'

interface NavRendererProps {
  sections: NavSection[]
  collapsed?: boolean
  onItemClick?: () => void
  className?: string
}

export function NavRenderer({ sections, collapsed, onItemClick, className }: NavRendererProps) {
  const { t } = useTranslation()
  const location = useLocation()

  const renderItem = (item: NavItem) => {
    const Icon = item.icon
    const isActive = location.pathname === item.url ||
                     location.pathname.startsWith(item.url + '/')

    return (
      <NavLink
        key={item.id}
        to={item.url}
        onClick={onItemClick}
        className={cn(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
          'hover:bg-accent hover:text-accent-foreground',
          isActive && 'bg-accent text-accent-foreground',
          collapsed && 'justify-center px-2'
        )}
      >
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span>{t(item.title)}</span>}
      </NavLink>
    )
  }

  return (
    <nav className={cn('flex flex-col gap-1', className)}>
      {sections.map((section) => (
        <div key={section.id} className="flex flex-col gap-1">
          {section.title && !collapsed && (
            <div className="px-3 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              {t(section.title)}
            </div>
          )}
          {section.items.map(renderItem)}
        </div>
      ))}
    </nav>
  )
}
```

**Step 4**: Update sidebars to use config.

```typescript
// src/components/AppSidebar.tsx (simplified)
import { useNavigation } from '@/hooks/useNavigation'
import { NavRenderer } from '@/components/navigation/NavRenderer'

export function AppSidebar() {
  const { sections } = useNavigation('main')
  const { state } = useSidebar()

  return (
    <Sidebar>
      <SidebarContent>
        <NavRenderer sections={sections} collapsed={state === 'collapsed'} />
      </SidebarContent>
    </Sidebar>
  )
}
```

### Migration Checklist

- [ ] Create `src/config/navigation.ts`
- [ ] Create `src/hooks/useNavigation.ts`
- [ ] Create `src/components/navigation/NavRenderer.tsx`
- [ ] Add navigation i18n keys to locale files
- [ ] Update `AppSidebar` to use navigation config
- [ ] Update `AdminSidebar` to use navigation config
- [ ] Update `PlatformAdminSidebar` to use navigation config
- [ ] Test all navigation paths work correctly
- [ ] Verify permission filtering works

---

## Bottleneck 3: Auth State Direct Access

### Problem

Auth state accessed directly via `useAppSelector` in 50+ locations:

```typescript
const { user, token } = useAppSelector((state) => state.auth)
const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)
```

**Impact**: Changing auth state shape requires updating all consumers. No abstraction layer.

### Solution: Auth Abstraction Layer

**Step 1**: Create comprehensive auth hook.

```typescript
// src/hooks/useAuth.ts
import { useCallback, useMemo } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { logout as logoutAction, setCredentials } from '@/features/auth/authSlice'
import { useLogoutMutation } from '@/features/auth/authApi'

export interface AuthUser {
  id: string
  email: string
  firstName: string
  lastName: string
  fullName: string
  avatarUrl?: string
  isAdmin: boolean
  isTwoFactorEnabled: boolean
  permissions: string[]
  organizationId: string
}

export interface AuthState {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  requiresTwoFactor: boolean
  requiresTwoFactorSetup: boolean
}

export function useAuth() {
  const dispatch = useAppDispatch()
  const [logoutMutation] = useLogoutMutation()

  // Select raw state
  const rawUser = useAppSelector((state) => state.auth.user)
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)
  const isLoading = useAppSelector((state) => state.auth.isLoading)
  const twoFactor = useAppSelector((state) => state.auth.twoFactor)
  const twoFactorSetupRequired = useAppSelector((state) => state.auth.twoFactorSetupRequired)

  // Transform user to stable interface
  const user: AuthUser | null = useMemo(() => {
    if (!rawUser) return null
    return {
      id: rawUser.id,
      email: rawUser.email,
      firstName: rawUser.first_name,
      lastName: rawUser.last_name,
      fullName: `${rawUser.first_name} ${rawUser.last_name}`.trim(),
      avatarUrl: rawUser.avatar_url,
      isAdmin: rawUser.is_admin ?? false,
      isTwoFactorEnabled: rawUser.two_factor_enabled ?? false,
      permissions: rawUser.permissions ?? [],
      organizationId: rawUser.organization_id,
    }
  }, [rawUser])

  const logout = useCallback(async () => {
    try {
      await logoutMutation().unwrap()
    } finally {
      dispatch(logoutAction())
    }
  }, [dispatch, logoutMutation])

  return {
    user,
    isAuthenticated,
    isLoading,
    requiresTwoFactor: twoFactor?.required ?? false,
    requiresTwoFactorSetup: twoFactorSetupRequired ?? false,
    logout,
  }
}
```

**Step 2**: Create selector hooks for specific use cases.

```typescript
// src/hooks/useCurrentUser.ts
import { useAuth } from './useAuth'

// Simple hook for just getting user data
export function useCurrentUser() {
  const { user } = useAuth()
  return user
}

// Hook for checking if user is authenticated
export function useIsAuthenticated() {
  const { isAuthenticated, isLoading } = useAuth()
  return { isAuthenticated, isLoading }
}
```

**Step 3**: Migrate existing code.

```typescript
// BEFORE
const user = useAppSelector((state) => state.auth.user)
const isAdmin = user?.is_admin

// AFTER
const { user } = useAuth()
const isAdmin = user?.isAdmin
```

### Migration Checklist

- [ ] Create `src/hooks/useAuth.ts`
- [ ] Create `src/hooks/useCurrentUser.ts`
- [ ] Update `AuthGuard` to use `useAuth`
- [ ] Update `AuthProvider` to use `useAuth`
- [ ] Search and replace direct auth state access
- [ ] Update components using `user?.is_admin` to `user?.isAdmin`
- [ ] Update components using `user?.first_name` to `user?.firstName`
- [ ] Run full test suite

---

## Bottleneck 4: Scattered Tailwind Utilities

### Problem

Common styling patterns repeated across components:

```typescript
// Same patterns everywhere
className="flex items-center justify-between gap-4"
className="rounded-lg border bg-card p-4 shadow-sm"
className="text-sm text-muted-foreground"
```

**Impact**: Changing common patterns requires find-replace across entire codebase.

### Solution: Style Utility System

**Step 1**: Create style presets.

```typescript
// src/lib/styles.ts
import { cn } from './utils'

// Layout presets
export const layout = {
  flexCenter: 'flex items-center justify-center',
  flexBetween: 'flex items-center justify-between',
  flexStart: 'flex items-center justify-start',
  flexCol: 'flex flex-col',
  flexColCenter: 'flex flex-col items-center justify-center',
  stack: (gap: number = 4) => `flex flex-col gap-${gap}`,
  row: (gap: number = 4) => `flex items-center gap-${gap}`,
  grid: (cols: number = 2) => `grid grid-cols-${cols} gap-4`,
  gridResponsive: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4',
} as const

// Container presets
export const container = {
  page: 'container mx-auto px-4 py-6',
  section: 'space-y-6',
  card: 'rounded-lg border bg-card p-6 shadow-sm',
  cardCompact: 'rounded-lg border bg-card p-4 shadow-sm',
  panel: 'rounded-lg bg-muted/50 p-4',
} as const

// Typography presets
export const text = {
  h1: 'text-4xl font-bold tracking-tight',
  h2: 'text-3xl font-semibold tracking-tight',
  h3: 'text-2xl font-semibold tracking-tight',
  h4: 'text-xl font-semibold',
  body: 'text-base text-foreground',
  small: 'text-sm text-foreground',
  muted: 'text-sm text-muted-foreground',
  label: 'text-sm font-medium',
  error: 'text-sm text-destructive',
  success: 'text-sm text-success',
} as const

// Interactive presets
export const interactive = {
  clickable: 'cursor-pointer transition-colors hover:bg-accent',
  focusRing: 'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
  disabled: 'disabled:pointer-events-none disabled:opacity-50',
} as const

// Animation presets
export const animation = {
  fadeIn: 'animate-in fade-in duration-200',
  fadeOut: 'animate-out fade-out duration-200',
  slideIn: 'animate-in slide-in-from-bottom-4 duration-200',
  spin: 'animate-spin',
} as const

// Combine utility
export function styles(...classes: (string | undefined | false)[]) {
  return cn(...classes)
}
```

**Step 2**: Usage in components.

```typescript
// BEFORE
<div className="flex items-center justify-between gap-4">
  <h2 className="text-2xl font-semibold tracking-tight">Users</h2>
  <p className="text-sm text-muted-foreground">Manage users</p>
</div>

// AFTER
import { layout, text, container } from '@/lib/styles'

<div className={cn(layout.flexBetween, 'gap-4')}>
  <h2 className={text.h3}>Users</h2>
  <p className={text.muted}>Manage users</p>
</div>
```

### Migration Checklist

- [ ] Create `src/lib/styles.ts`
- [ ] Document all presets
- [ ] Migrate common patterns in shared components first
- [ ] Gradually adopt in feature components
- [ ] Consider adding more presets as patterns emerge

---

## Bottleneck 5: Route-Permission Coupling

### Problem

Routes and permission checks are tightly coupled in `router.tsx`:

```typescript
{
  path: 'users',
  element: (
    <PermissionGate permission={['users:read', 'users:write', 'users:delete']} redirectTo="/dashboard">
      <UsersPage />
    </PermissionGate>
  ),
}
```

**Impact**: Changing route permissions requires editing router file. Route metadata not accessible programmatically.

### Solution: Route Configuration System

**Step 1**: Create route configuration with metadata.

```typescript
// src/config/routes.ts
import { lazy, type ComponentType } from 'react'

export interface RouteConfig {
  path: string
  component: ComponentType
  permissions?: string[]
  requireAll?: boolean
  requireAuth?: boolean
  guestOnly?: boolean
  layout?: 'root' | 'dashboard' | 'admin' | 'platform-admin'
  title?: string  // i18n key for page title
  breadcrumb?: string  // i18n key for breadcrumb
}

// Lazy load pages
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const UsersPage = lazy(() => import('@/pages/admin/UsersPage'))
const RolesPage = lazy(() => import('@/pages/admin/RolesPage'))
const LoginPage = lazy(() => import('@/pages/LoginPage'))

export const routes: RouteConfig[] = [
  // Public routes
  {
    path: '/login',
    component: LoginPage,
    guestOnly: true,
    title: 'auth:login.title',
  },

  // Dashboard routes
  {
    path: '/dashboard',
    component: DashboardPage,
    requireAuth: true,
    layout: 'dashboard',
    title: 'common:navigation.dashboard',
  },

  // Admin routes
  {
    path: '/admin/users',
    component: UsersPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['users:read'],
    title: 'admin:users.title',
    breadcrumb: 'admin:navigation.users',
  },
  {
    path: '/admin/roles',
    component: RolesPage,
    requireAuth: true,
    layout: 'admin',
    permissions: ['roles:read'],
    title: 'admin:roles.title',
    breadcrumb: 'admin:navigation.roles',
  },
]

// Helper to find route config by path
export function getRouteConfig(path: string): RouteConfig | undefined {
  return routes.find((r) => r.path === path)
}

// Helper to get all routes for a layout
export function getRoutesByLayout(layout: RouteConfig['layout']): RouteConfig[] {
  return routes.filter((r) => r.layout === layout)
}
```

**Step 2**: Create route generator.

```typescript
// src/lib/route-generator.tsx
import { Suspense } from 'react'
import type { RouteObject } from 'react-router-dom'
import { AuthGuard } from '@/components/AuthGuard'
import { PermissionGate } from '@/components/PermissionGate'
import { PageSkeleton } from '@/components/skeletons/PageSkeleton'
import type { RouteConfig } from '@/config/routes'

export function generateRoute(config: RouteConfig): RouteObject {
  const Component = config.component

  let element = (
    <Suspense fallback={<PageSkeleton />}>
      <Component />
    </Suspense>
  )

  // Wrap with permission gate if needed
  if (config.permissions && config.permissions.length > 0) {
    element = (
      <PermissionGate
        permission={config.permissions}
        requireAll={config.requireAll}
        redirectTo="/dashboard"
      >
        {element}
      </PermissionGate>
    )
  }

  // Wrap with auth guard if needed
  if (config.requireAuth) {
    element = <AuthGuard>{element}</AuthGuard>
  } else if (config.guestOnly) {
    element = <AuthGuard requireAuth={false} redirectTo="/dashboard">{element}</AuthGuard>
  }

  return {
    path: config.path,
    element,
  }
}

export function generateRoutes(configs: RouteConfig[]): RouteObject[] {
  return configs.map(generateRoute)
}
```

### Migration Checklist

- [ ] Create `src/config/routes.ts`
- [ ] Create `src/lib/route-generator.tsx`
- [ ] Migrate existing routes to configuration
- [ ] Update `router.tsx` to use generated routes
- [ ] Add route metadata (titles, breadcrumbs)
- [ ] Test all routes work correctly

---

## Additional Proposals

### Proposal 1: Theme Configuration File

Move theme tokens to a dedicated configuration that can be easily swapped.

```typescript
// src/config/theme.ts
export interface ThemeConfig {
  name: string
  colors: {
    light: Record<string, string>
    dark: Record<string, string>
  }
  radius: string
  fonts: {
    sans: string
    mono: string
  }
}

export const defaultTheme: ThemeConfig = {
  name: 'default',
  colors: {
    light: {
      background: 'oklch(1 0 0)',
      foreground: 'oklch(0.145 0 0)',
      primary: 'oklch(0.205 0 0)',
      // ... all colors
    },
    dark: {
      background: 'oklch(0.145 0 0)',
      foreground: 'oklch(0.985 0 0)',
      // ... all colors
    },
  },
  radius: '0.625rem',
  fonts: {
    sans: 'Inter, system-ui, sans-serif',
    mono: 'JetBrains Mono, monospace',
  },
}

// Generate CSS from theme config
export function generateThemeCSS(theme: ThemeConfig): string {
  const lightVars = Object.entries(theme.colors.light)
    .map(([key, value]) => `--${key}: ${value};`)
    .join('\n  ')

  const darkVars = Object.entries(theme.colors.dark)
    .map(([key, value]) => `--${key}: ${value};`)
    .join('\n  ')

  return `
:root {
  --radius: ${theme.radius};
  ${lightVars}
}

.dark {
  ${darkVars}
}
`
}
```

### Proposal 2: Component Variant Registry

Create a registry for component variants that can be modified in one place.

```typescript
// src/config/component-variants.ts
import { cva, type VariantProps } from 'class-variance-authority'

// Centralized button variants
export const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground shadow hover:bg-primary/90',
        destructive: 'bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90',
        outline: 'border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground',
        secondary: 'bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        link: 'text-primary underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        lg: 'h-10 rounded-md px-8',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
)

// Export types for components
export type ButtonVariants = VariantProps<typeof buttonVariants>

// Centralized card variants
export const cardVariants = cva('rounded-lg border bg-card text-card-foreground', {
  variants: {
    variant: {
      default: 'shadow-sm',
      elevated: 'shadow-md',
      outline: 'shadow-none',
    },
    padding: {
      none: '',
      sm: 'p-4',
      default: 'p-6',
      lg: 'p-8',
    },
  },
  defaultVariants: {
    variant: 'default',
    padding: 'default',
  },
})
```

### Proposal 3: Layout Slot System

Create a flexible layout system with named slots.

```typescript
// src/components/layouts/SlotLayout.tsx
import { createContext, useContext, type ReactNode } from 'react'

interface LayoutSlots {
  header?: ReactNode
  sidebar?: ReactNode
  main: ReactNode
  footer?: ReactNode
}

interface LayoutConfig {
  showHeader?: boolean
  showSidebar?: boolean
  showFooter?: boolean
  sidebarPosition?: 'left' | 'right'
  sidebarWidth?: 'narrow' | 'default' | 'wide'
}

const defaultConfig: LayoutConfig = {
  showHeader: true,
  showSidebar: true,
  showFooter: false,
  sidebarPosition: 'left',
  sidebarWidth: 'default',
}

export function SlotLayout({ slots, config = defaultConfig }: { slots: LayoutSlots; config?: LayoutConfig }) {
  const { showHeader, showSidebar, showFooter, sidebarPosition, sidebarWidth } = { ...defaultConfig, ...config }

  const sidebarWidthClass = {
    narrow: 'w-16',
    default: 'w-64',
    wide: 'w-80',
  }[sidebarWidth ?? 'default']

  return (
    <div className="min-h-screen flex flex-col">
      {showHeader && slots.header && (
        <header className="sticky top-0 z-50 border-b bg-background">
          {slots.header}
        </header>
      )}

      <div className="flex flex-1">
        {showSidebar && slots.sidebar && sidebarPosition === 'left' && (
          <aside className={cn('border-r bg-background', sidebarWidthClass)}>
            {slots.sidebar}
          </aside>
        )}

        <main className="flex-1 overflow-auto">
          {slots.main}
        </main>

        {showSidebar && slots.sidebar && sidebarPosition === 'right' && (
          <aside className={cn('border-l bg-background', sidebarWidthClass)}>
            {slots.sidebar}
          </aside>
        )}
      </div>

      {showFooter && slots.footer && (
        <footer className="border-t bg-background">
          {slots.footer}
        </footer>
      )}
    </div>
  )
}
```

### Proposal 4: Feature Flags for UI

Extend feature flags to control UI variations.

```typescript
// src/config/ui-features.ts
export interface UIFeatureFlags {
  // Layout
  'ui.sidebar.collapsible': boolean
  'ui.sidebar.position': 'left' | 'right'
  'ui.header.sticky': boolean

  // Components
  'ui.buttons.rounded': boolean
  'ui.cards.shadows': boolean
  'ui.animations.enabled': boolean

  // Features
  'ui.darkMode.enabled': boolean
  'ui.notifications.position': 'top-right' | 'bottom-right' | 'top-left' | 'bottom-left'
}

// Hook to use UI feature flags
export function useUIFeature<K extends keyof UIFeatureFlags>(
  key: K,
  defaultValue: UIFeatureFlags[K]
): UIFeatureFlags[K] {
  const { flags } = useFeatureFlags()
  return (flags[key] as UIFeatureFlags[K]) ?? defaultValue
}
```

### Proposal 5: i18n Key Namespacing Convention

Establish consistent i18n key patterns for UI elements.

```typescript
// Naming convention for i18n keys
const i18nPatterns = {
  // Page titles
  pageTitle: '{namespace}:{page}.title',           // 'admin:users.title'

  // Navigation
  navItem: '{namespace}:navigation.{item}',        // 'common:navigation.dashboard'

  // Actions
  action: '{namespace}:{resource}.actions.{verb}', // 'admin:users.actions.create'

  // Form fields
  field: '{namespace}:{form}.fields.{field}',      // 'auth:login.fields.email'

  // Messages
  success: '{namespace}:{resource}.toast.{action}Success', // 'admin:users.toast.createSuccess'
  error: '{namespace}:{resource}.toast.{action}Error',     // 'admin:users.toast.createError'

  // Validation
  validation: 'validation:{rule}',                 // 'validation:required'
}
```

---

## AI Agent Execution Guide

### Before Any UI Change

1. **Read these files first**:
   - `src/index.css` - Design tokens
   - `src/config/navigation.ts` - Navigation (after refactoring)
   - `src/router.tsx` - Routes
   - `src/layouts/*` - Layouts
   - `src/hooks/useAuth.ts` - Auth (after refactoring)
   - `src/hooks/usePermissions.ts` - Permissions (after refactoring)

2. **Search for patterns**:
   ```bash
   grep -r "useAppSelector.*auth" src/        # Auth state usage
   grep -r "usePermission\|PermissionGate" src/  # Permission checks
   grep -r "className=" src/components/       # Styling patterns
   ```

3. **Run validation before AND after**:
   ```bash
   npm run lint
   npm run build
   npm run test
   ```

### Change Execution Order

For radical UI changes, execute in this order:

1. **Tokens first** (`src/index.css`) - Colors, spacing, radius
2. **Styles second** (`src/lib/styles.ts`) - Common patterns
3. **Components third** (`src/components/ui/*`) - Primitives
4. **Layouts fourth** (`src/layouts/*`) - Page structure
5. **Navigation fifth** (`src/config/navigation.ts`) - Menus
6. **Pages last** (`src/pages/*`) - Feature pages

### Validation Checklist

After any change:

- [ ] `npm run lint` passes
- [ ] `npm run build` succeeds
- [ ] `npm run test` passes
- [ ] Light mode renders correctly
- [ ] Dark mode renders correctly
- [ ] Mobile viewport works (test at 375px width)
- [ ] Desktop viewport works
- [ ] All permissions still enforced
- [ ] Auth flow works (login/logout)
- [ ] Navigation works (all links)
- [ ] Forms validate and submit
- [ ] Toast notifications appear
- [ ] All 5 locales have required keys

### Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| Breaking permission checks | Never remove `PermissionGate` wrappers |
| Breaking auth state | Use `useAuth` hook, not direct selectors |
| Missing i18n keys | Add to ALL locale files (en, de, xh, zu, nso) |
| Responsive breakage | Test at 375px, 768px, 1024px, 1440px |
| Dark mode breakage | Test both themes after color changes |
| Missing error handling | Keep existing error boundaries |

---

## Files Reference

| Purpose | Location |
|---------|----------|
| Design tokens | `src/index.css` |
| Style utilities | `src/lib/utils.ts`, `src/lib/styles.ts` (new) |
| Permission service | `src/lib/permissions.ts` (new) |
| Permission hooks | `src/hooks/usePermissions.ts` (new) |
| Auth hooks | `src/hooks/useAuth.ts` (new) |
| Navigation config | `src/config/navigation.ts` (new) |
| Route config | `src/config/routes.ts` (new) |
| Theme config | `src/config/theme.ts` (new) |
| Component variants | `src/config/component-variants.ts` (new) |
| UI components | `src/components/ui/*` |
| Layouts | `src/layouts/*` |
| Router | `src/router.tsx` |

---

## Cross-References

- **Styling**: `ai_docs/frontend/context/styling.md`
- **Components**: `ai_docs/frontend/context/components.md`
- **State**: `ai_docs/frontend/context/state.md`
- **Routing**: `ai_docs/frontend/context/routing.md`
- **Permissions**: `ai_docs/frontend/context/permissions.md`
- **i18n**: `ai_docs/frontend/context/i18n.md`
