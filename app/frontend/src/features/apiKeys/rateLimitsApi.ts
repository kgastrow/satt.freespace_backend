import { api } from '@/store/api'
import type { components } from '@/types/api-generated'

type RateLimitResponse = components['schemas']['CreateRateLimitResponse']
type RateLimitListResponse = components['schemas']['RateLimitListResponse']
type RateLimitCreateRequest = components['schemas']['CreateRateLimitRequest']
type RateLimitUpdateRequest = components['schemas']['UpdateRateLimitRequest']

export const rateLimitsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getRateLimits: builder.query<RateLimitListResponse, void>({
      query: () => '/admin/api-key-rate-limits',
      providesTags: (result) =>
        result?.items
          ? [
              ...result.items.map(({ id }: { id: string }) => ({ type: 'RateLimit' as const, id })),
              { type: 'RateLimit', id: 'LIST' },
            ]
          : [{ type: 'RateLimit', id: 'LIST' }],
    }),

    createRateLimit: builder.mutation<RateLimitResponse, RateLimitCreateRequest>({
      query: (body) => ({
        url: '/admin/api-key-rate-limits',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'RateLimit', id: 'LIST' }],
    }),

    updateRateLimit: builder.mutation<RateLimitResponse, { id: string; data: RateLimitUpdateRequest }>({
      query: ({ id, data }) => ({
        url: `/admin/api-key-rate-limits/${id}`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'RateLimit', id },
        { type: 'RateLimit', id: 'LIST' },
      ],
    }),

    deleteRateLimit: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/admin/api-key-rate-limits/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'RateLimit', id },
        { type: 'RateLimit', id: 'LIST' },
      ],
    }),
  }),
})

export const {
  useGetRateLimitsQuery,
  useCreateRateLimitMutation,
  useUpdateRateLimitMutation,
  useDeleteRateLimitMutation,
} = rateLimitsApi
