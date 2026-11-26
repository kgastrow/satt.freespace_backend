/**
 * Permission types - re-export from generated plus frontend-only utilities
 */

// Re-export API types from generated
export type {
  Permission,
  PermissionsListResponse,
  CreatePermissionRequest,
  UpdatePermissionRequest,
  PermissionMatrixResponse,
  AssignPermissionRequest,
  RevokePermissionRequest,
  RoleWithPermissionsResponse as RoleWithPermissions,
} from '@/types/generated'

import type { Permission, RoleWithPermissionsResponse } from '@/types/generated'

/**
 * User type with permissions for the extended permission matrix
 */
export interface UserTypeWithPermissions {
  id: string
  name: string
  code: string
  description?: string | null
  permission_ids: string[]
}

/**
 * Extended permission matrix response including user types
 */
export interface ExtendedPermissionMatrixResponse {
  permissions: Permission[]
  roles: RoleWithPermissionsResponse[]
  user_types: UserTypeWithPermissions[]
}

/**
 * Request to assign a permission to a user type
 */
export interface AssignUserTypePermissionRequest {
  user_type_id: string
  permission_id: string
}

/**
 * Request to revoke a permission from a user type
 */
export interface RevokeUserTypePermissionRequest {
  user_type_id: string
  permission_id: string
}

/**
 * Group permissions by resource for display (frontend-only)
 */
export interface PermissionGroup {
  resource: string
  permissions: Permission[]
}

/**
 * Helper function to group permissions by resource
 */
export function groupPermissionsByResource(
  permissions: Permission[]
): PermissionGroup[] {
  const groups: Map<string, Permission[]> = new Map()

  for (const permission of permissions) {
    const existing = groups.get(permission.resource) || []
    existing.push(permission)
    groups.set(permission.resource, existing)
  }

  return Array.from(groups.entries())
    .map(([resource, perms]) => ({
      resource,
      permissions: perms.sort((a, b) => a.display_order - b.display_order),
    }))
    .sort((a, b) => a.resource.localeCompare(b.resource))
}
