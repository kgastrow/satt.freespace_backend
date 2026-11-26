import { api } from '@/store/api'
import type {
  LoginRequest,
  LoginResponse,
  RefreshTokenResponse,
  CurrentUserResponse,
  RegisterRequest,
  RegisterResponse,
  PasswordResetRequestPayload,
  PasswordResetConfirmPayload,
  VerifyEmailOTPPayload,
  SendVerificationEmailPayload,
  MessageResponse,
  LoginResponseWith2FA,
  Verify2FARequest,
  CheckEmailRequest,
  CheckEmailResponse,
} from '@/types/auth'

export const authApi = api.injectEndpoints({
  endpoints: (builder) => ({
    checkEmail: builder.mutation<CheckEmailResponse, CheckEmailRequest>({
      query: (body) => ({
        url: '/auth/check-email',
        method: 'POST',
        body,
      }),
    }),

    login: builder.mutation<LoginResponse | LoginResponseWith2FA, LoginRequest>({
      query: (credentials) => ({
        url: '/auth/login',
        method: 'POST',
        body: credentials,
      }),
    }),

    verify2FA: builder.mutation<LoginResponse, Verify2FARequest>({
      query: (body) => ({
        url: '/auth/verify-2fa',
        method: 'POST',
        body,
      }),
      // Invalidate backup codes cache in case a backup code was used for verification
      invalidatesTags: [{ type: 'UserTwoFactor', id: 'BACKUP_CODES' }],
    }),

    logout: builder.mutation<{ message: string }, void>({
      query: () => ({
        url: '/auth/logout',
        method: 'POST',
      }),
    }),

    refreshToken: builder.mutation<RefreshTokenResponse, void>({
      query: () => ({
        url: '/auth/refresh',
        method: 'POST',
      }),
    }),

    getCurrentUser: builder.query<CurrentUserResponse, void>({
      query: () => '/user/me',
      providesTags: ['User'],
    }),

    getUserPermissions: builder.query<{ permissions: string[] }, void>({
      query: () => '/user/permissions',
      providesTags: ['UserPermissions'],
    }),

    register: builder.mutation<RegisterResponse, RegisterRequest>({
      query: (body) => ({
        url: '/user/register',
        method: 'POST',
        body,
      }),
    }),

    requestPasswordReset: builder.mutation<MessageResponse, PasswordResetRequestPayload>({
      query: (body) => ({
        url: '/auth/password-reset/request',
        method: 'POST',
        body,
      }),
    }),

    confirmPasswordReset: builder.mutation<MessageResponse, PasswordResetConfirmPayload>({
      query: (body) => ({
        url: '/auth/password-reset/confirm',
        method: 'POST',
        body,
      }),
    }),

    verifyEmailOTP: builder.mutation<LoginResponse, VerifyEmailOTPPayload>({
      query: (body) => ({
        url: '/user-otp/verify-email',
        method: 'POST',
        body,
      }),
    }),

    sendVerificationEmail: builder.mutation<MessageResponse, SendVerificationEmailPayload>({
      query: (body) => ({
        url: '/user-otp/send-verification-email',
        method: 'POST',
        body,
      }),
    }),
  }),
})

export const {
  useCheckEmailMutation,
  useLoginMutation,
  useVerify2FAMutation,
  useLogoutMutation,
  useRefreshTokenMutation,
  useGetCurrentUserQuery,
  useLazyGetCurrentUserQuery,
  useGetUserPermissionsQuery,
  useLazyGetUserPermissionsQuery,
  useRegisterMutation,
  useRequestPasswordResetMutation,
  useConfirmPasswordResetMutation,
  useVerifyEmailOTPMutation,
  useSendVerificationEmailMutation,
} = authApi
