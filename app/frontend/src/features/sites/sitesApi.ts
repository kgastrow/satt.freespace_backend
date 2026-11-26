import { api } from '@/store/api'
import type {
  Site,
  SiteListResponse,
  SiteListParams,
  CreateSiteRequest,
  UpdateSiteRequest,
  SiteMutationResponse,
  MessageResponse,
  SiteConfig,
  UpdateSiteConfigRequest,
  UpdateSiteConfigResponse,
  AdvisoryType,
  SiteTemplateListResponse,
  UpdateSiteTemplateResponse,
  ZoneListResponse,
  CreateZoneRequest,
  UpdateZoneRequest,
  ZoneMutationResponse,
} from '@/types/site'

/**
 * Freespace admin API: /admin/sites and its sub-resources.
 *
 * Tags: `Site` (identity), `SiteConfig` (settings), `SiteTemplate`, `SiteZone`.
 * Later pages (live view, events, history) should add their own slice file in
 * this folder and their own tag in store/api.ts; invalidate `Site` LIST from
 * there only if they change site identity.
 */
export const sitesApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getSites: builder.query<SiteListResponse, SiteListParams | void>({
      query: (params) => {
        const { limit = 50, offset = 0, organization_id } = params || {}
        const search = new URLSearchParams({ limit: String(limit), offset: String(offset) })
        if (organization_id) search.set('organization_id', organization_id)
        return `/admin/sites?${search.toString()}`
      },
      providesTags: (result) => [
        ...(result?.items ?? []).map(({ id }) => ({ type: 'Site' as const, id })),
        { type: 'Site', id: 'LIST' },
      ],
    }),

    getSite: builder.query<Site, string>({
      query: (id) => `/admin/sites/${id}`,
      providesTags: (_r, _e, id) => [{ type: 'Site', id }],
    }),

    createSite: builder.mutation<SiteMutationResponse, CreateSiteRequest>({
      query: (body) => ({ url: '/admin/sites', method: 'POST', body }),
      invalidatesTags: [{ type: 'Site', id: 'LIST' }],
    }),

    updateSite: builder.mutation<SiteMutationResponse, { id: string; data: UpdateSiteRequest }>({
      query: ({ id, data }) => ({ url: `/admin/sites/${id}`, method: 'PUT', body: data }),
      invalidatesTags: (_r, _e, { id }) => [
        { type: 'Site', id },
        { type: 'Site', id: 'LIST' },
      ],
    }),

    deleteSite: builder.mutation<MessageResponse, string>({
      query: (id) => ({ url: `/admin/sites/${id}`, method: 'DELETE' }),
      invalidatesTags: (_r, _e, id) => [
        { type: 'Site', id },
        { type: 'Site', id: 'LIST' },
      ],
    }),

    getSiteConfig: builder.query<SiteConfig, string>({
      query: (id) => `/admin/sites/${id}/config`,
      providesTags: (_r, _e, id) => [{ type: 'SiteConfig', id }],
    }),

    /** managed, listed and time_zone live here too, so `Site` is invalidated. */
    updateSiteConfig: builder.mutation<
      UpdateSiteConfigResponse,
      { id: string; data: UpdateSiteConfigRequest }
    >({
      query: ({ id, data }) => ({ url: `/admin/sites/${id}/config`, method: 'PUT', body: data }),
      invalidatesTags: (_r, _e, { id }) => [
        { type: 'SiteConfig', id },
        { type: 'Site', id },
        { type: 'Site', id: 'LIST' },
      ],
    }),

    getSiteTemplates: builder.query<SiteTemplateListResponse, string>({
      query: (id) => `/admin/sites/${id}/templates`,
      providesTags: (_r, _e, id) => [{ type: 'SiteTemplate', id }],
    }),

    updateSiteTemplate: builder.mutation<
      UpdateSiteTemplateResponse,
      { siteId: string; advisoryType: AdvisoryType; title: string; body: string }
    >({
      query: ({ siteId, advisoryType, title, body }) => ({
        url: `/admin/sites/${siteId}/templates/${advisoryType}`,
        method: 'PUT',
        body: { title, body },
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteTemplate', id: siteId }],
    }),

    resetSiteTemplate: builder.mutation<
      UpdateSiteTemplateResponse,
      { siteId: string; advisoryType: AdvisoryType }
    >({
      query: ({ siteId, advisoryType }) => ({
        url: `/admin/sites/${siteId}/templates/${advisoryType}/reset`,
        method: 'POST',
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteTemplate', id: siteId }],
    }),

    getZones: builder.query<ZoneListResponse, { siteId: string; discovered?: boolean }>({
      query: ({ siteId, discovered }) =>
        `/admin/sites/${siteId}/zones${discovered === undefined ? '' : `?discovered=${discovered}`}`,
      providesTags: (_r, _e, { siteId }) => [{ type: 'SiteZone', id: siteId }],
    }),

    createZone: builder.mutation<ZoneMutationResponse, { siteId: string; data: CreateZoneRequest }>({
      query: ({ siteId, data }) => ({
        url: `/admin/sites/${siteId}/zones`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteZone', id: siteId }],
    }),

    updateZone: builder.mutation<
      ZoneMutationResponse,
      { siteId: string; zoneId: string; data: UpdateZoneRequest }
    >({
      query: ({ siteId, zoneId, data }) => ({
        url: `/admin/sites/${siteId}/zones/${zoneId}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteZone', id: siteId }],
    }),

    deleteZone: builder.mutation<MessageResponse, { siteId: string; zoneId: string }>({
      query: ({ siteId, zoneId }) => ({
        url: `/admin/sites/${siteId}/zones/${zoneId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'SiteZone', id: siteId }],
    }),
  }),
})

export const {
  useGetSitesQuery,
  useGetSiteQuery,
  useCreateSiteMutation,
  useUpdateSiteMutation,
  useDeleteSiteMutation,
  useGetSiteConfigQuery,
  useUpdateSiteConfigMutation,
  useGetSiteTemplatesQuery,
  useUpdateSiteTemplateMutation,
  useResetSiteTemplateMutation,
  useGetZonesQuery,
  useCreateZoneMutation,
  useUpdateZoneMutation,
  useDeleteZoneMutation,
} = sitesApi
