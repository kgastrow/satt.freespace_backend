import { api } from '@/store/api'
import type {
  MockClockResponse,
  MockOccupancyRequest,
  MockOccupancyResponse,
  MockStatus,
} from '@/types/siteLive'

/**
 * Mock mode (BF-84) endpoints are mounted at the backend ROOT (/mock/...), not
 * under /api/v1, and are unauthenticated. The origin is derived from the
 * configured API base URL.
 */
export function mockOrigin(): string {
  const base = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1'
  try {
    return new URL(base).origin
  } catch {
    return ''
  }
}

type QueryResult<T> =
  | { data: T }
  | { error: { status: number; data: unknown } }

async function mockFetch<T>(path: string, init?: RequestInit): Promise<QueryResult<T>> {
  try {
    const response = await fetch(`${mockOrigin()}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json' },
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) return { error: { status: response.status, data: body } }
    return { data: body as T }
  } catch {
    return { error: { status: 0, data: null } }
  }
}

export const mockApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /** 404 (or unreachable) means mock mode is off: resolved as `enabled: false`. */
    getMockStatus: builder.query<MockStatus, void>({
      queryFn: async () => {
        const result = await mockFetch<{ mockTime: string; offsetSeconds: number }>('/mock/status')
        if ('data' in result) return { data: { enabled: true, ...result.data } }
        return { data: { enabled: false } }
      },
      providesTags: [{ type: 'MockStatus', id: 'STATUS' }],
      keepUnusedDataFor: 600,
    }),

    postMockOccupancy: builder.mutation<
      MockOccupancyResponse,
      { slug: string; body: MockOccupancyRequest }
    >({
      queryFn: ({ slug, body }) =>
        mockFetch<MockOccupancyResponse>(`/mock/sites/${encodeURIComponent(slug)}/occupancy`, {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      invalidatesTags: [{ type: 'SiteLive' }, { type: 'SiteEvent' }, { type: 'SiteHistory' }],
    }),

    postMockClock: builder.mutation<MockClockResponse, { seconds: number } | { reset: true }>({
      queryFn: (body) =>
        mockFetch<MockClockResponse>('/mock/clock', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      invalidatesTags: [
        { type: 'MockStatus', id: 'STATUS' },
        { type: 'SiteLive' },
        { type: 'SiteEvent' },
      ],
    }),
  }),
})

export const {
  useGetMockStatusQuery,
  usePostMockOccupancyMutation,
  usePostMockClockMutation,
} = mockApi
