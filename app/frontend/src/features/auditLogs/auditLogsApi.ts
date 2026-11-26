import { api } from '@/store/api'
import type { AuditLog, AuditLogsListResponse } from '@/types/generated'

// Re-export for backwards compatibility
export type { AuditLog, AuditLogsListResponse } from '@/types/generated'

// Frontend-only type for query parameters using DSL format
export interface AuditLogsQueryParams {
  // DSL filters
  resource_type?: string
  action?: string
  actor_id?: string
  created_time_gte?: string // date_from
  created_time_lte?: string // date_to
  resource_name_contains?: string // search within resource_name filter
  // Search (searches resource_name)
  q?: string
  // Sort
  sort?: string
  // Pagination
  limit?: number
  offset?: number
}

export const auditLogsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getAuditLogs: builder.query<AuditLogsListResponse, AuditLogsQueryParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()

        // DSL filters
        if (params.resource_type) searchParams.set('filter[resource_type]', params.resource_type)
        if (params.action) searchParams.set('filter[action]', params.action)
        if (params.actor_id) searchParams.set('filter[actor_id]', params.actor_id)
        if (params.created_time_gte) searchParams.set('filter[created_time][gte]', params.created_time_gte)
        if (params.created_time_lte) searchParams.set('filter[created_time][lte]', params.created_time_lte)

        // Search
        if (params.q) searchParams.set('q', params.q)

        // Sort (default: created_time:desc)
        if (params.sort) searchParams.set('sort', params.sort)

        // Pagination
        searchParams.set('limit', String(params.limit || 50))
        searchParams.set('offset', String(params.offset || 0))

        return `/audit-logs?${searchParams.toString()}`
      },
      providesTags: ['AuditLog'],
    }),

    getAuditLog: builder.query<AuditLog, string>({
      query: (id) => `/audit-logs/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'AuditLog', id }],
    }),
  }),
})

export const { useGetAuditLogsQuery, useGetAuditLogQuery } = auditLogsApi
