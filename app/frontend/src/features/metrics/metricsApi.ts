import { api } from '@/store/api'
import type { MetricsSummary } from '@/types/generated'

// Re-export for backwards compatibility
export type { MetricsSummary } from '@/types/generated'

export const metricsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getMetricsSummary: builder.query<MetricsSummary, void>({
      query: () => '/metrics/summary',
      // Don't cache metrics - always fetch fresh
      keepUnusedDataFor: 0,
    }),
  }),
})

export const { useGetMetricsSummaryQuery } = metricsApi
