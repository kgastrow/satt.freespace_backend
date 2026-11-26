import { api } from '@/store/api'
import type {
  ChangelogEntry,
  ChangelogListResponse,
  ChangelogListParams,
  CreateChangelogRequest,
  UpdateChangelogRequest,
  UnreadCountResponse,
} from '@/types/changelog'

export const changelogApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /changelogs/published - Get published entries for current user
     */
    getPublishedChangelogs: builder.query<
      ChangelogListResponse,
      ChangelogListParams | void
    >({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) searchParams.append('limit', params.limit.toString())
        if (params?.offset)
          searchParams.append('offset', params.offset.toString())
        if (params?.category) searchParams.append('category', params.category)
        const qs = searchParams.toString()
        return `/changelogs/published${qs ? `?${qs}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'Changelog' as const,
                id,
              })),
              { type: 'Changelog', id: 'PUBLISHED' },
            ]
          : [{ type: 'Changelog', id: 'PUBLISHED' }],
    }),

    /**
     * GET /changelogs/unread-count - Get unread count
     */
    getUnreadChangelogCount: builder.query<UnreadCountResponse, void>({
      query: () => '/changelogs/unread-count',
      providesTags: [{ type: 'Changelog', id: 'UNREAD' }],
    }),

    /**
     * POST /changelogs/{id}/view - Mark single as viewed
     */
    markChangelogViewed: builder.mutation<void, string>({
      query: (id) => ({
        url: `/changelogs/${id}/view`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Changelog', id },
        { type: 'Changelog', id: 'UNREAD' },
        { type: 'Changelog', id: 'PUBLISHED' },
      ],
    }),

    /**
     * POST /changelogs/mark-all-viewed - Mark all as viewed
     */
    markAllChangelogsViewed: builder.mutation<void, void>({
      query: () => ({
        url: '/changelogs/mark-all-viewed',
        method: 'POST',
      }),
      invalidatesTags: [
        { type: 'Changelog', id: 'UNREAD' },
        { type: 'Changelog', id: 'PUBLISHED' },
      ],
    }),

    /**
     * GET /changelogs - List all (admin, including drafts)
     */
    getChangelogs: builder.query<
      ChangelogListResponse,
      ChangelogListParams | void
    >({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) searchParams.append('limit', params.limit.toString())
        if (params?.offset)
          searchParams.append('offset', params.offset.toString())
        if (params?.category) searchParams.append('category', params.category)
        const qs = searchParams.toString()
        return `/changelogs${qs ? `?${qs}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'Changelog' as const,
                id,
              })),
              { type: 'Changelog', id: 'LIST' },
            ]
          : [{ type: 'Changelog', id: 'LIST' }],
    }),

    /**
     * POST /changelogs - Create
     */
    createChangelog: builder.mutation<ChangelogEntry, CreateChangelogRequest>({
      query: (body) => ({
        url: '/changelogs',
        method: 'POST',
        body,
      }),
      invalidatesTags: [
        { type: 'Changelog', id: 'LIST' },
        { type: 'Changelog', id: 'PUBLISHED' },
        { type: 'Changelog', id: 'UNREAD' },
      ],
    }),

    /**
     * PUT /changelogs/{id} - Update
     */
    updateChangelog: builder.mutation<
      ChangelogEntry,
      { id: string; body: UpdateChangelogRequest }
    >({
      query: ({ id, body }) => ({
        url: `/changelogs/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Changelog', id },
        { type: 'Changelog', id: 'LIST' },
        { type: 'Changelog', id: 'PUBLISHED' },
        { type: 'Changelog', id: 'UNREAD' },
      ],
    }),

    /**
     * DELETE /changelogs/{id} - Soft delete
     */
    deleteChangelog: builder.mutation<void, string>({
      query: (id) => ({
        url: `/changelogs/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Changelog', id },
        { type: 'Changelog', id: 'LIST' },
        { type: 'Changelog', id: 'PUBLISHED' },
        { type: 'Changelog', id: 'UNREAD' },
      ],
    }),
  }),
})

export const {
  useGetPublishedChangelogsQuery,
  useGetUnreadChangelogCountQuery,
  useMarkChangelogViewedMutation,
  useMarkAllChangelogsViewedMutation,
  useGetChangelogsQuery,
  useCreateChangelogMutation,
  useUpdateChangelogMutation,
  useDeleteChangelogMutation,
} = changelogApi
