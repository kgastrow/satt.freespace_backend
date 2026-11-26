import { api } from '@/store/api'
import type {
  InAppNotification,
  InAppNotificationListResponse,
  UnreadCountResponse,
  DismissNotificationsRequest,
  MarkReadResponse,
  DismissResponse,
  InAppNotificationListParams,
} from '@/types/in-app-notification'

export const inAppNotificationsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /notifications/in-app - List in-app notifications for current user
     */
    getInAppNotifications: builder.query<
      InAppNotificationListResponse,
      InAppNotificationListParams | void
    >({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.unread_only) {
          searchParams.append('unread_only', 'true')
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/notifications/in-app${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'InAppNotification' as const,
                id,
              })),
              { type: 'InAppNotification', id: 'LIST' },
            ]
          : [{ type: 'InAppNotification', id: 'LIST' }],
    }),

    /**
     * GET /notifications/in-app/:id - Get a single notification
     */
    getInAppNotification: builder.query<InAppNotification, string>({
      query: (id) => `/notifications/in-app/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'InAppNotification', id }],
    }),

    /**
     * GET /notifications/in-app/unread-count - Get unread count
     */
    getUnreadCount: builder.query<UnreadCountResponse, void>({
      query: () => '/notifications/in-app/unread-count',
      providesTags: [{ type: 'InAppNotification', id: 'UNREAD_COUNT' }],
    }),

    /**
     * POST /notifications/in-app/:id/read - Mark single notification as read
     */
    markAsRead: builder.mutation<MarkReadResponse, string>({
      query: (notificationId) => ({
        url: `/notifications/in-app/${notificationId}/read`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, notificationId) => [
        { type: 'InAppNotification', id: notificationId },
        { type: 'InAppNotification', id: 'UNREAD_COUNT' },
      ],
    }),

    /**
     * POST /notifications/in-app/mark-all-read - Mark all notifications as read
     */
    markAllAsRead: builder.mutation<MarkReadResponse, void>({
      query: () => ({
        url: '/notifications/in-app/mark-all-read',
        method: 'POST',
      }),
      invalidatesTags: [
        { type: 'InAppNotification', id: 'LIST' },
        { type: 'InAppNotification', id: 'UNREAD_COUNT' },
      ],
    }),

    /**
     * POST /notifications/in-app/dismiss - Dismiss multiple notifications
     */
    dismissNotifications: builder.mutation<DismissResponse, string[]>({
      query: (notificationIds) => ({
        url: '/notifications/in-app/dismiss',
        method: 'POST',
        body: { notification_ids: notificationIds } as DismissNotificationsRequest,
      }),
      invalidatesTags: (_result, _error, notificationIds) => [
        ...notificationIds.map((id) => ({
          type: 'InAppNotification' as const,
          id,
        })),
        { type: 'InAppNotification', id: 'LIST' },
        { type: 'InAppNotification', id: 'UNREAD_COUNT' },
      ],
    }),
  }),
})

export const {
  useGetInAppNotificationsQuery,
  useGetInAppNotificationQuery,
  useGetUnreadCountQuery,
  useMarkAsReadMutation,
  useMarkAllAsReadMutation,
  useDismissNotificationsMutation,
} = inAppNotificationsApi
