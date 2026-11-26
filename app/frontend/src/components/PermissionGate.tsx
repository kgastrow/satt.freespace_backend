import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAppSelector } from '@/store/hooks'
import { useImpersonation } from '@/hooks/useImpersonation'

interface PermissionGateProps {
  /** Permission code(s) required. Can be a single code or array of codes. */
  permission: string | string[]
  /** If true, user must have ALL permissions. If false (default), ANY permission is sufficient. */
  requireAll?: boolean
  /** Content to render when user has permission */
  children: ReactNode
  /** Optional fallback content when user lacks permission (for inline use) */
  fallback?: ReactNode
  /** Optional redirect path when user lacks permission (for route-level use) */
  redirectTo?: string
}

/**
 * Conditionally renders children based on user permissions.
 *
 * @example
 * ```tsx
 * // Single permission
 * <PermissionGate permission="users:write">
 *   <CreateUserButton />
 * </PermissionGate>
 *
 * // Multiple permissions (any)
 * <PermissionGate permission={['users:write', 'users:delete']}>
 *   <ManageUsersPanel />
 * </PermissionGate>
 *
 * // Multiple permissions (all required)
 * <PermissionGate permission={['users:read', 'users:write']} requireAll>
 *   <EditUserButton />
 * </PermissionGate>
 *
 * // With fallback
 * <PermissionGate permission="admin:access" fallback={<AccessDenied />}>
 *   <AdminPanel />
 * </PermissionGate>
 * ```
 */
export function PermissionGate({
  permission,
  requireAll = false,
  children,
  fallback = null,
  redirectTo,
}: PermissionGateProps) {
  const location = useLocation()
  const { user, isLoading } = useAppSelector((state) => state.auth)
  const { isImpersonating } = useImpersonation()
  const userPermissions = user?.permissions || []

  // For route-level use, show loading state while auth is being determined
  if (redirectTo && isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  // Super admins have all permissions, BUT NOT during impersonation
  // When impersonating, the admin should see the app as the impersonated user
  if (user?.is_admin && !isImpersonating) {
    return <>{children}</>
  }

  const codes = Array.isArray(permission) ? permission : [permission]

  const hasPermission = requireAll
    ? codes.every((code) => userPermissions.includes(code))
    : codes.some((code) => userPermissions.includes(code))

  if (hasPermission) {
    return <>{children}</>
  }

  // Route-level: redirect if no permission
  if (redirectTo) {
    return <Navigate to={redirectTo} state={{ from: location }} replace />
  }

  // Inline: show fallback
  return <>{fallback}</>
}
