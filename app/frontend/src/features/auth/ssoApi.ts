import { api } from '@/store/api'
import type {
  SSOAuthorizationResponse,
  SSOCallbackResponse,
  SSOCallbackSuccessResponse,
  ConfirmLinkRequest,
  EnabledProvidersResponse,
  SSOProvider,
  OrganizationSSOSettings,
  UpdateOrganizationSSOSettingsRequest,
  SetSSOAllowedRequest,
} from '@/types/sso'

export const ssoApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * Get SSO settings for the current user's organization
     */
    getSSOSettings: builder.query<OrganizationSSOSettings, void>({
      query: () => '/organization-sso-settings',
      providesTags: ['SSO'],
    }),

    /**
     * Update SSO settings for the current user's organization
     */
    updateSSOSettings: builder.mutation<OrganizationSSOSettings, UpdateOrganizationSSOSettingsRequest>({
      query: (data) => ({
        url: '/organization-sso-settings',
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: ['SSO'],
    }),

    /**
     * Get list of enabled SSO providers for an organization
     */
    getEnabledSSOProviders: builder.query<EnabledProvidersResponse, { orgSlug: string }>({
      query: ({ orgSlug }) => ({
        url: '/organization-sso-settings/enabled-providers',
        params: { org_slug: orgSlug },
      }),
      providesTags: ['SSO'],
    }),

    /**
     * Get SSO settings for a specific organization (super admin only)
     */
    getOrgSSOSettings: builder.query<OrganizationSSOSettings, { organizationId: string }>({
      query: ({ organizationId }) => `/organization-sso-settings/organization/${organizationId}`,
      providesTags: (_result, _error, { organizationId }) => [{ type: 'SSO', id: organizationId }],
    }),

    /**
     * Set SSO allowed for an organization (super admin only)
     */
    setSSOAllowed: builder.mutation<OrganizationSSOSettings, { organizationId: string; ssoAllowed: boolean }>({
      query: ({ organizationId, ssoAllowed }) => ({
        url: `/organization-sso-settings/organization/${organizationId}/allow`,
        method: 'PUT',
        body: { sso_allowed: ssoAllowed } as SetSSOAllowedRequest,
      }),
      invalidatesTags: (_result, _error, { organizationId }) => [{ type: 'SSO', id: organizationId }, 'SSO'],
    }),

    /**
     * Initiate SSO login flow by getting the authorization URL
     */
    initiateSSOLogin: builder.query<
      SSOAuthorizationResponse,
      { provider: SSOProvider; orgSlug: string }
    >({
      query: ({ provider, orgSlug }) => ({
        url: `/sso/${provider}/authorize`,
        params: { org_slug: orgSlug },
      }),
    }),

    /**
     * Handle SSO callback after OAuth provider redirects back
     * This endpoint exchanges the authorization code for JWT tokens
     * or returns a linking required response if account linking is needed
     */
    handleSSOCallback: builder.query<
      SSOCallbackResponse,
      { provider: SSOProvider; code: string; state: string }
    >({
      query: ({ provider, code, state }) => ({
        url: `/sso/${provider}/callback`,
        params: { code, state },
      }),
    }),

    /**
     * Confirm account linking after SSO callback returns requires_linking
     * This endpoint creates the user identity link and returns JWT tokens
     */
    confirmAccountLink: builder.mutation<SSOCallbackSuccessResponse, ConfirmLinkRequest>({
      query: (data) => ({
        url: '/auth/sso/link',
        method: 'POST',
        body: data,
      }),
    }),
  }),
})

export const {
  useGetSSOSettingsQuery,
  useUpdateSSOSettingsMutation,
  useGetOrgSSOSettingsQuery,
  useLazyGetOrgSSOSettingsQuery,
  useSetSSOAllowedMutation,
  useGetEnabledSSOProvidersQuery,
  useLazyGetEnabledSSOProvidersQuery,
  useLazyInitiateSSOLoginQuery,
  useLazyHandleSSOCallbackQuery,
  useConfirmAccountLinkMutation,
} = ssoApi
