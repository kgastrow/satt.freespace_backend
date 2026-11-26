import { api } from '@/store/api'
import type {
  UserIdentitiesResponse,
  UnlinkIdentityResponse,
  UnlinkWithSetupRequest,
  UnlinkWithSetupResponse,
} from '@/types/identity'

export const identityApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /user/me/identities - Get user's linked identities
     */
    getUserIdentities: builder.query<UserIdentitiesResponse, void>({
      query: () => '/user/me/identities',
      providesTags: [{ type: 'UserIdentity', id: 'LIST' }],
    }),

    /**
     * DELETE /user/me/identities/{provider} - Simple unlink (requires password)
     */
    unlinkIdentity: builder.mutation<UnlinkIdentityResponse, { provider: string }>({
      query: ({ provider }) => ({
        url: `/user/me/identities/${provider}`,
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'UserIdentity', id: 'LIST' }],
    }),

    /**
     * POST /user/me/identities/{provider}/unlink-with-setup - Unlink with password/2FA setup
     */
    unlinkWithSetup: builder.mutation<
      UnlinkWithSetupResponse,
      { provider: string } & UnlinkWithSetupRequest
    >({
      query: ({ provider, ...body }) => ({
        url: `/user/me/identities/${provider}/unlink-with-setup`,
        method: 'POST',
        body,
      }),
      invalidatesTags: [
        { type: 'UserIdentity', id: 'LIST' },
        { type: 'UserTwoFactor', id: 'STATUS' },
      ],
    }),
  }),
})

export const {
  useGetUserIdentitiesQuery,
  useLazyGetUserIdentitiesQuery,
  useUnlinkIdentityMutation,
  useUnlinkWithSetupMutation,
} = identityApi
