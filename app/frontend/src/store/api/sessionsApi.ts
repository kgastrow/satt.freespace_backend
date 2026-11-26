import { api } from '@/store/api'

export interface SessionDeviceInfo {
  device_type: 'mobile' | 'tablet' | 'desktop' | 'unknown'
  browser: string
  os: string
}

export interface SessionLocation {
  city: string | null
  country: string | null
  country_code: string | null
}

export interface Session {
  id: string
  device: SessionDeviceInfo
  location: SessionLocation
  ip_address: string | null
  auth_provider: string | null
  created_time: string
  updated_time: string
  is_current: boolean
}

export interface SessionListResponse {
  items: Session[]
  total: number
  limit: number
  offset: number
}

export interface RevokeSessionResponse {
  message: string
  message_code: string
}

export interface RevokeOtherSessionsResponse {
  message: string
  message_code: string
  revoked_count: number
}

export const sessionsApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /sessions - List all active sessions for current user
     */
    getSessions: builder.query<SessionListResponse, void>({
      query: () => '/sessions',
      providesTags: [{ type: 'Session', id: 'LIST' }],
    }),

    /**
     * DELETE /sessions/{sessionId} - Revoke a specific session
     */
    revokeSession: builder.mutation<RevokeSessionResponse, string>({
      query: (sessionId) => ({
        url: `/sessions/${sessionId}`,
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'Session', id: 'LIST' }],
    }),

    /**
     * DELETE /sessions/others - Revoke all sessions except current
     */
    revokeOtherSessions: builder.mutation<RevokeOtherSessionsResponse, void>({
      query: () => ({
        url: '/sessions/others',
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'Session', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetSessionsQuery,
  useRevokeSessionMutation,
  useRevokeOtherSessionsMutation,
} = sessionsApi
