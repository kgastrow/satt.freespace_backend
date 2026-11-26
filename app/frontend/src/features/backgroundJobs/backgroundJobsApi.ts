import { api } from '@/store/api'

export interface JobTypeInfo {
  code: string
  name: string
  description: string
  category: string
  is_cron: boolean
  enabled: boolean
}

export interface JobTypeStats {
  job_type: string
  name: string
  description: string
  category: string
  is_cron: boolean
  enabled: boolean
  executions_24h: number
  failures_24h: number
  failure_rate: number
  avg_duration_ms: number
  last_execution: string | null
}

export interface JobTypesListResponse {
  items: JobTypeInfo[]
}

export interface BackgroundJobsStatsResponse {
  job_stats: JobTypeStats[]
  total_executions_24h: number
  total_failures_24h: number
}

export interface StuckJob {
  job_id: string
  function: string
  start_time: string
  duration_minutes: number
}

export interface QueueHealthResponse {
  is_healthy: boolean
  issues: string[]
  queue_depth: number
  depth_threshold: number
  stuck_jobs_count: number
  stuck_jobs: StuckJob[]
  workers_online: number
  workers_offline: number
  total_workers: number
  checked_at: string
}

export interface ToggleJobTypeRequest {
  enabled: boolean
}

export interface ToggleJobTypeResponse {
  job_type: string
  enabled: boolean
  message: string
}

export const backgroundJobsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /background-jobs/stats - Get execution stats for all job types
     */
    getBackgroundJobsStats: builder.query<BackgroundJobsStatsResponse, void>({
      query: () => '/background-jobs/stats',
      providesTags: ['BackgroundJobStats'],
    }),

    /**
     * GET /background-jobs/queue-health - Get queue health status
     */
    getQueueHealth: builder.query<QueueHealthResponse, void>({
      query: () => '/background-jobs/queue-health',
      providesTags: ['QueueHealth'],
    }),

    /**
     * GET /background-jobs/types - List all job types with enabled status
     */
    getJobTypes: builder.query<JobTypesListResponse, void>({
      query: () => '/background-jobs/types',
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ code }) => ({
                type: 'BackgroundJobType' as const,
                id: code,
              })),
              { type: 'BackgroundJobType', id: 'LIST' },
            ]
          : [{ type: 'BackgroundJobType', id: 'LIST' }],
    }),

    /**
     * PATCH /background-jobs/types/{type}/toggle - Enable/disable a job type
     */
    toggleJobType: builder.mutation<
      ToggleJobTypeResponse,
      { jobType: string; body: ToggleJobTypeRequest }
    >({
      query: ({ jobType, body }) => ({
        url: `/background-jobs/types/${jobType}/toggle`,
        method: 'PATCH',
        body,
      }),
      invalidatesTags: (_result, _error, { jobType }) => [
        { type: 'BackgroundJobType', id: jobType },
        { type: 'BackgroundJobType', id: 'LIST' },
        'BackgroundJobStats',
      ],
    }),
  }),
})

export const {
  useGetBackgroundJobsStatsQuery,
  useGetQueueHealthQuery,
  useGetJobTypesQuery,
  useToggleJobTypeMutation,
} = backgroundJobsApi
