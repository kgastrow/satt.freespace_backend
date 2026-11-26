import { usePermissions } from './usePermissions'

/**
 * Permission check result for a resource
 */
export interface PermissionCheck {
  /** User can read/view the resource */
  canRead: boolean
  /** User can create/update the resource */
  canWrite: boolean
  /** User can delete the resource */
  canDelete: boolean
  /** Check if user has a specific permission code */
  hasPermission: (code: string) => boolean
}

/**
 * Hook to check user permissions for a resource.
 *
 * This hook provides a resource-centric interface for permission checking.
 * Internally uses the centralized usePermissions hook for consistency.
 *
 * @param resource - The resource name (e.g., 'users', 'api_keys', 'roles')
 * @returns Permission check object with canRead, canWrite, canDelete, and hasPermission
 *
 * @example
 * ```tsx
 * const { canRead, canWrite, canDelete } = usePermission('users')
 *
 * if (canWrite) {
 *   // Show create button
 * }
 * ```
 */
export function usePermission(resource: string): PermissionCheck {
  const { canAccess, hasPermission } = usePermissions()

  return {
    canRead: canAccess(resource, 'read'),
    canWrite: canAccess(resource, 'write'),
    canDelete: canAccess(resource, 'delete'),
    hasPermission,
  }
}

/**
 * Hook to check if user has any of the specified permissions.
 *
 * This hook uses the centralized usePermissions hook for consistency.
 *
 * @param codes - Array of permission codes to check
 * @returns true if user has any of the specified permissions
 *
 * @example
 * ```tsx
 * const canManageUsers = useHasAnyPermission(['users:write', 'users:delete'])
 * ```
 */
export function useHasAnyPermission(codes: string[]): boolean {
  const { hasAnyPermission } = usePermissions()
  return hasAnyPermission(codes)
}

/**
 * Hook to check if user has all of the specified permissions.
 *
 * This hook uses the centralized usePermissions hook for consistency.
 *
 * @param codes - Array of permission codes to check
 * @returns true if user has all of the specified permissions
 *
 * @example
 * ```tsx
 * const canFullyManageUsers = useHasAllPermissions(['users:read', 'users:write', 'users:delete'])
 * ```
 */
export function useHasAllPermissions(codes: string[]): boolean {
  const { hasAllPermissions } = usePermissions()
  return hasAllPermissions(codes)
}
