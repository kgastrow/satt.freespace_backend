import { api } from '@/store/api'
import type {
  Role,
  RolesListResponse,
  CreateRoleRequest,
  UpdateRoleRequest,
  UserRole,
  AssignRoleRequest,
  RevokeRoleRequest,
} from '@/types/generated'

// Re-export for backwards compatibility
export type {
  Role,
  RolesListResponse,
  CreateRoleRequest,
  UpdateRoleRequest,
  UserRole,
  AssignRoleRequest,
  RevokeRoleRequest,
} from '@/types/generated'

export const rolesApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getRoles: builder.query<RolesListResponse, { limit?: number; offset?: number }>({
      query: ({ limit = 50, offset = 0 }) => `/roles?limit=${limit}&offset=${offset}`,
      providesTags: ['Role'],
    }),

    getRole: builder.query<Role, string>({
      query: (id) => `/roles/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Role', id }],
    }),

    createRole: builder.mutation<Role, CreateRoleRequest>({
      query: (body) => ({
        url: '/roles',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Role'],
    }),

    updateRole: builder.mutation<Role, { id: string; data: UpdateRoleRequest }>({
      query: ({ id, data }) => ({
        url: `/roles/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Role', id }, 'Role'],
    }),

    deleteRole: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/roles/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Role'],
    }),

    // User role management
    getUserRoles: builder.query<
      { items: UserRole[]; total: number; limit: number; offset: number },
      { userId: string; limit?: number; offset?: number }
    >({
      query: ({ userId, limit = 50, offset = 0 }) =>
        `/user-roles/users/${userId}/roles?limit=${limit}&offset=${offset}`,
      providesTags: (_result, _error, { userId }) => [{ type: 'UserRole', id: userId }],
    }),

    assignRole: builder.mutation<{ message: string }, AssignRoleRequest>({
      query: (body) => ({
        url: '/user-roles/assign',
        method: 'POST',
        body,
      }),
      invalidatesTags: (_result, _error, { user_id }) => [
        { type: 'UserRole', id: user_id },
        'User',
      ],
    }),

    revokeRole: builder.mutation<{ message: string }, RevokeRoleRequest>({
      query: (body) => ({
        url: '/user-roles/revoke',
        method: 'POST',
        body,
      }),
      invalidatesTags: (_result, _error, { user_id }) => [
        { type: 'UserRole', id: user_id },
        'User',
      ],
    }),
  }),
})

export const {
  useGetRolesQuery,
  useGetRoleQuery,
  useCreateRoleMutation,
  useUpdateRoleMutation,
  useDeleteRoleMutation,
  useGetUserRolesQuery,
  useAssignRoleMutation,
  useRevokeRoleMutation,
} = rolesApi
