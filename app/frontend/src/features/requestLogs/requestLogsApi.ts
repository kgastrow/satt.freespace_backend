import { api } from '@/store/api'

// Request Log types (matching backend serializers)
export interface RequestLog {
  id: string
  created_time: string
  organization_id: string | null
  user_id: string | null
  method: string
  path: string
  status_code: number
  duration_ms: number
  request_body: Record<string, unknown> | null
  response_body: Record<string, unknown> | null
  ip_address: string
  user_agent: string
  error_traceback: string | null
}

export interface ListRequestLogsResponse {
  items: RequestLog[]
  next_cursor: string | null
  has_more: boolean
  limit: number
}

export interface CleanupResponse {
  message: string
  job_id: string
}

// Request logging configuration types
export interface RequestLoggingConfig {
  enabled: boolean
  db_enabled: boolean
  max_body_size: number
  retention_days: number
}

export interface UpdateRequestLoggingConfigRequest {
  enabled: boolean
  db_enabled: boolean
  max_body_size: number
  retention_days: number
}

// Query parameters for filtering
export interface RequestLogsQueryParams {
  method?: string
  path?: string
  status_code_min?: number
  status_code_max?: number
  date_from?: string
  date_to?: string
  organization_id?: string
  user_id?: string
  user_email?: string
  limit?: number
  cursor?: string
}

export const requestLogsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getRequestLogs: builder.query<ListRequestLogsResponse, RequestLogsQueryParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params.method) searchParams.set('method', params.method)
        if (params.path) searchParams.set('path', params.path)
        if (params.status_code_min !== undefined)
          searchParams.set('status_code_min', String(params.status_code_min))
        if (params.status_code_max !== undefined)
          searchParams.set('status_code_max', String(params.status_code_max))
        if (params.date_from) searchParams.set('date_from', params.date_from)
        if (params.date_to) searchParams.set('date_to', params.date_to)
        if (params.organization_id) searchParams.set('organization_id', params.organization_id)
        if (params.user_id) searchParams.set('user_id', params.user_id)
        if (params.user_email) searchParams.set('user_email', params.user_email)
        searchParams.set('limit', String(params.limit || 50))
        if (params.cursor) searchParams.set('cursor', params.cursor)
        return `/admin/request-logs?${searchParams.toString()}`
      },
      providesTags: ['RequestLog'],
    }),

    getRequestLog: builder.query<RequestLog, string>({
      query: (id) => `/admin/request-logs/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'RequestLog', id }],
    }),

    triggerLogCleanup: builder.mutation<CleanupResponse, void>({
      query: () => ({
        url: '/admin/request-logs/cleanup',
        method: 'POST',
      }),
      invalidatesTags: ['RequestLog'],
    }),

    getRequestLoggingConfig: builder.query<RequestLoggingConfig, void>({
      query: () => '/admin/request-logs/config',
      providesTags: ['RequestLogConfig'],
    }),

    updateRequestLoggingConfig: builder.mutation<
      RequestLoggingConfig,
      UpdateRequestLoggingConfigRequest
    >({
      query: (body) => ({
        url: '/admin/request-logs/config',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['RequestLogConfig'],
    }),
  }),
})

export const {
  useGetRequestLogsQuery,
  useGetRequestLogQuery,
  useTriggerLogCleanupMutation,
  useGetRequestLoggingConfigQuery,
  useUpdateRequestLoggingConfigMutation,
} = requestLogsApi
