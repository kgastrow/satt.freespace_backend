import { api } from '@/store/api'

export interface OrganizationTwoFactorSettings {
  id: string
  organization_id: string
  two_factor_allowed: boolean
  two_factor_policy: 'disabled' | 'optional' | 'mandatory'
  grace_period_days: number
  enforcement_start_time: string | null
  two_factor_app_name: string | null
  created_time: string
  updated_time: string
}

export interface OrganizationTwoFactorSettingsUpdateRequest {
  two_factor_policy: 'disabled' | 'optional' | 'mandatory'
  grace_period_days: number
  two_factor_app_name?: string | null
}

export interface SuperAdminAllowRequest {
  two_factor_allowed: boolean
}

export interface UsersWithout2FAResponse {
  users: Array<{
    id: string
    email: string
    first_name: string
    last_name: string
  }>
  total: number
}

export interface UserTwoFactorSetupResponse {
  secret: string
  provisioning_uri: string
}

export interface UserTwoFactorVerifyRequest {
  code: string
  secret: string
}

export interface UserTwoFactorStatusResponse {
  is_enabled: boolean
  verified_at: string | null
}

export interface BackupCodesResponse {
  backup_codes: string[]
}

export interface BackupCodesInfoResponse {
  total_codes: number
  remaining_codes: number
  used_codes: number
}

export interface DisableTwoFactorRequest {
  password: string
}

export interface TwoFactorPolicyResponse {
  two_factor_available: boolean
  two_factor_policy: 'disabled' | 'optional' | 'mandatory'
  is_mandatory: boolean
  grace_period_days: number | null
  enforcement_deadline: string | null
  user_has_2fa: boolean
  requires_setup: boolean
}

export const twoFactorApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /two-factor/policy - Get org 2FA policy for current user (no special permissions needed)
     */
    getTwoFactorPolicy: builder.query<TwoFactorPolicyResponse, void>({
      query: () => '/two-factor/policy',
      providesTags: [{ type: 'TwoFactorSettings', id: 'POLICY' }, { type: 'UserTwoFactor', id: 'STATUS' }],
    }),

    /**
     * GET /organization-two-factor-settings - Get organization 2FA settings
     */
    getOrganizationTwoFactorSettings: builder.query<OrganizationTwoFactorSettings, void>({
      query: () => '/organization-two-factor-settings',
      providesTags: [{ type: 'TwoFactorSettings', id: 'ORG' }],
    }),

    /**
     * PUT /organization-two-factor-settings - Update organization 2FA settings
     */
    updateOrganizationTwoFactorSettings: builder.mutation<
      OrganizationTwoFactorSettings,
      OrganizationTwoFactorSettingsUpdateRequest
    >({
      query: (body) => ({
        url: '/organization-two-factor-settings',
        method: 'PUT',
        body,
      }),
      invalidatesTags: [{ type: 'TwoFactorSettings', id: 'ORG' }],
    }),

    /**
     * PUT /organization-two-factor-settings/organization/{id}/allow - Super admin: allow/disallow 2FA for organization
     */
    updateOrganizationTwoFactorAllow: builder.mutation<
      OrganizationTwoFactorSettings,
      { organizationId: string; body: SuperAdminAllowRequest }
    >({
      query: ({ organizationId, body }) => ({
        url: `/organization-two-factor-settings/organization/${organizationId}/allow`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: [{ type: 'TwoFactorSettings', id: 'ORG' }],
    }),

    /**
     * GET /two-factor/users-without-2fa - Get users in organization without 2FA enabled
     */
    getUsersWithout2FA: builder.query<UsersWithout2FAResponse, void>({
      query: () => '/two-factor/users-without-2fa',
      providesTags: [{ type: 'TwoFactorSettings', id: 'USERS_WITHOUT_2FA' }],
    }),

    /**
     * GET /two-factor/status - Get current user's 2FA status
     */
    getUserTwoFactorStatus: builder.query<UserTwoFactorStatusResponse, void>({
      query: () => '/two-factor/status',
      providesTags: [{ type: 'UserTwoFactor', id: 'STATUS' }],
    }),

    /**
     * POST /two-factor/setup - Initialize 2FA setup (get secret and QR code URI)
     */
    initiateTwoFactorSetup: builder.mutation<UserTwoFactorSetupResponse, void>({
      query: () => ({
        url: '/two-factor/setup',
        method: 'POST',
      }),
    }),

    /**
     * POST /two-factor/verify-setup - Verify TOTP code to enable 2FA
     */
    verifyTwoFactorSetup: builder.mutation<BackupCodesResponse, UserTwoFactorVerifyRequest>({
      query: (body) => ({
        url: '/two-factor/verify-setup',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'UserTwoFactor', id: 'STATUS' }],
    }),

    /**
     * DELETE /two-factor/setup - Disable 2FA for current user
     * Requires password re-authentication
     */
    disableTwoFactor: builder.mutation<void, DisableTwoFactorRequest>({
      query: (body) => ({
        url: '/two-factor/setup',
        method: 'DELETE',
        body,
      }),
      invalidatesTags: [{ type: 'UserTwoFactor', id: 'STATUS' }],
    }),

    /**
     * GET /two-factor/backup-codes - Get backup codes info (count of remaining codes)
     */
    getBackupCodesInfo: builder.query<BackupCodesInfoResponse, void>({
      query: () => '/two-factor/backup-codes',
      providesTags: [{ type: 'UserTwoFactor', id: 'BACKUP_CODES' }],
    }),

    /**
     * POST /two-factor/regenerate-backup-codes - Regenerate backup codes
     */
    regenerateBackupCodes: builder.mutation<BackupCodesResponse, void>({
      query: () => ({
        url: '/two-factor/regenerate-backup-codes',
        method: 'POST',
      }),
      invalidatesTags: [{ type: 'UserTwoFactor', id: 'BACKUP_CODES' }],
    }),
  }),
})

export const {
  useGetTwoFactorPolicyQuery,
  useLazyGetTwoFactorPolicyQuery,
  useGetOrganizationTwoFactorSettingsQuery,
  useUpdateOrganizationTwoFactorSettingsMutation,
  useUpdateOrganizationTwoFactorAllowMutation,
  useGetUsersWithout2FAQuery,
  useGetUserTwoFactorStatusQuery,
  useInitiateTwoFactorSetupMutation,
  useVerifyTwoFactorSetupMutation,
  useDisableTwoFactorMutation,
  useGetBackupCodesInfoQuery,
  useRegenerateBackupCodesMutation,
} = twoFactorApi
