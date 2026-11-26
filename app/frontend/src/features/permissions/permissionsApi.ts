import { api } from '@/store/api'
import type {
  Permission,
  PermissionsListResponse,
  CreatePermissionRequest,
  UpdatePermissionRequest,
  PermissionMatrixResponse,
  AssignPermissionRequest,
  RevokePermissionRequest,
  ExtendedPermissionMatrixResponse,
  AssignUserTypePermissionRequest,
  RevokeUserTypePermissionRequest,
} from './types'

export const permissionsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * Get list of all permissions (paginated)
     */
    getPermissions: builder.query<
      PermissionsListResponse,
      { limit?: number; offset?: number }
    >({
      query: ({ limit = 50, offset = 0 }) =>
        `/admin/permissions?limit=${limit}&offset=${offset}`,
      providesTags: (result) =>
        result
          ? [
              ...result.items.map((p) => ({
                type: 'Permission' as const,
                id: p.id,
              })),
              { type: 'Permission', id: 'LIST' },
            ]
          : [{ type: 'Permission', id: 'LIST' }],
    }),

    /**
     * Get a single permission by ID
     */
    getPermission: builder.query<Permission, string>({
      query: (id) => `/admin/permissions/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Permission', id }],
    }),

    /**
     * Create a new permission
     */
    createPermission: builder.mutation<
      { message: string; permission: Permission },
      CreatePermissionRequest
    >({
      query: (body) => ({
        url: '/admin/permissions',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'Permission', id: 'LIST' }],
    }),

    /**
     * Update an existing permission
     */
    updatePermission: builder.mutation<
      Permission,
      { id: string; data: UpdatePermissionRequest }
    >({
      query: ({ id, data }) => ({
        url: `/admin/permissions/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Permission', id },
        { type: 'Permission', id: 'LIST' },
        { type: 'PermissionMatrix', id: 'LIST' },
      ],
    }),

    /**
     * Delete a permission
     */
    deletePermission: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/admin/permissions/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: [
        { type: 'Permission', id: 'LIST' },
        { type: 'PermissionMatrix', id: 'LIST' },
      ],
    }),

    /**
     * Get global permission matrix
     * Shows all permissions and which roles have them assigned
     * Roles are global (system-wide) so no organization context needed
     */
    getPermissionMatrix: builder.query<PermissionMatrixResponse, void>({
      query: () => '/admin/permissions/matrix',
      providesTags: [{ type: 'PermissionMatrix', id: 'LIST' }],
    }),

    /**
     * Assign a permission to a role
     * Roles are global so no organization context needed
     */
    assignPermission: builder.mutation<{ message: string }, AssignPermissionRequest>({
      query: (body) => ({
        url: '/admin/role-permissions/assign',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'PermissionMatrix', id: 'LIST' }],
    }),

    /**
     * Revoke a permission from a role
     * Roles are global so no organization context needed
     */
    revokePermission: builder.mutation<{ message: string }, RevokePermissionRequest>({
      query: (body) => ({
        url: '/admin/role-permissions/revoke',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'PermissionMatrix', id: 'LIST' }],
    }),

    /**
     * Get extended permission matrix (includes user types)
     * Shows all permissions, roles, and user types with their assigned permissions
     */
    getExtendedPermissionMatrix: builder.query<ExtendedPermissionMatrixResponse, void>({
      query: () => '/admin/permissions/matrix/extended',
      providesTags: [{ type: 'UserTypePermissionMatrix', id: 'LIST' }],
    }),

    /**
     * Assign a permission to a user type
     * User types are global so no organization context needed
     */
    assignUserTypePermission: builder.mutation<{ message: string }, AssignUserTypePermissionRequest>({
      query: (body) => ({
        url: '/admin/user-type-permissions/assign',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'UserTypePermissionMatrix', id: 'LIST' }],
    }),

    /**
     * Revoke a permission from a user type
     * User types are global so no organization context needed
     */
    revokeUserTypePermission: builder.mutation<{ message: string }, RevokeUserTypePermissionRequest>({
      query: (body) => ({
        url: '/admin/user-type-permissions/revoke',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'UserTypePermissionMatrix', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetPermissionsQuery,
  useGetPermissionQuery,
  useCreatePermissionMutation,
  useUpdatePermissionMutation,
  useDeletePermissionMutation,
  useGetPermissionMatrixQuery,
  useAssignPermissionMutation,
  useRevokePermissionMutation,
  useGetExtendedPermissionMatrixQuery,
  useAssignUserTypePermissionMutation,
  useRevokeUserTypePermissionMutation,
} = permissionsApi

// Re-export types for convenience
export type { Permission } from './types'
