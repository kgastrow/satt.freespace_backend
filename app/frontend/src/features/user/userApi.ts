import { api } from '@/store/api'
import type {
  UpdateUserProfileRequest,
  ProfileResponse,
} from '@/types/generated'

// Re-export for backwards compatibility
export type { ProfileResponse } from '@/types/generated'

// Frontend-only type aliases for backwards compatibility
export type UpdateProfileRequest = UpdateUserProfileRequest
export type UpdatePasswordRequest = { password: string }
export type ChangePasswordRequest = {
  current_password: string
  new_password: string
}

// Data export types
// Note: These types are manually defined based on backend serializers
// until the OpenAPI schema is regenerated with the new endpoints
export type DataExportRequest = {
  id: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'expired'
  file_size_bytes: number | null
  expires_at: string | null
  completed_at: string | null
  download_count: number
  created_time: string
}

export type CreateExportRequestResponse = {
  message: string
  message_code: string
  request_id: string
}

export type ListExportRequestsResponse = {
  items: DataExportRequest[]
  total: number
  limit: number
  offset: number
}

export type ExportDownloadUrlResponse = {
  message: string
  message_code: string
  download_url: string
  expires_at: string
}

// Data deletion types
export type DataDeletionRequest = {
  id: string
  status: 'pending' | 'scheduled' | 'completed' | 'cancelled'
  scheduled_hard_delete_at: string | null
  hard_deleted_at: string | null
  cancelled_at: string | null
  cancellation_reason: string | null
  created_time: string
}

export type CreateDeletionRequestResponse = {
  message: string
  message_code: string
  request_id: string
  scheduled_hard_delete_at: string
}

export type CancelDeletionRequestResponse = {
  message: string
  message_code: string
}

export type GetDeletionStatusResponse = {
  has_active_request: boolean
  request: DataDeletionRequest | null
}

// Query parameters
export type ListExportsParams = {
  limit?: number
  offset?: number
}

export const userApi = api.injectEndpoints({
  endpoints: (builder) => ({
    updateProfile: builder.mutation<ProfileResponse, UpdateProfileRequest>({
      query: (body) => ({
        url: '/user/me',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['User'],
    }),

    updatePassword: builder.mutation<{ message: string }, UpdatePasswordRequest>({
      query: (body) => ({
        url: '/user/me',
        method: 'PUT',
        body,
      }),
    }),

    changePassword: builder.mutation<{ message: string }, ChangePasswordRequest>({
      query: (body) => ({
        url: '/user/me/change-password',
        method: 'POST',
        body,
      }),
    }),

    uploadAvatar: builder.mutation<{ avatar_url: string; full_avatar_url?: string }, File>({
      query: (file) => {
        const formData = new FormData()
        formData.append('file', file)
        return {
          url: '/user/me/avatar',
          method: 'POST',
          body: formData,
        }
      },
      invalidatesTags: ['User'],
    }),

    deleteAvatar: builder.mutation<{ message: string }, void>({
      query: () => ({
        url: '/user/me/avatar',
        method: 'DELETE',
      }),
      invalidatesTags: ['User'],
    }),

    // Data export endpoints
    requestExport: builder.mutation<CreateExportRequestResponse, void>({
      query: () => ({
        url: '/users/me/export',
        method: 'POST',
      }),
      // Note: Using 'User' tag as 'DataExport' is not yet registered in base API
      // This should be updated to use 'DataExport' tag once it's added to api.ts
      invalidatesTags: ['User'],
    }),

    getExports: builder.query<ListExportRequestsResponse, ListExportsParams | void>({
      query: (params) => ({
        url: '/users/me/exports',
        params: params || {},
      }),
      // Note: Using 'User' tag as 'DataExport' is not yet registered in base API
      // This should be updated to use 'DataExport' tag once it's added to api.ts
      providesTags: ['User'],
    }),

    getExportDownload: builder.mutation<ExportDownloadUrlResponse, string>({
      query: (exportId) => ({
        url: `/users/me/exports/${exportId}/download`,
        method: 'GET',
      }),
      // Note: Using 'User' tag as 'DataExport' is not yet registered in base API
      // This should be updated to use 'DataExport' tag once it's added to api.ts
      invalidatesTags: ['User'],
    }),

    // Data deletion endpoints
    requestDeletion: builder.mutation<CreateDeletionRequestResponse, void>({
      query: () => ({
        url: '/users/me/delete',
        method: 'POST',
      }),
      // Note: Using 'User' tag as 'DataDeletion' is not yet registered in base API
      // This should be updated to use 'DataDeletion' tag once it's added to api.ts
      invalidatesTags: ['User'],
    }),

    cancelDeletion: builder.mutation<CancelDeletionRequestResponse, void>({
      query: () => ({
        url: '/users/me/delete/cancel',
        method: 'POST',
      }),
      // Note: Using 'User' tag as 'DataDeletion' is not yet registered in base API
      // This should be updated to use 'DataDeletion' tag once it's added to api.ts
      invalidatesTags: ['User'],
    }),

    getDeletionStatus: builder.query<GetDeletionStatusResponse, void>({
      query: () => '/users/me/delete',
      // Note: Using 'User' tag as 'DataDeletion' is not yet registered in base API
      // This should be updated to use 'DataDeletion' tag once it's added to api.ts
      providesTags: ['User'],
    }),
  }),
})

export const {
  useUpdateProfileMutation,
  useUpdatePasswordMutation,
  useChangePasswordMutation,
  useUploadAvatarMutation,
  useDeleteAvatarMutation,
  useRequestExportMutation,
  useGetExportsQuery,
  useGetExportDownloadMutation,
  useRequestDeletionMutation,
  useCancelDeletionMutation,
  useGetDeletionStatusQuery,
} = userApi
