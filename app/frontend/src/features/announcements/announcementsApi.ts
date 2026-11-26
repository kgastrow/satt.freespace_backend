import { api } from '@/store/api'
import type {
  Announcement,
  ActiveAnnouncementsResponse,
  DismissAnnouncementResponse,
  AnnouncementListResponse,
  AnnouncementListParams,
  AnnouncementCreateRequest,
  AnnouncementUpdateRequest,
} from '@/types/announcement'

export const announcementsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /announcements/active - Get active announcements for current user
     */
    getActiveAnnouncements: builder.query<ActiveAnnouncementsResponse, void>({
      query: () => '/announcements/active',
      providesTags: (result) =>
        result
          ? [
              ...result.announcements.map(({ id }) => ({
                type: 'Announcement' as const,
                id,
              })),
              { type: 'Announcement', id: 'ACTIVE' },
            ]
          : [{ type: 'Announcement', id: 'ACTIVE' }],
    }),

    /**
     * POST /announcements/{id}/dismiss - Dismiss announcement for current user
     */
    dismissAnnouncement: builder.mutation<DismissAnnouncementResponse, string>({
      query: (announcementId) => ({
        url: `/announcements/${announcementId}/dismiss`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, announcementId) => [
        { type: 'Announcement', id: announcementId },
        { type: 'Announcement', id: 'ACTIVE' },
      ],
    }),

    /**
     * GET /announcements - List all announcements (admin view)
     */
    getAnnouncements: builder.query<
      AnnouncementListResponse,
      AnnouncementListParams | void
    >({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/announcements${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'Announcement' as const,
                id,
              })),
              { type: 'Announcement', id: 'LIST' },
            ]
          : [{ type: 'Announcement', id: 'LIST' }],
    }),

    /**
     * GET /announcements/{id} - Get a single announcement
     */
    getAnnouncement: builder.query<Announcement, string>({
      query: (id) => `/announcements/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Announcement', id }],
    }),

    /**
     * POST /announcements - Create a new announcement
     */
    createAnnouncement: builder.mutation<Announcement, AnnouncementCreateRequest>({
      query: (body) => ({
        url: '/announcements',
        method: 'POST',
        body,
      }),
      invalidatesTags: [
        { type: 'Announcement', id: 'LIST' },
        { type: 'Announcement', id: 'ACTIVE' },
      ],
    }),

    /**
     * PUT /announcements/{id} - Update an announcement
     */
    updateAnnouncement: builder.mutation<
      Announcement,
      { id: string; body: AnnouncementUpdateRequest }
    >({
      query: ({ id, body }) => ({
        url: `/announcements/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Announcement', id },
        { type: 'Announcement', id: 'LIST' },
        { type: 'Announcement', id: 'ACTIVE' },
      ],
    }),

    /**
     * DELETE /announcements/{id} - Soft delete an announcement
     */
    deleteAnnouncement: builder.mutation<void, string>({
      query: (id) => ({
        url: `/announcements/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Announcement', id },
        { type: 'Announcement', id: 'LIST' },
        { type: 'Announcement', id: 'ACTIVE' },
      ],
    }),
  }),
})

export const {
  useGetActiveAnnouncementsQuery,
  useDismissAnnouncementMutation,
  useGetAnnouncementsQuery,
  useGetAnnouncementQuery,
  useCreateAnnouncementMutation,
  useUpdateAnnouncementMutation,
  useDeleteAnnouncementMutation,
} = announcementsApi
