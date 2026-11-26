import { api } from '@/store/api'
import type {
  ImpersonationResponse,
  EndImpersonationResponse,
  ImpersonationSessionStatusResponse,
  ImpersonationHistoryItem,
  MyImpersonationHistoryResponse,
  MyImpersonationHistoryParams,
} from '@/types/impersonation'

export const impersonationApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * Start impersonating a user
     * POST /admin/impersonate/{user_id}
     * Invalidates User and UserPermissions to force fresh data fetch for impersonated user
     */
    startImpersonation: builder.mutation<ImpersonationResponse, string>({
      query: (userId) => ({
        url: `/admin/impersonate/${userId}`,
        method: 'POST',
      }),
      invalidatesTags: ['User', 'UserPermissions'],
    }),

    /**
     * End current impersonation session
     * POST /admin/impersonate/end
     * NOTE: Does NOT invalidate tags here - the useImpersonation hook handles
     * cache invalidation AFTER updating the token to avoid race conditions
     */
    endImpersonation: builder.mutation<EndImpersonationResponse, void>({
      query: () => ({
        url: '/admin/impersonate/end',
        method: 'POST',
      }),
      // Don't invalidate here - token must be updated first, then we manually refetch
    }),

    /**
     * Resume impersonation after page refresh
     * POST /admin/impersonate/resume
     * Called by AuthProvider when an active impersonation session is detected
     */
    resumeImpersonation: builder.mutation<ImpersonationResponse, void>({
      query: () => ({
        url: '/admin/impersonate/resume',
        method: 'POST',
      }),
      invalidatesTags: ['User', 'UserPermissions'],
    }),

    /**
     * Get current impersonation session status
     * GET /admin/impersonate/session
     *
     * Returns { active: false } when not impersonating,
     * or { active: true, session: {...} } when impersonating.
     */
    getCurrentSession: builder.query<ImpersonationSessionStatusResponse, void>({
      query: () => '/admin/impersonate/session',
    }),

    /**
     * Get impersonation session history (admin view)
     * GET /admin/impersonate/history
     */
    getImpersonationHistory: builder.query<ImpersonationHistoryItem[], void>({
      query: () => '/admin/impersonate/history',
    }),

    /**
     * Get the current user's impersonation history (when they were impersonated)
     * GET /impersonate/my-history
     *
     * Returns paginated list of impersonation sessions where the current user
     * was the target (i.e., when they were impersonated by a super admin).
     * Only completed sessions are returned (where impersonation has ended).
     */
    getMyImpersonationHistory: builder.query<MyImpersonationHistoryResponse, MyImpersonationHistoryParams | void>({
      query: (params) => {
        const queryParams = new URLSearchParams()
        if (params?.limit) queryParams.set('limit', params.limit.toString())
        if (params?.offset) queryParams.set('offset', params.offset.toString())
        const queryString = queryParams.toString()
        return `/impersonate/my-history${queryString ? `?${queryString}` : ''}`
      },
    }),
  }),
})

export const {
  useStartImpersonationMutation,
  useEndImpersonationMutation,
  useResumeImpersonationMutation,
  useGetCurrentSessionQuery,
  useLazyGetCurrentSessionQuery,
  useGetImpersonationHistoryQuery,
  useGetMyImpersonationHistoryQuery,
} = impersonationApi
