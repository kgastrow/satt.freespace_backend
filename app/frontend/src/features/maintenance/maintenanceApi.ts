import { api } from '@/store/api'

export interface MaintenanceStatusResponse {
  enabled: boolean
  message: string | null
  scheduled_start: string | null
  scheduled_end: string | null
  allow_super_admin: boolean
}

export interface MaintenanceConfigResponse {
  enabled: boolean
  message: string | null
  scheduled_start: string | null
  scheduled_end: string | null
  allow_super_admin: boolean
  updated_time: string | null
  updated_by_user_id: string | null
}

export interface UpdateMaintenanceRequest {
  enabled: boolean
  message?: string | null
  scheduled_start?: string | null
  scheduled_end?: string | null
  allow_super_admin?: boolean
}

export interface UpdateMaintenanceResponse {
  message: string
  message_code: string
  config: MaintenanceConfigResponse
}

export interface UserSummary {
  id: string
  first_name: string | null
  last_name: string | null
  email: string
}

export interface MaintenanceHistoryItem {
  id: string
  status: 'scheduled' | 'active' | 'completed' | 'cancelled'
  scheduled_start: string | null
  scheduled_end: string | null
  actual_start: string | null
  actual_end: string | null
  message: string | null
  started_by: UserSummary | null
  ended_by: UserSummary | null
  created_time: string
}

export interface MaintenanceHistoryResponse {
  items: MaintenanceHistoryItem[]
  total: number
  limit: number
  offset: number
}

export interface MaintenanceHistoryParams {
  limit?: number
  offset?: number
  status?: string
}

export const maintenanceApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getMaintenanceStatus: builder.query<MaintenanceStatusResponse, void>({
      query: () => '/maintenance/status',
      providesTags: ['Maintenance'],
    }),

    getMaintenanceConfig: builder.query<MaintenanceConfigResponse, void>({
      query: () => '/admin/maintenance',
      providesTags: ['Maintenance'],
    }),

    updateMaintenance: builder.mutation<UpdateMaintenanceResponse, UpdateMaintenanceRequest>({
      query: (body) => ({
        url: '/admin/maintenance',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['Maintenance', 'MaintenanceHistory'],
    }),

    getMaintenanceHistory: builder.query<MaintenanceHistoryResponse, MaintenanceHistoryParams | void>({
      query: (params) => ({
        url: '/admin/maintenance/history',
        params: params || { limit: 10, offset: 0 },
      }),
      providesTags: ['MaintenanceHistory'],
    }),
  }),
})

export const {
  useGetMaintenanceStatusQuery,
  useGetMaintenanceConfigQuery,
  useUpdateMaintenanceMutation,
  useGetMaintenanceHistoryQuery,
} = maintenanceApi
