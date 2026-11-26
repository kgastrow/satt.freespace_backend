import { Suspense } from 'react'
import type { RouteObject } from 'react-router-dom'
import { AuthGuard } from '@/components/AuthGuard'
import { PermissionGate } from '@/components/PermissionGate'
import { PageLoader } from '@/components/PageLoader'
import type { RouteConfig } from '@/config/routes'

/**
 * Generate a React Router route object from a route configuration.
 *
 * This function wraps the route component with appropriate guards:
 * 1. Suspense for lazy-loaded components
 * 2. PermissionGate for permission-based access control
 * 3. AuthGuard for authentication requirements
 *
 * The order matters: AuthGuard → PermissionGate → Suspense → Component
 *
 * @param config - Route configuration object
 * @returns React Router RouteObject
 *
 * @example
 * ```typescript
 * const route = generateRoute({
 *   path: '/admin/users',
 *   component: lazy(() => import('./UsersPage')),
 *   requireAuth: true,
 *   permissions: ['users:read'],
 * })
 * ```
 */
export function generateRoute(config: RouteConfig): RouteObject {
  const Component = config.component

  // Start with the component wrapped in Suspense for lazy loading support
  let element = (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  )

  // Wrap with permission gate if permissions are specified
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

  // Wrap with auth guard if authentication is required or guest-only
  if (config.requireAuth) {
    element = <AuthGuard>{element}</AuthGuard>
  } else if (config.guestOnly) {
    element = (
      <AuthGuard requireAuth={false} redirectTo="/dashboard">
        {element}
      </AuthGuard>
    )
  }

  return {
    path: config.path,
    element,
  }
}

/**
 * Generate multiple React Router route objects from route configurations.
 *
 * @param configs - Array of route configuration objects
 * @returns Array of React Router RouteObject instances
 *
 * @example
 * ```typescript
 * const adminRouteObjects = generateRoutes(adminRoutes)
 * ```
 */
export function generateRoutes(configs: RouteConfig[]): RouteObject[] {
  return configs.map(generateRoute)
}
