import { api } from '@/store/api'
import type {
  User,
  CreateUserRequest,
  UpdateUserRequest,
} from '@/types/generated'

// Re-export for backwards compatibility
export type {
  User,
  CreateUserRequest,
  UpdateUserRequest,
} from '@/types/generated'

// Types for user list with filtering/sorting/search (offset-based - legacy)
export interface UserListParams {
  limit?: number
  offset?: number
  fields?: string
  'filter[status]'?: string
  'filter[user_type_id]'?: string
  'filter[created_via]'?: string
  'filter[email_verified]'?: boolean
  sort?: string
  q?: string
}

// Types for cursor-based pagination (better performance for large datasets)
export interface UserCursorListParams {
  limit?: number
  cursor?: string | null
  fields?: string
  'filter[status]'?: string
  'filter[user_type_id]'?: string
  'filter[created_via]'?: string
  'filter[email_verified]'?: boolean
  q?: string
}

export interface UserTypeOnboardingInfo {
  id: string
  name: string
  code: string
  onboarding_status: string
  onboarded_at?: string | null
}

export interface UserRoleInfo {
  id: string
  name: string
}

export interface UserListItem {
  id: string
  email?: string | null
  email_verified?: boolean | null
  email_deliverable?: boolean | null
  phone?: string | null
  phone_verified?: boolean | null
  first_name?: string | null
  last_name?: string | null
  is_admin?: boolean | null
  created_time?: string | null
  updated_time?: string | null
  suspension_status?: string | null
  created_via?: string | null
  roles?: UserRoleInfo[] | null
  user_types?: UserTypeOnboardingInfo[] | null
  avatar_url?: string | null
  total_storage_bytes?: number | null
  last_login?: string | null
}

export interface UserListResponse {
  items: UserListItem[]
  total: number
  limit: number
  offset: number
}

export interface UserCursorListResponse {
  items: UserListItem[]
  total: number
  limit: number
  next_cursor: string | null
  has_more: boolean
}

// Types for user detail
export interface UserSessionInfo {
  id: string
  created_time: string
  updated_time?: string | null
  expires_at: string
  auth_provider?: string | null
  ip_address?: string | null
  user_agent?: string | null
  city?: string | null
  country?: string | null
  country_code?: string | null
  is_current: boolean
}

export interface TwoFactorStatusInfo {
  is_enabled: boolean
  verified_at?: string | null
  backup_codes_remaining: number
}

export interface FileUsageInfo {
  total_files: number
  total_size_bytes: number
  image_count: number
  image_size_bytes: number
  video_count: number
  video_size_bytes: number
  document_count: number
  document_size_bytes: number
  audio_count: number
  audio_size_bytes: number
  other_count: number
  other_size_bytes: number
}

export interface FeedbackSummaryInfo {
  id: string
  type: string
  subject: string
  status: string
  created_time: string
}

export interface NotificationPreferencesInfo {
  email_enabled: boolean
  sms_enabled: boolean
  push_enabled: boolean
  in_app_enabled: boolean
}

export interface IdentityProviderInfo {
  id: string
  provider: string
  provider_email?: string | null
  created_time: string
}

export interface DataExportInfo {
  id: string
  status: string
  created_time: string
  completed_at?: string | null
  file_size_bytes?: number | null
  download_count: number
  expires_at?: string | null
}

export interface ImpersonationHistoryInfo {
  id: string
  impersonator_id: string
  impersonator_name?: string | null
  created_time: string
  ended_time?: string | null
}

export interface SuspensionInfo {
  suspended_time?: string | null
  suspended_by?: string | null
  suspended_by_name?: string | null
  suspension_reason?: string | null
}

export interface UserFullDetail {
  id: string
  email: string
  email_verified: boolean
  email_deliverable: boolean
  phone?: string | null
  phone_verified: boolean
  first_name?: string | null
  last_name?: string | null
  is_admin: boolean
  created_time: string
  updated_time?: string | null
  created_via: string
  avatar_url?: string | null
  suspension_status: string
  suspension_info?: SuspensionInfo | null
  roles: UserRoleInfo[]
  user_types: UserTypeOnboardingInfo[]
  sessions: UserSessionInfo[]
  two_factor: TwoFactorStatusInfo
  identity_providers: IdentityProviderInfo[]
  file_usage?: FileUsageInfo | null
  feedback: FeedbackSummaryInfo[]
  data_exports: DataExportInfo[]
  impersonation_history: ImpersonationHistoryInfo[]
  notification_preferences?: NotificationPreferencesInfo | null
}

// Login History Types
export interface LoginHistoryEntry {
  id: string
  created_time: string
  success: boolean
  auth_method?: string | null
  ip_address?: string | null
  user_agent?: string | null
  city?: string | null
  country?: string | null
  country_code?: string | null
  failure_reason?: string | null
}

export interface LoginHistoryResponse {
  items: LoginHistoryEntry[]
  total: number
  limit: number
  offset: number
}

export interface LoginHistoryParams {
  userId: string
  limit?: number
  offset?: number
}

// Full Notification Preferences Types
export interface NotificationPreferencesFullInfo {
  email_enabled: boolean
  sms_enabled: boolean
  whatsapp_enabled: boolean
  in_app_enabled: boolean
  quiet_hours_enabled: boolean
  quiet_hours_start?: string | null
  quiet_hours_end?: string | null
  quiet_hours_timezone: string
}

export interface AdminNotificationPreferencesResponse {
  message: string
  message_code: string
  user_id: string
  preferences: NotificationPreferencesFullInfo
}

export interface UpdateNotificationPreferencesRequest {
  email_enabled?: boolean
  sms_enabled?: boolean
  whatsapp_enabled?: boolean
  in_app_enabled?: boolean
}

// User Type Management Types
export interface UserTypeActionResponse {
  message: string
  message_code: string
  user_id: string
  user_type_id: string
}

// ===== Invitation Types =====

export interface InvitationItem {
  id: string
  email: string
  invited_by_user_id: string
  invited_by_name?: string | null
  role_ids?: string[] | null
  user_type_ids?: string[] | null
  expires_at: string
  created_time?: string | null
}

export interface InvitationListResponse {
  items: InvitationItem[]
  total: number
}

export interface CreateInvitationPayload {
  email: string
  role_ids?: string[] | null
  user_type_ids?: string[] | null
}

export interface InvitationCreateResponse {
  message: string
  message_code: string
  invitation: InvitationItem
}

export interface ValidateInvitationResponse {
  email: string
  organization_slug: string
  expires_at: string
}

export const usersApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // User list with filtering, sorting, search (offset-based - legacy)
    getUsers: builder.query<UserListResponse, UserListParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
        if (params.offset !== undefined) searchParams.set('offset', String(params.offset))
        if (params.fields) searchParams.set('fields', params.fields)
        if (params['filter[status]']) searchParams.set('filter[status]', params['filter[status]'])
        if (params['filter[user_type_id]']) searchParams.set('filter[user_type_id]', params['filter[user_type_id]'])
        if (params['filter[created_via]']) searchParams.set('filter[created_via]', params['filter[created_via]'])
        if (params['filter[email_verified]'] !== undefined) {
          searchParams.set('filter[email_verified]', String(params['filter[email_verified]']))
        }
        if (params.sort) searchParams.set('sort', params.sort)
        if (params.q) searchParams.set('q', params.q)
        return `/users?${searchParams.toString()}`
      },
      providesTags: ['User'],
    }),

    // User list with cursor-based pagination (better performance for large datasets)
    getUsersCursor: builder.query<UserCursorListResponse, UserCursorListParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params.limit !== undefined) searchParams.set('limit', String(params.limit))
        if (params.cursor) searchParams.set('cursor', params.cursor)
        if (params.fields) searchParams.set('fields', params.fields)
        if (params['filter[status]']) searchParams.set('filter[status]', params['filter[status]'])
        if (params['filter[user_type_id]']) searchParams.set('filter[user_type_id]', params['filter[user_type_id]'])
        if (params['filter[created_via]']) searchParams.set('filter[created_via]', params['filter[created_via]'])
        if (params['filter[email_verified]'] !== undefined) {
          searchParams.set('filter[email_verified]', String(params['filter[email_verified]']))
        }
        if (params.q) searchParams.set('q', params.q)
        return `/users/cursor?${searchParams.toString()}`
      },
      providesTags: ['User'],
    }),

    getUser: builder.query<User, string>({
      query: (id) => `/users/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'User', id }],
    }),

    createUser: builder.mutation<User, CreateUserRequest>({
      query: (body) => ({
        url: '/users',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['User'],
    }),

    updateUser: builder.mutation<User, { id: string; data: UpdateUserRequest }>({
      query: ({ id, data }) => ({
        url: `/users/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'User', id }, 'User'],
    }),

    deleteUser: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/users/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['User'],
    }),

    suspendUser: builder.mutation<
      { message_code: string },
      { id: string; reason?: string; send_notification?: boolean }
    >({
      query: ({ id, reason, send_notification }) => ({
        url: `/users/${id}/suspend`,
        method: 'POST',
        body: { reason, send_notification },
      }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'User', id }, 'User'],
    }),

    unsuspendUser: builder.mutation<{ message_code: string }, string>({
      query: (id) => ({
        url: `/users/${id}/unsuspend`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, id) => [{ type: 'User', id }, 'User'],
    }),

    // Full user detail
    getUserDetail: builder.query<UserFullDetail, string>({
      query: (id) => `/users/${id}/detail`,
      providesTags: (_result, _error, id) => [
        { type: 'User', id },
        { type: 'Session', id },
      ],
    }),

    // Invalidate user session
    invalidateUserSession: builder.mutation<
      { message: string; session_id: string },
      { userId: string; sessionId: string }
    >({
      query: ({ userId, sessionId }) => ({
        url: `/users/${userId}/sessions/${sessionId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    // Login history
    getUserLoginHistory: builder.query<LoginHistoryResponse, LoginHistoryParams>({
      query: ({ userId, limit = 20, offset = 0 }) => {
        const params = new URLSearchParams()
        params.set('limit', String(limit))
        params.set('offset', String(offset))
        return `/users/${userId}/login-history?${params.toString()}`
      },
      providesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    // Notification preferences
    getUserNotificationPreferences: builder.query<AdminNotificationPreferencesResponse, string>({
      query: (userId) => `/users/${userId}/notification-preferences`,
      providesTags: (_result, _error, userId) => [{ type: 'User', id: userId }],
    }),

    updateUserNotificationPreferences: builder.mutation<
      AdminNotificationPreferencesResponse,
      { userId: string; data: UpdateNotificationPreferencesRequest }
    >({
      query: ({ userId, data }) => ({
        url: `/users/${userId}/notification-preferences`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    // User type management
    assignUserType: builder.mutation<
      UserTypeActionResponse,
      { userId: string; userTypeId: string }
    >({
      query: ({ userId, userTypeId }) => ({
        url: `/user-types/admin/users/${userId}/user-types/${userTypeId}`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    revokeUserType: builder.mutation<
      UserTypeActionResponse,
      { userId: string; userTypeId: string }
    >({
      query: ({ userId, userTypeId }) => ({
        url: `/user-types/admin/users/${userId}/user-types/${userTypeId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    resetUserTypeOnboarding: builder.mutation<
      UserTypeActionResponse,
      { userId: string; userTypeId: string }
    >({
      query: ({ userId, userTypeId }) => ({
        url: `/user-types/admin/users/${userId}/user-types/${userTypeId}/reset-onboarding`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, { userId }) => [{ type: 'User', id: userId }],
    }),

    // Admin 2FA disable
    adminDisable2FA: builder.mutation<
      { message: string; message_code: string; user_id: string },
      string
    >({
      query: (userId) => ({
        url: `/two-factor/admin/users/${userId}/2fa`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, userId) => [{ type: 'User', id: userId }],
    }),

    // Admin password reset
    adminSendPasswordReset: builder.mutation<
      { message: string; message_code: string; user_id: string },
      string
    >({
      query: (userId) => ({
        url: `/users/${userId}/password-reset`,
        method: 'POST',
      }),
    }),

    // ===== Invitation endpoints =====
    listInvitations: builder.query<InvitationListResponse, void>({
      query: () => '/invitations',
      providesTags: ['Invitation'],
    }),

    createInvitation: builder.mutation<InvitationCreateResponse, CreateInvitationPayload>({
      query: (body) => ({
        url: '/invitations',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Invitation'],
    }),

    revokeInvitation: builder.mutation<{ message: string; message_code: string }, string>({
      query: (invitationId) => ({
        url: `/invitations/${invitationId}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Invitation'],
    }),

    validateInvitationToken: builder.query<ValidateInvitationResponse, string>({
      query: (token) => `/invitations/validate/${token}`,
    }),
  }),
})

export const {
  useGetUsersQuery,
  useGetUsersCursorQuery,
  useGetUserQuery,
  useCreateUserMutation,
  useUpdateUserMutation,
  useDeleteUserMutation,
  useSuspendUserMutation,
  useUnsuspendUserMutation,
  useGetUserDetailQuery,
  useInvalidateUserSessionMutation,
  useGetUserLoginHistoryQuery,
  useGetUserNotificationPreferencesQuery,
  useUpdateUserNotificationPreferencesMutation,
  useAssignUserTypeMutation,
  useRevokeUserTypeMutation,
  useResetUserTypeOnboardingMutation,
  useAdminDisable2FAMutation,
  useAdminSendPasswordResetMutation,
  useListInvitationsQuery,
  useCreateInvitationMutation,
  useRevokeInvitationMutation,
  useValidateInvitationTokenQuery,
} = usersApi
