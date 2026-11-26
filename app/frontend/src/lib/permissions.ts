import type { RootState } from '@/store'
import { store } from '@/store'

/**
 * Permission action types for resource-based checks
 */
export type PermissionAction = 'read' | 'write' | 'delete' | 'admin'

/**
 * Centralized permission service for checking user permissions.
 * This service provides a single source of truth for all permission logic.
 *
 * All methods automatically handle:
 * - Super admin bypass (is_admin: true)
 * - Impersonation blocking (super admin access disabled during impersonation)
 * - Permission code validation
 *
 * @example
 * ```typescript
 * import { permissions } from '@/lib/permissions'
 *
 * if (permissions.hasPermission('users:write')) {
 *   // User can write users
 * }
 *
 * if (permissions.isSuperAdmin()) {
 *   // User is super admin
 * }
 * ```
 */
export interface PermissionService {
  /**
   * Check if user has a specific permission code.
   *
   * @param permission - Permission code (e.g., 'users:read')
   * @returns true if user has permission or is super admin
   */
  hasPermission: (permission: string) => boolean

  /**
   * Check if user has any of the specified permissions (OR logic).
   *
   * @param permissions - Array of permission codes
   * @returns true if user has any of the permissions or is super admin
   */
  hasAnyPermission: (permissions: string[]) => boolean

  /**
   * Check if user has all of the specified permissions (AND logic).
   *
   * @param permissions - Array of permission codes
   * @returns true if user has all permissions or is super admin
   */
  hasAllPermissions: (permissions: string[]) => boolean

  /**
   * Check if user can perform an action on a resource.
   * Convenience method for resource:action pattern.
   *
   * @param resource - Resource name (e.g., 'users')
   * @param action - Action type ('read' | 'write' | 'delete' | 'admin')
   * @returns true if user has permission or is super admin
   */
  canAccess: (resource: string, action: PermissionAction) => boolean

  /**
   * Check if user is a super admin (is_admin: true).
   * Super admin access is disabled during impersonation.
   *
   * @returns true if user is admin and not impersonating
   */
  isSuperAdmin: () => boolean

  /**
   * Check if user is currently impersonating another user.
   *
   * @returns true if active impersonation session exists
   */
  isImpersonating: () => boolean
}

/**
 * Get current auth and impersonation state from Redux store
 */
function getState(): { user: RootState['auth']['user']; isImpersonating: boolean } {
  const state = store.getState()
  return {
    user: state.auth.user,
    isImpersonating: state.impersonation?.isImpersonating ?? false,
  }
}

/**
 * Create the permission service instance.
 * This is a singleton that reads from the Redux store.
 */
function createPermissionService(): PermissionService {
  const isSuperAdmin = (): boolean => {
    const { user, isImpersonating } = getState()
    return user?.is_admin === true && !isImpersonating
  }

  const isImpersonating = (): boolean => {
    const { isImpersonating } = getState()
    return isImpersonating
  }

  const hasPermission = (permission: string): boolean => {
    if (isSuperAdmin()) return true
    const { user } = getState()
    return user?.permissions?.includes(permission) ?? false
  }

  const hasAnyPermission = (permissions: string[]): boolean => {
    if (isSuperAdmin()) return true
    if (permissions.length === 0) return false
    return permissions.some(hasPermission)
  }

  const hasAllPermissions = (permissions: string[]): boolean => {
    if (isSuperAdmin()) return true
    if (permissions.length === 0) return true
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
    isImpersonating,
  }
}

/**
 * Global permission service instance.
 * Use this for non-reactive permission checks.
 *
 * For React components, prefer usePermissions hook for reactive updates.
 *
 * @example
 * ```typescript
 * // In a utility function
 * import { permissions } from '@/lib/permissions'
 *
 * function canUserEdit(resource: string): boolean {
 *   return permissions.canAccess(resource, 'write')
 * }
 *
 * // In a React component (prefer usePermissions hook)
 * import { usePermissions } from '@/hooks/usePermissions'
 *
 * function MyComponent() {
 *   const { hasPermission } = usePermissions()
 *   return hasPermission('users:write') ? <Button>Edit</Button> : null
 * }
 * ```
 */
export const permissions = createPermissionService()
