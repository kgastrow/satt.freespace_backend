import { api } from '@/store/api'
import type {
  Organization,
  OrganizationsListResponse,
  OrganizationMembersResponse,
  CreateOrganizationRequest,
  UpdateOrganizationRequest,
  DeletionRequestResponse,
  CancelDeletionResponse,
  HardDeleteStatusResponse,
  HardDeleteResponse,
} from '@/types/generated'

// Re-export for backwards compatibility
export type {
  Organization,
  OrganizationMember,
  OrganizationsListResponse,
  OrganizationMembersResponse,
  CreateOrganizationRequest,
  UpdateOrganizationRequest,
  DeletionRequestResponse,
  CancelDeletionResponse,
  HardDeleteStatusResponse,
  HardDeleteResponse,
} from '@/types/generated'

export const organizationsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getOrganizations: builder.query<
      OrganizationsListResponse,
      { limit?: number; offset?: number }
    >({
      query: ({ limit = 10, offset = 0 }) =>
        `/organizations?limit=${limit}&offset=${offset}`,
      providesTags: ['Organization'],
    }),

    getOrganization: builder.query<Organization, string>({
      query: (id) => `/organizations/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Organization', id }],
    }),

    createOrganization: builder.mutation<Organization, CreateOrganizationRequest>({
      query: (body) => ({
        url: '/organizations',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Organization'],
    }),

    updateOrganization: builder.mutation<
      Organization,
      { id: string; data: UpdateOrganizationRequest }
    >({
      query: ({ id, data }) => ({
        url: `/organizations/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Organization', id },
        'Organization',
      ],
    }),

    deleteOrganization: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/organizations/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Organization'],
    }),

    // Deletion request endpoints
    requestOrganizationDeletion: builder.mutation<DeletionRequestResponse, string>({
      query: (id) => ({
        url: `/organizations/${id}/request-deletion`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Organization', id },
        'Organization',
      ],
    }),

    cancelOrganizationDeletionRequest: builder.mutation<CancelDeletionResponse, string>({
      query: (id) => ({
        url: `/organizations/${id}/request-deletion`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Organization', id },
        'Organization',
      ],
    }),

    // Hard-delete endpoints
    getHardDeleteStatus: builder.query<HardDeleteStatusResponse, string>({
      query: (id) => `/organizations/${id}/hard-delete-status`,
    }),

    hardDeleteOrganization: builder.mutation<HardDeleteResponse, string>({
      query: (id) => ({
        url: `/organizations/${id}/hard-delete`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Organization'],
    }),

    // Member management
    getOrganizationMembers: builder.query<
      OrganizationMembersResponse,
      { id: string; limit?: number; offset?: number }
    >({
      query: ({ id, limit = 10, offset = 0 }) =>
        `/organizations/${id}/members?limit=${limit}&offset=${offset}`,
      providesTags: (_result, _error, { id }) => [
        { type: 'OrganizationMember', id },
      ],
    }),

    getOrganizationMemberCount: builder.query<{ count: number }, string>({
      query: (id) => `/organizations/${id}/members/count`,
    }),

    removeOrganizationMember: builder.mutation<
      { message: string },
      { orgId: string; userId: string }
    >({
      query: ({ orgId, userId }) => ({
        url: `/organizations/${orgId}/members/${userId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, { orgId }) => [
        { type: 'OrganizationMember', id: orgId },
      ],
    }),

    // 2FA management
    getOrg2FASettings: builder.query<{ two_factor_allowed: boolean }, string>({
      query: (id) => `/organization-two-factor-settings/organization/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Organization2FA', id }],
    }),

    setOrg2FAAllowed: builder.mutation<
      { two_factor_allowed: boolean },
      { organizationId: string; twoFaAllowed: boolean }
    >({
      query: ({ organizationId, twoFaAllowed }) => ({
        url: `/organization-two-factor-settings/organization/${organizationId}/allow`,
        method: 'PUT',
        body: { two_factor_allowed: twoFaAllowed },
      }),
      invalidatesTags: (_result, _error, { organizationId }) => [
        { type: 'Organization2FA', id: organizationId },
      ],
    }),
  }),
})

export const {
  useGetOrganizationsQuery,
  useGetOrganizationQuery,
  useCreateOrganizationMutation,
  useUpdateOrganizationMutation,
  useDeleteOrganizationMutation,
  useRequestOrganizationDeletionMutation,
  useCancelOrganizationDeletionRequestMutation,
  useGetHardDeleteStatusQuery,
  useLazyGetHardDeleteStatusQuery,
  useHardDeleteOrganizationMutation,
  useGetOrganizationMembersQuery,
  useGetOrganizationMemberCountQuery,
  useRemoveOrganizationMemberMutation,
  useLazyGetOrg2FASettingsQuery,
  useSetOrg2FAAllowedMutation,
} = organizationsApi
