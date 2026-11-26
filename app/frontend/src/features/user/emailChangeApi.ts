import { api } from '@/store/api'

// Type definitions based on backend serializers
export type EmailChangeStatus = 'pending_verification' | 'pending_otp' | 'completed' | 'expired' | 'cancelled'
export type IdentityVerificationMethod = 'password' | 'totp' | 'sms_2fa'

export type InitiateEmailChangeRequest = {
  new_email: string
}

export type InitiateEmailChangeResponse = {
  message: string
  message_code: string
  request_id: string
}

export type VerifyIdentityRequest = {
  verification_method: IdentityVerificationMethod
  verification_value: string
}

export type VerifyIdentityResponse = {
  message: string
  message_code: string
}

export type VerifyOTPRequest = {
  otp_code: string
}

export type VerifyOTPResponse = {
  message: string
  message_code: string
}

export type ResendOTPResponse = {
  message: string
  message_code: string
}

export type CancelEmailChangeResponse = {
  message: string
  message_code: string
}

export type EmailChangeStatusResponse = {
  has_active_request: boolean
  request_id?: string
  old_email?: string
  new_email?: string
  status?: EmailChangeStatus
  identity_verified?: boolean
  otp_attempts?: number
  otp_resend_count?: number
  expires_at?: string
}

export const emailChangeApi = api.injectEndpoints({
  endpoints: (builder) => ({
    initiateEmailChange: builder.mutation<InitiateEmailChangeResponse, InitiateEmailChangeRequest>({
      query: (body) => ({
        url: '/users/me/email/change',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['User'],
    }),

    verifyIdentity: builder.mutation<VerifyIdentityResponse, VerifyIdentityRequest>({
      query: (body) => ({
        url: '/users/me/email/change/verify',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['User'],
    }),

    verifyOTP: builder.mutation<VerifyOTPResponse, VerifyOTPRequest>({
      query: (body) => ({
        url: '/users/me/email/change/otp',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['User'],
    }),

    resendOTP: builder.mutation<ResendOTPResponse, void>({
      query: () => ({
        url: '/users/me/email/change/resend',
        method: 'POST',
      }),
    }),

    cancelEmailChange: builder.mutation<CancelEmailChangeResponse, void>({
      query: () => ({
        url: '/users/me/email/change',
        method: 'DELETE',
      }),
      invalidatesTags: ['User'],
    }),

    getEmailChangeStatus: builder.query<EmailChangeStatusResponse, void>({
      query: () => '/users/me/email/change/status',
      providesTags: ['User'],
    }),
  }),
})

export const {
  useInitiateEmailChangeMutation,
  useVerifyIdentityMutation,
  useVerifyOTPMutation,
  useResendOTPMutation,
  useCancelEmailChangeMutation,
  useGetEmailChangeStatusQuery,
  useLazyGetEmailChangeStatusQuery,
} = emailChangeApi
