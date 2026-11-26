import { api } from '@/store/api'
import type {
  AnnouncementRequest,
  PushResponse,
  SiteEventListResponse,
  SiteEventQuery,
  TestPushRequest,
} from '@/types/siteLive'
import { eventQueryString } from './eventFilters'

/** Event log, CSV export, test push and announcements. Tag: SiteEvent. */
export const eventsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getSiteEvents: builder.query<SiteEventListResponse, { siteId: string; query: SiteEventQuery }>({
      query: ({ siteId, query }) => `/admin/sites/${siteId}/events${eventQueryString(query)}`,
      providesTags: (_r, _e, { siteId }) => [{ type: 'SiteEvent', id: siteId }],
    }),

    /**
     * CSV of the current filter. Fetched through the API layer so the bearer
     * token is attached; returned as text (Blobs are not serialisable in the
     * store) and turned into a download by the caller.
     */
    exportSiteEvents: builder.mutation<string, { siteId: string; query: SiteEventQuery }>({
      query: ({ siteId, query }) => ({
        url: `/admin/sites/${siteId}/events/export.csv${eventQueryString({ ...query, limit: undefined, offset: undefined })}`,
        responseHandler: 'text',
      }),
    }),

    sendTestPush: builder.mutation<PushResponse, { siteId: string; data: TestPushRequest }>({
      query: ({ siteId, data }) => ({
        url: `/admin/sites/${siteId}/test-push`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteEvent', id: siteId }],
    }),

    sendAnnouncement: builder.mutation<
      PushResponse,
      { siteId: string; data: AnnouncementRequest }
    >({
      query: ({ siteId, data }) => ({
        url: `/admin/sites/${siteId}/announcements`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteEvent', id: siteId }],
    }),
  }),
})

export const {
  useGetSiteEventsQuery,
  useExportSiteEventsMutation,
  useSendTestPushMutation,
  useSendAnnouncementMutation,
} = eventsApi
