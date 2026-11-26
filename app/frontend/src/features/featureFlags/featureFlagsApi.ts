import { api } from '@/store/api'

export interface FeatureFlagOverrideSummary {
  organization_id: string
  organization_name: string
  enabled: boolean
}

export interface FeatureFlag {
  id: string
  key: string
  name: string
  description: string | null
  default_enabled: boolean
  created_time: string
  updated_time: string
  overrides?: FeatureFlagOverrideSummary[]
}

export interface FeatureFlagListResponse {
  items: FeatureFlag[]
  total: number
  limit: number
  offset: number
}

export interface CreateFeatureFlagRequest {
  key: string
  name: string
  description?: string | null
  default_enabled?: boolean
}

export interface UpdateFeatureFlagRequest {
  key?: string
  name?: string
  description?: string | null
  default_enabled?: boolean
}

export interface CreateFeatureFlagResponse {
  message: string
  message_code: string
  flag: FeatureFlag
}

export interface UpdateFeatureFlagResponse {
  message: string
  message_code: string
  flag: FeatureFlag
}

export interface DeleteFeatureFlagResponse {
  message: string
  message_code: string
  flag_id: string
}

export interface FeatureFlagOverride {
  id: string
  feature_flag_id: string
  organization_id: string
  enabled: boolean
  created_time: string
  updated_time: string
}

export interface FeatureFlagOverrideListResponse {
  items: FeatureFlagOverride[]
  total: number
  limit: number
  offset: number
}

export interface CreateOverrideRequest {
  organization_id: string
  enabled: boolean
}

export interface CreateOverrideResponse {
  message: string
  message_code: string
  override: FeatureFlagOverride
}

export interface DeleteOverrideResponse {
  message: string
  message_code: string
  flag_id: string
  organization_id: string
}

export interface ResolvedFeatureFlagsResponse {
  flags: Record<string, boolean>
}

export const featureFlagsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * Get list of all feature flags (paginated, super admin only)
     */
    getFeatureFlags: builder.query<
      FeatureFlagListResponse,
      { limit?: number; offset?: number }
    >({
      query: ({ limit = 100, offset = 0 }) =>
        `/admin/feature-flags?limit=${limit}&offset=${offset}`,
      providesTags: (result) =>
        result
          ? [
              ...result.items.map((flag) => ({
                type: 'FeatureFlag' as const,
                id: flag.id,
              })),
              { type: 'FeatureFlag', id: 'LIST' },
            ]
          : [{ type: 'FeatureFlag', id: 'LIST' }],
    }),

    /**
     * Get a single feature flag by ID (super admin only)
     */
    getFeatureFlag: builder.query<FeatureFlag, string>({
      query: (id) => `/admin/feature-flags/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'FeatureFlag', id }],
    }),

    /**
     * Create a new feature flag (super admin only)
     */
    createFeatureFlag: builder.mutation<
      CreateFeatureFlagResponse,
      CreateFeatureFlagRequest
    >({
      query: (body) => ({
        url: '/admin/feature-flags',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'FeatureFlag', id: 'LIST' }],
    }),

    /**
     * Update an existing feature flag (super admin only)
     */
    updateFeatureFlag: builder.mutation<
      UpdateFeatureFlagResponse,
      { id: string; data: UpdateFeatureFlagRequest }
    >({
      query: ({ id, data }) => ({
        url: `/admin/feature-flags/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'FeatureFlag', id },
        { type: 'FeatureFlag', id: 'LIST' },
        { type: 'ResolvedFlags', id: 'CURRENT' },
      ],
    }),

    /**
     * Delete a feature flag (super admin only)
     */
    deleteFeatureFlag: builder.mutation<DeleteFeatureFlagResponse, string>({
      query: (id) => ({
        url: `/admin/feature-flags/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: [
        { type: 'FeatureFlag', id: 'LIST' },
        { type: 'ResolvedFlags', id: 'CURRENT' },
      ],
    }),

    /**
     * Get overrides for a specific flag (super admin only)
     */
    getFeatureFlagOverrides: builder.query<
      FeatureFlagOverrideListResponse,
      string
    >({
      query: (flagId) => `/admin/feature-flags/${flagId}/overrides`,
      providesTags: (result, _error, flagId) =>
        result
          ? [
              ...result.items.map((override) => ({
                type: 'FeatureFlagOverride' as const,
                id: override.id,
              })),
              { type: 'FeatureFlagOverride', id: `FLAG_${flagId}` },
            ]
          : [{ type: 'FeatureFlagOverride', id: `FLAG_${flagId}` }],
    }),

    /**
     * Create or update an organization override (super admin only)
     */
    createFeatureFlagOverride: builder.mutation<
      CreateOverrideResponse,
      { flagId: string; data: CreateOverrideRequest }
    >({
      query: ({ flagId, data }) => ({
        url: `/admin/feature-flags/${flagId}/overrides`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_result, _error, { flagId }) => [
        { type: 'FeatureFlagOverride', id: `FLAG_${flagId}` },
        { type: 'ResolvedFlags', id: 'CURRENT' },
      ],
    }),

    /**
     * Delete an organization override (super admin only)
     */
    deleteFeatureFlagOverride: builder.mutation<
      DeleteOverrideResponse,
      { flagId: string; orgId: string }
    >({
      query: ({ flagId, orgId }) => ({
        url: `/admin/feature-flags/${flagId}/overrides/${orgId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, { flagId }) => [
        { type: 'FeatureFlagOverride', id: `FLAG_${flagId}` },
        { type: 'ResolvedFlags', id: 'CURRENT' },
      ],
    }),

    /**
     * Get resolved feature flags for current organization
     * Returns a dictionary of flag keys to boolean values
     */
    getResolvedFeatureFlags: builder.query<ResolvedFeatureFlagsResponse, void>(
      {
        query: () => '/feature-flags',
        providesTags: [{ type: 'ResolvedFlags', id: 'CURRENT' }],
      }
    ),
  }),
})

export const {
  useGetFeatureFlagsQuery,
  useGetFeatureFlagQuery,
  useCreateFeatureFlagMutation,
  useUpdateFeatureFlagMutation,
  useDeleteFeatureFlagMutation,
  useGetFeatureFlagOverridesQuery,
  useCreateFeatureFlagOverrideMutation,
  useDeleteFeatureFlagOverrideMutation,
  useGetResolvedFeatureFlagsQuery,
} = featureFlagsApi
