import { api } from '@/store/api'

// Types for reports
export interface Report {
  id: string
  organization_id: string
  generated_by_user_id: string | null
  report_type: string
  name: string
  description: string | null
  parameters: Record<string, unknown> | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  file_id: string | null
  row_count: number | null
  schedule_id: string | null
  created_time: string
  updated_time: string | null
  download_url: string | null
}

export interface ReportSchedule {
  id: string
  organization_id: string
  created_by_user_id: string | null
  report_type: string
  name: string
  description: string | null
  schedule_expression: string
  is_active: boolean
  parameters: Record<string, unknown> | null
  recipients: string[] | null
  last_run_time: string | null
  next_run_time: string | null
  last_run_status: string | null
  last_run_error_message: string | null
  created_time: string
  updated_time: string | null
}

export interface ReportType {
  code: string
  name: string
  description: string
}

export interface ReportsListResponse {
  items: Report[]
  total: number
  limit: number
  offset: number
}

export interface ReportSchedulesListResponse {
  items: ReportSchedule[]
  total: number
  limit: number
  offset: number
}

export interface ReportTypesListResponse {
  items: ReportType[]
}

export interface CreateReportRequest {
  report_type: string
  name: string
  description?: string
  parameters?: Record<string, unknown>
}

export interface CreateReportScheduleRequest {
  report_type: string
  name: string
  schedule_expression: string
  recipients: string[]
  description?: string
  parameters?: Record<string, unknown>
}

export interface UpdateReportScheduleRequest {
  name?: string
  description?: string
  schedule_expression?: string
  recipients?: string[]
  parameters?: Record<string, unknown>
  is_active?: boolean
}

export interface ReportsQueryParams {
  report_type?: string
  status?: string
  sort?: string
  limit?: number
  offset?: number
}

export interface SchedulesQueryParams {
  report_type?: string
  is_active?: boolean
  sort?: string
  limit?: number
  offset?: number
}

export const reportsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // Report types
    getReportTypes: builder.query<ReportTypesListResponse, void>({
      query: () => '/reports/types',
      providesTags: ['ReportType'],
    }),

    // Reports
    getReports: builder.query<ReportsListResponse, ReportsQueryParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()

        if (params.report_type) searchParams.set('filter[report_type]', params.report_type)
        if (params.status) searchParams.set('filter[status]', params.status)
        if (params.sort) searchParams.set('sort', params.sort)
        searchParams.set('limit', String(params.limit || 50))
        searchParams.set('offset', String(params.offset || 0))

        return `/reports?${searchParams.toString()}`
      },
      providesTags: ['Report'],
    }),

    getReport: builder.query<Report, string>({
      query: (id) => `/reports/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Report', id }],
    }),

    createReport: builder.mutation<{ message: string; report: Report }, CreateReportRequest>({
      query: (body) => ({
        url: '/reports',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['Report'],
    }),

    deleteReport: builder.mutation<{ message: string; report_id: string }, string>({
      query: (id) => ({
        url: `/reports/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['Report'],
    }),

    // Report Schedules
    getReportSchedules: builder.query<ReportSchedulesListResponse, SchedulesQueryParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()

        if (params.report_type) searchParams.set('filter[report_type]', params.report_type)
        if (params.is_active !== undefined) searchParams.set('filter[is_active]', String(params.is_active))
        if (params.sort) searchParams.set('sort', params.sort)
        searchParams.set('limit', String(params.limit || 50))
        searchParams.set('offset', String(params.offset || 0))

        return `/report-schedules?${searchParams.toString()}`
      },
      providesTags: ['ReportSchedule'],
    }),

    getReportSchedule: builder.query<ReportSchedule, string>({
      query: (id) => `/report-schedules/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'ReportSchedule', id }],
    }),

    createReportSchedule: builder.mutation<{ message: string; schedule: ReportSchedule }, CreateReportScheduleRequest>({
      query: (body) => ({
        url: '/report-schedules',
        method: 'POST',
        body,
      }),
      invalidatesTags: ['ReportSchedule'],
    }),

    updateReportSchedule: builder.mutation<{ message: string; schedule: ReportSchedule }, { id: string; data: UpdateReportScheduleRequest }>({
      query: ({ id, data }) => ({
        url: `/report-schedules/${id}`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: ['ReportSchedule'],
    }),

    deleteReportSchedule: builder.mutation<{ message: string; schedule_id: string }, string>({
      query: (id) => ({
        url: `/report-schedules/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: ['ReportSchedule'],
    }),
  }),
})

export const {
  useGetReportTypesQuery,
  useGetReportsQuery,
  useGetReportQuery,
  useCreateReportMutation,
  useDeleteReportMutation,
  useGetReportSchedulesQuery,
  useGetReportScheduleQuery,
  useCreateReportScheduleMutation,
  useUpdateReportScheduleMutation,
  useDeleteReportScheduleMutation,
} = reportsApi
