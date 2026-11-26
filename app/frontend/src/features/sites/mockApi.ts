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
    // Relative bases (e.g. `/api/v1`) resolve against the SPA's own origin.
    return new URL(base, window.location.origin).origin
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

function isMockStatusBody(
  body: unknown,
): body is { mockTime: string; offsetSeconds: number } {
  return (
    typeof body === 'object' &&
    body !== null &&
    typeof (body as { mockTime?: unknown }).mockTime === 'string'
  )
}

export const mockApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /** 404 (or unreachable) means mock mode is off: resolved as `enabled: false`. */
    getMockStatus: builder.query<MockStatus, void>({
      queryFn: async () => {
        const result = await mockFetch<{ mockTime: string; offsetSeconds: number }>('/mock/status')
        // A 2xx that is not the status JSON (e.g. an SPA index.html fallback) is not mock mode.
        if ('data' in result && isMockStatusBody(result.data)) {
          return { data: { enabled: true, ...result.data } }
        }
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
