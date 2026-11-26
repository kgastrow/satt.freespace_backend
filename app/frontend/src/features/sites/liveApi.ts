import { api } from '@/store/api'
import type {
  DeviceStatsResponse,
  SiteHistoryResponse,
  SiteLiveResponse,
  SiteSummaryResponse,
} from '@/types/siteLive'

/**
 * Read-only operations endpoints: summary (sites list), live view, device
 * statistics and occupancy history. Tags: SiteLive, SiteDevices, SiteHistory.
 */
export const liveApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getSitesSummary: builder.query<SiteSummaryResponse, void>({
      query: () => '/admin/sites/summary',
      providesTags: [{ type: 'SiteLive', id: 'SUMMARY' }],
    }),

    getSiteLive: builder.query<SiteLiveResponse, string>({
      query: (siteId) => `/admin/sites/${siteId}/live`,
      providesTags: (_r, _e, siteId) => [{ type: 'SiteLive', id: siteId }],
    }),

    getSiteHistory: builder.query<SiteHistoryResponse, { siteId: string; date?: string }>({
      query: ({ siteId, date }) =>
        `/admin/sites/${siteId}/history${date ? `?date=${encodeURIComponent(date)}` : ''}`,
      providesTags: (_r, _e, { siteId }) => [{ type: 'SiteHistory', id: siteId }],
    }),

    getAllDeviceStats: builder.query<DeviceStatsResponse, void>({
      query: () => '/admin/sites/device-stats',
      providesTags: [{ type: 'SiteDevices', id: 'ALL' }],
    }),

    getSiteDeviceStats: builder.query<DeviceStatsResponse, string>({
      query: (siteId) => `/admin/sites/${siteId}/device-stats`,
      providesTags: (_r, _e, siteId) => [{ type: 'SiteDevices', id: siteId }],
    }),
  }),
})

export const {
  useGetSitesSummaryQuery,
  useGetSiteLiveQuery,
  useGetSiteHistoryQuery,
  useGetAllDeviceStatsQuery,
  useGetSiteDeviceStatsQuery,
} = liveApi
