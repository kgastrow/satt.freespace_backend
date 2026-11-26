import { api } from '@/store/api'
import type {
  FileRecord,
  FileListResponse,
  FileUsage,
  OrgFileUsage,
  FileSettings,
  UploadUrlRequest,
  UploadUrlResponse,
  UploadCompleteRequest,
  UploadCompleteResponse,
  DownloadUrlResponse,
  UpdateFileSettingsRequest,
} from '@/types/generated'

// Re-export for backwards compatibility
export type {
  FileRecord,
  FileListResponse,
  FileUsage,
  OrgFileUsage,
  FileSettings,
  UploadUrlRequest,
  UploadUrlResponse,
  UploadCompleteRequest,
  UploadCompleteResponse,
  DownloadUrlResponse,
  UpdateFileSettingsRequest,
} from '@/types/generated'

export const filesApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // List current user's files
    getFiles: builder.query<
      FileListResponse,
      { category?: string; status?: string; sort?: string; limit?: number; offset?: number }
    >({
      query: ({ category, status, sort, limit = 50, offset = 0 }) => {
        const params = new URLSearchParams()
        params.append('limit', limit.toString())
        params.append('offset', offset.toString())
        if (category) params.append('filter[category]', category)
        if (status) params.append('filter[status]', status)
        if (sort) params.append('sort', sort)
        return `/files?${params.toString()}`
      },
      providesTags: ['File'],
    }),

    // List all organization files (admin only)
    getOrgFiles: builder.query<
      FileListResponse,
      { category?: string; status?: string; userId?: string; sort?: string; limit?: number; offset?: number }
    >({
      query: ({ category, status, userId, sort, limit = 50, offset = 0 }) => {
        const params = new URLSearchParams()
        params.append('limit', limit.toString())
        params.append('offset', offset.toString())
        if (category) params.append('filter[category]', category)
        if (status) params.append('filter[status]', status)
        if (userId) params.append('filter[user_id]', userId)
        if (sort) params.append('sort', sort)
        return `/files/organization?${params.toString()}`
      },
      providesTags: ['File'],
    }),

    // Get single file
    getFile: builder.query<FileRecord, string>({
      query: (id) => `/files/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'File', id }],
    }),

    // Upload file directly
    uploadFile: builder.mutation<FileRecord, FormData>({
      query: (formData) => ({
        url: '/files/upload',
        method: 'POST',
        body: formData,
      }),
      invalidatesTags: ['File'],
    }),

    // Get presigned upload URL
    getUploadUrl: builder.mutation<UploadUrlResponse, UploadUrlRequest>({
      query: (body) => ({
        url: '/files/upload-url',
        method: 'POST',
        body,
      }),
    }),

    // Confirm upload complete
    confirmUpload: builder.mutation<UploadCompleteResponse, UploadCompleteRequest>({
      query: (body) => ({
        url: '/files/upload-complete',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['File'],
    }),

    // Get download URL
    getDownloadUrl: builder.query<DownloadUrlResponse, string>({
      query: (id) => `/files/${id}/download`,
    }),

    // Get thumbnail URL (for images)
    getThumbnailUrl: builder.query<{ thumbnail_url: string; expires_at: string; filename: string }, string>({
      query: (id) => `/files/${id}/thumbnail`,
    }),

    // Delete file
    deleteFile: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/files/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['File'],
    }),

    // Get user usage
    getUserUsage: builder.query<FileUsage, void>({
      query: () => '/files/usage',
      providesTags: ['File'],
    }),

    // Get organization usage (admin)
    getOrgUsage: builder.query<OrgFileUsage, void>({
      query: () => '/files/usage/organization',
      providesTags: ['File'],
    }),

    // Get file settings (admin)
    getFileSettings: builder.query<FileSettings, void>({
      query: () => '/files/settings',
      providesTags: ['FileSettings'],
    }),

    // Update file settings (admin)
    updateFileSettings: builder.mutation<FileSettings, UpdateFileSettingsRequest>({
      query: (body) => ({
        url: '/files/settings',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['FileSettings'],
    }),
  }),
})

export const {
  useGetFilesQuery,
  useGetOrgFilesQuery,
  useGetFileQuery,
  useUploadFileMutation,
  useGetUploadUrlMutation,
  useConfirmUploadMutation,
  useLazyGetDownloadUrlQuery,
  useLazyGetThumbnailUrlQuery,
  useDeleteFileMutation,
  useGetUserUsageQuery,
  useGetOrgUsageQuery,
  useGetFileSettingsQuery,
  useUpdateFileSettingsMutation,
} = filesApi
