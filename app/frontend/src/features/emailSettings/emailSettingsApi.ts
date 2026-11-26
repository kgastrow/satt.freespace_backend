import { api } from '@/store/api'

export type EmailProvider = 'smtp' | 'sendgrid' | null

export interface EmailSettings {
  id: string
  organization_id: string
  provider: EmailProvider
  provider_display: string
  smtp_host: string | null
  smtp_port: number | null
  smtp_username: string | null
  smtp_password_set: boolean
  smtp_use_tls: boolean | null
  smtp_use_ssl: boolean | null
  sendgrid_api_key_set: boolean
  sender_email: string | null
  sender_name: string | null
  reply_to_email: string | null
  created_time: string | null
  updated_time: string | null
  using_platform_defaults: boolean
}

export interface EffectiveEmailConfig {
  provider: string
  provider_display: string
  smtp_host: string | null
  smtp_port: number | null
  smtp_username_set: boolean
  smtp_password_set: boolean
  smtp_use_tls: boolean
  smtp_use_ssl: boolean
  sendgrid_api_key_set: boolean
  sender_email: string | null
  sender_name: string | null
  reply_to_email: string | null
  config_source: 'organization' | 'platform' | 'default'
}

export interface UpdateEmailSettingsRequest {
  provider?: EmailProvider
  smtp_host?: string | null
  smtp_port?: number | null
  smtp_username?: string | null
  smtp_password?: string | null
  smtp_use_tls?: boolean | null
  smtp_use_ssl?: boolean | null
  sendgrid_api_key?: string | null
  sender_email?: string | null
  sender_name?: string | null
  reply_to_email?: string | null
}

export interface TestEmailRequest {
  recipient_email: string
}

export interface TestEmailResponse {
  success: boolean
  message: string
  message_code: string
  provider_used: string
}

export interface ResetEmailSettingsResponse {
  message: string
  message_code: string
}

export const emailSettingsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /email-settings - Get organization email settings
     */
    getEmailSettings: builder.query<EmailSettings, void>({
      query: () => '/email-settings',
      providesTags: ['EmailSettings'],
    }),

    /**
     * GET /email-settings/effective - Get effective email configuration
     */
    getEffectiveEmailConfig: builder.query<EffectiveEmailConfig, void>({
      query: () => '/email-settings/effective',
      providesTags: ['EmailSettings'],
    }),

    /**
     * PUT /email-settings - Update email settings
     */
    updateEmailSettings: builder.mutation<EmailSettings, UpdateEmailSettingsRequest>({
      query: (body) => ({
        url: '/email-settings',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['EmailSettings'],
    }),

    /**
     * POST /email-settings/test - Send test email
     */
    testEmailSettings: builder.mutation<TestEmailResponse, TestEmailRequest>({
      query: (body) => ({
        url: '/email-settings/test',
        method: 'POST',
        body,
      }),
    }),

    /**
     * DELETE /email-settings - Reset to platform defaults
     */
    resetEmailSettings: builder.mutation<ResetEmailSettingsResponse, void>({
      query: () => ({
        url: '/email-settings',
        method: 'DELETE',
      }),
      invalidatesTags: ['EmailSettings'],
    }),
  }),
})

export const {
  useGetEmailSettingsQuery,
  useGetEffectiveEmailConfigQuery,
  useUpdateEmailSettingsMutation,
  useTestEmailSettingsMutation,
  useResetEmailSettingsMutation,
} = emailSettingsApi
