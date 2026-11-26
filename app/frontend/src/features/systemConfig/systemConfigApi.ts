import { api } from '@/store/api'

export interface SystemConfig {
  id: string
  key: string
  value: unknown
  description: string | null
  is_sensitive: boolean
  created_time: string | null
  updated_time: string | null
  updated_by_user_id: string | null
  updated_by_email: string | null
}

export interface SystemConfigListResponse {
  items: SystemConfig[]
  total: number
  limit: number
  offset: number
}

export interface SystemConfigListParams {
  limit?: number
  offset?: number
}

export interface CreateSystemConfigRequest {
  key: string
  value: unknown
  description?: string | null
}

export interface UpdateSystemConfigRequest {
  value: unknown
  description?: string | null
}

export interface DeleteSystemConfigResponse {
  message: string
  message_code: string
}

export const systemConfigApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /admin/system-config - List all system configs
     */
    getSystemConfigs: builder.query<SystemConfigListResponse, SystemConfigListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/admin/system-config${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map((config) => ({
                type: 'SystemConfig' as const,
                id: config.key,
              })),
              { type: 'SystemConfig', id: 'LIST' },
            ]
          : [{ type: 'SystemConfig', id: 'LIST' }],
    }),

    /**
     * GET /admin/system-config/{key} - Get a single system config
     */
    getSystemConfig: builder.query<SystemConfig, string>({
      query: (key) => `/admin/system-config/${encodeURIComponent(key)}`,
      providesTags: (_result, _error, key) => [{ type: 'SystemConfig', id: key }],
    }),

    /**
     * POST /admin/system-config - Create a new system config
     */
    createSystemConfig: builder.mutation<SystemConfig, CreateSystemConfigRequest>({
      query: (body) => ({
        url: '/admin/system-config',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'SystemConfig', id: 'LIST' }],
    }),

    /**
     * PUT /admin/system-config/{key} - Update a system config
     */
    updateSystemConfig: builder.mutation<
      SystemConfig,
      { key: string; body: UpdateSystemConfigRequest }
    >({
      query: ({ key, body }) => ({
        url: `/admin/system-config/${encodeURIComponent(key)}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { key }) => [
        { type: 'SystemConfig', id: key },
        { type: 'SystemConfig', id: 'LIST' },
      ],
    }),

    /**
     * DELETE /admin/system-config/{key} - Delete a system config
     */
    deleteSystemConfig: builder.mutation<DeleteSystemConfigResponse, string>({
      query: (key) => ({
        url: `/admin/system-config/${encodeURIComponent(key)}`,
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'SystemConfig', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetSystemConfigsQuery,
  useGetSystemConfigQuery,
  useCreateSystemConfigMutation,
  useUpdateSystemConfigMutation,
  useDeleteSystemConfigMutation,
} = systemConfigApi
