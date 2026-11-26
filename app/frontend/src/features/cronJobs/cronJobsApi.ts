import { api } from '@/store/api'
import type {
  CronJob,
  CronJobListResponse,
  CronJobListParams,
  CreateCronJobRequest,
  UpdateCronJobRequest,
  CronJobExecutionListResponse,
  CronJobExecutionListParams,
  ToggleCronJobRequest,
  TriggerCronJobResponse,
  DeleteCronJobResponse,
  CronJobConfigResponse,
  UpdateCronJobConfigRequest,
} from '@/types/cron-job'

export const cronJobsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /cron-jobs - List all cron jobs with optional filtering
     */
    getCronJobs: builder.query<CronJobListResponse, CronJobListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.is_active !== undefined) {
          searchParams.append('filter[is_active]', params.is_active.toString())
        }
        if (params?.organization_id) {
          searchParams.append('filter[organization_id]', params.organization_id)
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/cron-jobs${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'CronJob' as const,
                id,
              })),
              { type: 'CronJob', id: 'LIST' },
            ]
          : [{ type: 'CronJob', id: 'LIST' }],
    }),

    /**
     * GET /cron-jobs/{id} - Get a single cron job
     */
    getCronJob: builder.query<CronJob, string>({
      query: (id) => `/cron-jobs/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'CronJob', id }],
    }),

    /**
     * POST /cron-jobs - Create a new cron job
     */
    createCronJob: builder.mutation<CronJob, CreateCronJobRequest>({
      query: (body) => ({
        url: '/cron-jobs',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'CronJob', id: 'LIST' }],
    }),

    /**
     * PUT /cron-jobs/{id} - Update a cron job
     */
    updateCronJob: builder.mutation<
      CronJob,
      { id: string; body: UpdateCronJobRequest }
    >({
      query: ({ id, body }) => ({
        url: `/cron-jobs/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'CronJob', id },
        { type: 'CronJob', id: 'LIST' },
      ],
    }),

    /**
     * DELETE /cron-jobs/{id} - Soft delete a cron job
     */
    deleteCronJob: builder.mutation<DeleteCronJobResponse, string>({
      query: (id) => ({
        url: `/cron-jobs/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'CronJob', id },
        { type: 'CronJob', id: 'LIST' },
      ],
    }),

    /**
     * PATCH /cron-jobs/{id}/toggle - Toggle cron job active status
     */
    toggleCronJob: builder.mutation<
      CronJob,
      { id: string; body: ToggleCronJobRequest }
    >({
      query: ({ id, body }) => ({
        url: `/cron-jobs/${id}/toggle`,
        method: 'PATCH',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'CronJob', id },
        { type: 'CronJob', id: 'LIST' },
      ],
    }),

    /**
     * POST /cron-jobs/{id}/trigger - Manually trigger a cron job execution
     */
    triggerCronJob: builder.mutation<TriggerCronJobResponse, string>({
      query: (id) => ({
        url: `/cron-jobs/${id}/trigger`,
        method: 'POST',
        body: {},
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'CronJob', id },
        { type: 'CronJobExecution', id: 'LIST' },
      ],
    }),

    /**
     * GET /cron-jobs/{id}/executions - Get execution history for a cron job
     */
    getCronJobExecutions: builder.query<
      CronJobExecutionListResponse,
      { id: string; params?: CronJobExecutionListParams }
    >({
      query: ({ id, params }) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/cron-jobs/${id}/executions${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result, _error, { id }) =>
        result
          ? [
              ...result.items.map((execution) => ({
                type: 'CronJobExecution' as const,
                id: execution.id,
              })),
              { type: 'CronJobExecution', id: 'LIST' },
              { type: 'CronJob', id },
            ]
          : [
              { type: 'CronJobExecution', id: 'LIST' },
              { type: 'CronJob', id },
            ],
    }),

    /**
     * GET /cron-jobs/{id}/config - Get configuration for a cron job
     */
    getCronJobConfig: builder.query<CronJobConfigResponse, string>({
      query: (id) => `/cron-jobs/${id}/config`,
      providesTags: (_result, _error, id) => [
        { type: 'CronJob', id },
        { type: 'CronJobConfig', id },
      ],
    }),

    /**
     * PUT /cron-jobs/{id}/config - Update a configuration value for a cron job
     */
    updateCronJobConfig: builder.mutation<
      CronJobConfigResponse,
      { id: string; body: UpdateCronJobConfigRequest }
    >({
      query: ({ id, body }) => ({
        url: `/cron-jobs/${id}/config`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'CronJob', id },
        { type: 'CronJobConfig', id },
      ],
    }),
  }),
})

export const {
  useGetCronJobsQuery,
  useGetCronJobQuery,
  useCreateCronJobMutation,
  useUpdateCronJobMutation,
  useDeleteCronJobMutation,
  useToggleCronJobMutation,
  useTriggerCronJobMutation,
  useGetCronJobExecutionsQuery,
  useGetCronJobConfigQuery,
  useUpdateCronJobConfigMutation,
} = cronJobsApi
