import { useMemo } from 'react'
import { useAppSelector } from '@/store/hooks'
import { selectUser } from '@/features/auth/authSelectors'
import { selectIsImpersonating } from '@/features/impersonation/impersonationSelectors'
import type { PermissionAction } from '@/lib/permissions'

/**
 * Enhanced permission hook with reactive updates from Redux.
 *
 * This hook provides a comprehensive set of permission checking utilities
 * that automatically respond to auth state changes. It consolidates all
 * permission checking patterns into a single, consistent interface.
 *
 * Features:
 * - Reactive updates when auth state changes
 * - Super admin bypass (is_admin: true)
 * - Impersonation blocking (super admin access disabled during impersonation)
 * - Multiple check patterns (single, any, all, resource-based)
 *
 * @returns Permission checking utilities and current permission state
 *
 * @example
 * ```tsx
 * function UsersPage() {
 *   const {
 *     hasPermission,
 *     hasAnyPermission,
 *     hasAllPermissions,
 *     canAccess,
 *     isSuperAdmin,
 *     isImpersonating,
 *     permissions
 *   } = usePermissions()
 *
 *   // Single permission check
 *   if (hasPermission('users:write')) {
 *     return <CreateUserButton />
 *   }
 *
 *   // Multiple permission check (OR logic)
 *   const canManage = hasAnyPermission(['users:write', 'users:delete'])
 *
 *   // Multiple permission check (AND logic)
 *   const hasFullAccess = hasAllPermissions(['users:read', 'users:write', 'users:delete'])
 *
 *   // Resource-based check
 *   const canEditUsers = canAccess('users', 'write')
 *
 *   // Super admin check
 *   if (isSuperAdmin) {
 *     return <AdminPanel />
 *   }
 * }
 * ```
 */
export function usePermissions() {
  // Select auth state using memoized selectors
  const user = useAppSelector(selectUser)
  const isImpersonatingUser = useAppSelector(selectIsImpersonating)

  // Memoize permission utilities to prevent unnecessary re-renders
  return useMemo(() => {
    const isSuperAdmin = user?.is_admin === true && !isImpersonatingUser
    const userPermissions = user?.permissions ?? []

    /**
     * Check if user has a specific permission code.
     *
     * @param permission - Permission code (e.g., 'users:read')
     * @returns true if user has permission or is super admin
     */
    const hasPermission = (permission: string): boolean => {
      if (isSuperAdmin) return true
      return userPermissions.includes(permission)
    }

    /**
     * Check if user has any of the specified permissions (OR logic).
     *
     * @param codes - Array of permission codes
     * @returns true if user has any of the permissions or is super admin
     */
    const hasAnyPermission = (codes: string[]): boolean => {
      if (isSuperAdmin) return true
      if (codes.length === 0) return false
      return codes.some((code) => userPermissions.includes(code))
    }

    /**
     * Check if user has all of the specified permissions (AND logic).
     *
     * @param codes - Array of permission codes
     * @returns true if user has all permissions or is super admin
     */
    const hasAllPermissions = (codes: string[]): boolean => {
      if (isSuperAdmin) return true
      if (codes.length === 0) return true
      return codes.every((code) => userPermissions.includes(code))
    }

    /**
     * Check if user can perform an action on a resource.
     * Convenience method for resource:action pattern.
     *
     * @param resource - Resource name (e.g., 'users')
     * @param action - Action type ('read' | 'write' | 'delete' | 'admin')
     * @returns true if user has permission or is super admin
     */
    const canAccess = (resource: string, action: PermissionAction): boolean => {
      return hasPermission(`${resource}:${action}`)
    }

    return {
      /** Check if user has a specific permission code */
      hasPermission,
      /** Check if user has any of the specified permissions (OR logic) */
      hasAnyPermission,
      /** Check if user has all of the specified permissions (AND logic) */
      hasAllPermissions,
      /** Check if user can perform an action on a resource */
      canAccess,
      /** True if user is super admin (is_admin: true) and not impersonating */
      isSuperAdmin,
      /** True if user is currently impersonating another user */
      isImpersonating: isImpersonatingUser,
      /** Array of user's permission codes */
      permissions: userPermissions,
    }
  }, [user, isImpersonatingUser])
}
