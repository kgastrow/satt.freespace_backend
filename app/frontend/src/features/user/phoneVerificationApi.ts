import { api } from '@/store/api'

// Type definitions based on backend serializers
export type SendPhoneOTPRequest = {
  phone: string
}

export type SendPhoneOTPResponse = {
  message: string
  message_code: string
  verification_id: string
  expires_at: string
}

export type VerifyPhoneOTPRequest = {
  phone: string
  otp_code: string
}

export type VerifyPhoneOTPResponse = {
  message: string
  message_code: string
  verified: boolean
  phone?: string
}

export const phoneVerificationApi = api.injectEndpoints({
  endpoints: (builder) => ({
    sendPhoneOTP: builder.mutation<SendPhoneOTPResponse, SendPhoneOTPRequest>({
      query: (body) => ({
        url: '/user/me/phone/send-otp',
        method: 'POST',
        body,
      }),
    }),

    verifyPhoneOTP: builder.mutation<VerifyPhoneOTPResponse, VerifyPhoneOTPRequest>({
      query: (body) => ({
        url: '/user/me/phone/verify-otp',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['User'],
    }),
  }),
})

export const {
  useSendPhoneOTPMutation,
  useVerifyPhoneOTPMutation,
} = phoneVerificationApi
