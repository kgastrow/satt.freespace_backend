import { api } from '@/store/api'
import type {
  Notification,
  NotificationListResponse,
  NotificationTemplate,
  TemplateListResponse,
  NotificationCategory,
  CategoryListResponse,
  CategoryPreferencesResponse,
  BulkNotification,
  NotificationSettings,
  UserNotificationPreference,
  SendNotificationRequest,
  CreateBulkNotificationRequest,
  CreateTemplateRequest,
  UpdateTemplateRequest,
  CreateCategoryRequest,
  UpdateCategoryRequest,
  UpdateNotificationSettingsRequest,
  UpdateUserPreferenceRequest,
  UpdateCategoryPreferenceRequest,
  UnsubscribeInfoResponse,
} from '@/types/generated'

// Re-export for backwards compatibility
export type {
  Notification,
  NotificationListResponse,
  NotificationTemplate,
  TemplateListResponse,
  NotificationCategory,
  CategoryListResponse,
  CategoryPreferencesResponse,
  BulkNotification,
  NotificationSettings,
  UserNotificationPreference,
  SendNotificationRequest,
  CreateBulkNotificationRequest,
  CreateTemplateRequest,
  UpdateTemplateRequest,
  CreateCategoryRequest,
  UpdateCategoryRequest,
  UpdateNotificationSettingsRequest,
  UpdateUserPreferenceRequest,
  UpdateCategoryPreferenceRequest,
  UnsubscribeInfoResponse,
} from '@/types/generated'

// Frontend-only type aliases
export type NotificationChannel = 'email' | 'sms' | 'whatsapp' | 'in_app'
export type NotificationStatus = 'pending' | 'queued' | 'sent' | 'delivered' | 'failed'
export type BulkNotificationStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled'

export const notificationsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // =========================================================================
    // Notification History
    // =========================================================================
    getNotifications: builder.query<
      NotificationListResponse,
      {
        channel?: NotificationChannel
        status?: NotificationStatus
        user_id?: string
        date_from?: string
        date_to?: string
        sort?: string
        limit?: number
        offset?: number
      }
    >({
      query: ({ channel, status, user_id, date_from, date_to, sort, limit = 50, offset = 0 }) => {
        const params = new URLSearchParams()
        params.append('limit', limit.toString())
        params.append('offset', offset.toString())
        // SDL format filters
        if (channel) params.append('filter[channel]', channel)
        if (status) params.append('filter[status]', status)
        if (user_id) params.append('filter[user_id]', user_id)
        if (date_from) params.append('filter[created_time][gte]', date_from)
        if (date_to) params.append('filter[created_time][lte]', date_to)
        if (sort) params.append('sort', sort)
        return `/notifications?${params.toString()}`
      },
      providesTags: ['Notification'],
    }),

    getNotification: builder.query<Notification, string>({
      query: (id) => `/notifications/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Notification', id }],
    }),

    // =========================================================================
    // Send Notifications
    // =========================================================================
    sendNotification: builder.mutation<
      { message: string; notification: Notification },
      SendNotificationRequest
    >({
      query: (body) => ({
        url: '/notifications/send',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Notification'],
    }),

    // =========================================================================
    // Bulk Notifications
    // =========================================================================
    createBulkNotification: builder.mutation<
      { message: string; bulk_notification: BulkNotification },
      CreateBulkNotificationRequest
    >({
      query: (body) => ({
        url: '/notifications/bulk',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Notification'],
    }),

    getBulkNotification: builder.query<BulkNotification, string>({
      query: (id) => `/notifications/bulk/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Notification', id }],
    }),

    cancelBulkNotification: builder.mutation<
      { message: string; bulk_notification_id: string; status: string },
      string
    >({
      query: (id) => ({
        url: `/notifications/bulk/${id}/cancel`,
        method: 'POST',
      }),
      invalidatesTags: ['Notification'],
    }),

    // =========================================================================
    // Templates
    // =========================================================================
    getTemplates: builder.query<
      TemplateListResponse,
      { channel?: NotificationChannel; include_system?: boolean; sort?: string; limit?: number; offset?: number } | void
    >({
      query: (params) => {
        const { channel, include_system = true, sort, limit = 50, offset = 0 } = params ?? {}
        const searchParams = new URLSearchParams()
        searchParams.append('limit', limit.toString())
        searchParams.append('offset', offset.toString())
        searchParams.append('include_system', include_system.toString())
        // SDL format filters
        if (channel) searchParams.append('filter[channel]', channel)
        if (sort) searchParams.append('sort', sort)
        return `/notifications/templates?${searchParams.toString()}`
      },
      providesTags: ['Template'],
    }),

    createTemplate: builder.mutation<
      { message: string; template: NotificationTemplate },
      CreateTemplateRequest
    >({
      query: (body) => ({
        url: '/notifications/templates',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Template'],
    }),

    updateTemplate: builder.mutation<
      { message: string; template: NotificationTemplate },
      { id: string; data: UpdateTemplateRequest }
    >({
      query: ({ id, data }) => ({
        url: `/notifications/templates/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: ['Template'],
    }),

    deleteTemplate: builder.mutation<{ message: string; template_id: string }, string>({
      query: (id) => ({
        url: `/notifications/templates/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Template'],
    }),

    // =========================================================================
    // Categories
    // =========================================================================
    getNotificationCategories: builder.query<
      CategoryListResponse,
      { include_system?: boolean; sort?: string; limit?: number; offset?: number } | void
    >({
      query: (params) => {
        const { include_system = true, sort, limit = 50, offset = 0 } = params ?? {}
        const searchParams = new URLSearchParams()
        searchParams.append('limit', limit.toString())
        searchParams.append('offset', offset.toString())
        searchParams.append('include_system', include_system.toString())
        // SDL format sort
        if (sort) searchParams.append('sort', sort)
        return `/notifications/categories?${searchParams.toString()}`
      },
      providesTags: ['Category'],
    }),

    createCategory: builder.mutation<
      { message: string; category: NotificationCategory },
      CreateCategoryRequest
    >({
      query: (body) => ({
        url: '/notifications/categories',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Category'],
    }),

    updateCategory: builder.mutation<
      { message: string; category: NotificationCategory },
      { id: string; data: UpdateCategoryRequest }
    >({
      query: ({ id, data }) => ({
        url: `/notifications/categories/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: ['Category'],
    }),

    deleteCategory: builder.mutation<{ message: string; category_id: string }, string>({
      query: (id) => ({
        url: `/notifications/categories/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Category'],
    }),

    // =========================================================================
    // Organization Settings (Admin)
    // =========================================================================
    getNotificationSettings: builder.query<NotificationSettings, void>({
      query: () => '/notifications/settings',
      providesTags: ['NotificationSettings'],
    }),

    updateNotificationSettings: builder.mutation<
      { message: string; settings: NotificationSettings },
      UpdateNotificationSettingsRequest
    >({
      query: (body) => ({
        url: '/notifications/settings',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['NotificationSettings'],
    }),

    // =========================================================================
    // User Preferences
    // =========================================================================
    getUserPreferences: builder.query<UserNotificationPreference, void>({
      query: () => '/notifications/preferences',
      providesTags: ['UserPreference'],
    }),

    updateUserPreferences: builder.mutation<
      { message: string; preferences: UserNotificationPreference },
      UpdateUserPreferenceRequest
    >({
      query: (body) => ({
        url: '/notifications/preferences',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['UserPreference'],
    }),

    getCategoryPreferences: builder.query<CategoryPreferencesResponse, void>({
      query: () => '/notifications/preferences/categories',
      providesTags: ['UserPreference', 'Category'],
    }),

    updateCategoryPreference: builder.mutation<
      {
        message: string
        category_id: string
        email_enabled: boolean
        sms_enabled: boolean
        whatsapp_enabled: boolean
      },
      { category_id: string; data: UpdateCategoryPreferenceRequest }
    >({
      query: ({ category_id, data }) => ({
        url: `/notifications/preferences/categories/${category_id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: ['UserPreference'],
    }),

    // =========================================================================
    // Unsubscribe (Public)
    // =========================================================================
    getUnsubscribeInfo: builder.query<UnsubscribeInfoResponse, string>({
      query: (token) => `/notifications/unsubscribe?token=${encodeURIComponent(token)}`,
    }),

    processUnsubscribe: builder.mutation<{ message: string; success: boolean }, string>({
      query: (token) => ({
        url: '/notifications/unsubscribe',
        method: 'POST',
        body: { token },
      }),
    }),
  }),
})

export const {
  // Notifications
  useGetNotificationsQuery,
  useGetNotificationQuery,
  useSendNotificationMutation,
  // Bulk
  useCreateBulkNotificationMutation,
  useGetBulkNotificationQuery,
  useCancelBulkNotificationMutation,
  // Templates
  useGetTemplatesQuery,
  useCreateTemplateMutation,
  useUpdateTemplateMutation,
  useDeleteTemplateMutation,
  // Categories
  useGetNotificationCategoriesQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useDeleteCategoryMutation,
  // Settings
  useGetNotificationSettingsQuery,
  useUpdateNotificationSettingsMutation,
  // User Preferences
  useGetUserPreferencesQuery,
  useUpdateUserPreferencesMutation,
  useGetCategoryPreferencesQuery,
  useUpdateCategoryPreferenceMutation,
  // Unsubscribe
  useGetUnsubscribeInfoQuery,
  useProcessUnsubscribeMutation,
} = notificationsApi
