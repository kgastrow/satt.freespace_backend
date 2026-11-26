import {
  createApi,
  fetchBaseQuery,
  type BaseQueryFn,
  type FetchArgs,
  type FetchBaseQueryError,
} from '@reduxjs/toolkit/query/react'
import type { RootState } from './index'

/**
 * The commit this bundle was built from - the same value that lands in
 * version.json (see getBuildMetadata in vite.config.ts), so the two can never
 * disagree.
 *
 * Sent on every request because updates are staged rather than forced: a tab
 * can go on running an older build for hours, and without this the backend has
 * no way to tell which one it is answering.
 */
const APP_COMMIT = import.meta.env.VITE_BUILD_COMMIT || 'development'

const baseQuery = fetchBaseQuery({
  baseUrl: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
  credentials: 'include',
  prepareHeaders: (headers, { getState }) => {
    const token = (getState() as RootState).auth.token
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    headers.set('X-App-Commit', APP_COMMIT)
    return headers
  },
})

/**
 * Check if error is due to ended impersonation session
 */
function isImpersonationEndedError(error: FetchBaseQueryError): boolean {
  if (error.status !== 401) return false
  const data = error.data as { detail?: string } | undefined
  return data?.detail === 'Impersonation session has ended'
}

/**
 * The single in-flight `/auth/refresh` call, shared across every caller.
 *
 * A cold load fires several authenticated requests at once. When the access
 * token has expired they all 401 together, and without this each one posts its
 * own refresh: N POST /auth/refresh per expiry, a self-inflicted burst against
 * the one endpoint whose failure signs the user out (and the one most likely to
 * be rate limited). The first 401 starts the refresh; the rest await the same
 * promise and then retry.
 */
let refreshInFlight: Promise<Awaited<ReturnType<typeof baseQuery>>> | null = null

function sharedRefresh(
  api: Parameters<typeof baseQuery>[1],
  extraOptions: Parameters<typeof baseQuery>[2]
) {
  if (!refreshInFlight) {
    // Promise.resolve because a base query is typed as MaybePromise - it may
    // answer synchronously - and the latch has to be a real promise for every
    // waiter to await the same one.
    const pending: Promise<Awaited<ReturnType<typeof baseQuery>>> = Promise.resolve(
      baseQuery({ url: '/auth/refresh', method: 'POST' }, api, extraOptions)
    ).finally(() => {
      // Only clear the latch if it is still ours - a later refresh may already
      // have replaced it, and clearing that one would let a second refresh run
      // alongside it.
      if (refreshInFlight === pending) refreshInFlight = null
    })
    refreshInFlight = pending
  }
  return refreshInFlight
}

/**
 * Test seam - the refresh latch is module state and outlives a store, so tests
 * that share the module registry between cases must clear it. Not used by
 * application code.
 */
export function resetRefreshState(): void {
  refreshInFlight = null
}

/** Statuses that mean the refresh cookie itself is dead - the only sign-out. */
function isDefinitiveAuthFailure(error: FetchBaseQueryError | undefined): boolean {
  return error?.status === 401 || error?.status === 403
}

/**
 * How long to wait before retrying the original request when a refresh failed
 * for a reason that says nothing about the session (502, 429, network drop).
 * Tunable: long enough for a rolling restart to hand over or a burst to clear,
 * short enough that the user does not notice a stall.
 */
const REFRESH_RETRY_DELAY_MS = 500

/**
 * Enhanced base query with automatic token refresh on 401 errors
 */
const baseQueryWithReauth: BaseQueryFn<
  string | FetchArgs,
  unknown,
  FetchBaseQueryError
> = async (args, api, extraOptions) => {
  let result = await baseQuery(args, api, extraOptions)

  // Don't attempt reauth for the refresh endpoint itself to prevent infinite loops
  const isRefreshRequest =
    typeof args === 'object' && 'url' in args && args.url === '/auth/refresh'

  // A 401 on a session that never existed is NOT an expired session - it's a
  // signed-out visitor touching an auth-only endpoint (a public route, or a
  // query still mounted just after logout). Attempting a refresh there fails,
  // and the failure branch below dispatches session-expired, which toasts
  // "Your session has expired" and hard-redirects to /login (see
  // authMiddleware). Let the caller see the 401 instead. Bootstrap is
  // unaffected: AuthProvider restores the session with an explicit
  // POST /auth/refresh, which is excluded above, before any other request runs.
  const hadSession = (api.getState() as RootState).auth.token !== null

  // If we get a 401, check if it's due to ended impersonation session
  if (result.error && result.error.status === 401 && !isRefreshRequest && hadSession) {
    // Check for impersonation session ended
    if (isImpersonationEndedError(result.error)) {
      // Clear impersonation state and logout with specific reason
      api.dispatch({ type: 'impersonation/clearImpersonation' })
      api.dispatch({ type: 'auth/logout', payload: { reason: 'impersonation-ended' } })
      return result
    }

    // Try to refresh the token - cookie is sent automatically. Shared across
    // concurrent 401s so a cold load makes one refresh call, not five.
    const refreshResult = await sharedRefresh(api, extraOptions)

    if (refreshResult.data) {
      // Token refreshed successfully - update Redux state and retry
      const data = refreshResult.data as { access_token: string }
      api.dispatch({ type: 'auth/updateToken', payload: data.access_token })
      result = await baseQuery(args, api, extraOptions)
    } else if (isDefinitiveAuthFailure(refreshResult.error)) {
      // The refresh cookie itself is gone, expired or revoked (401), or the
      // account is suspended / the org deactivated (403). This is a real ended
      // session, so sign out promptly.
      // Using action type string to avoid circular dependency with authSlice
      api.dispatch({ type: 'auth/logout', payload: { reason: 'session-expired' } })
    } else {
      // Anything else - a 502/503 while the backend is rolling, a 429 from a
      // shared NAT'd address, a dropped connection - says nothing about
      // whether the session is still valid. Signing the user out here is how a
      // whole office gets logged out by one bad minute. Wait briefly and retry
      // the original request once; if it still fails, the caller sees the error
      // and the session survives. The latch is already cleared, so the next
      // 401 refreshes again and the session recovers on its own once the
      // backend does - or ends properly if the refresh then answers 401.
      await new Promise((resolve) => setTimeout(resolve, REFRESH_RETRY_DELAY_MS))
      result = await baseQuery(args, api, extraOptions)
    }
  }

  return result
}

export const api = createApi({
  reducerPath: 'api',
  baseQuery: baseQueryWithReauth,
  tagTypes: [
    'User',
    'UserPermissions',
    'Organization',
    'OrganizationMember',
    'Organization2FA',
    'Role',
    'UserRole',
    'ApiKey',
    'RateLimit',
    'AuditLog',
    'File',
    'FileSettings',
    'Notification',
    'Template',
    'Category',
    'NotificationSettings',
    'UserPreference',
    'PushSubscription',
    'Permission',
    'PermissionMatrix',
    'SSO',
    'InAppNotification',
    'Announcement',
    'HelpCategory',
    'HelpArticle',
    'HelpFaq',
    'TwoFactorSettings',
    'UserTwoFactor',
    'CronJob',
    'CronJobExecution',
    'CronJobConfig',
    'Media',
    'RequestLog',
    'RequestLogConfig',
    'FeatureFlag',
    'FeatureFlagOverride',
    'ResolvedFlags',
    'Maintenance',
    'MaintenanceHistory',
    'Feedback',
    'UserOnboarding',
    'UserType',
    'OnboardingStep',
    'Session',
    'SystemConfig',
    'EmailSettings',
    'UserIdentity',
    'BackgroundJobStats',
    'BackgroundJobType',
    'QueueHealth',
    'About',
    'Changelog',
    'Invitation',
    'Report',
    'ReportType',
    'ReportSchedule',
    'UserTypePermissionMatrix',
  ],
  endpoints: () => ({}),
})
