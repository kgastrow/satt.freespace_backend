import { useEffect } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
  useRefreshTokenMutation,
} from '@/features/auth/authApi'
import { updateToken, initializeAuth, setLoading, setCredentials } from '@/features/auth/authSlice'
import {
  useLazyGetCurrentSessionQuery,
  useResumeImpersonationMutation,
} from '@/features/impersonation/impersonationApi'
import { useGetResolvedFeatureFlagsQuery } from '@/features/featureFlags/featureFlagsApi'
import { useWebSocket } from '@/hooks/useWebSocket'

import { useAnnouncementWebSocket } from '@/hooks/useAnnouncementWebSocket'
import { useMaintenanceWebSocket } from '@/hooks/useMaintenanceWebSocket'
import { useNotificationProcessor } from '@/hooks/useNotificationProcessor'
import { useDataExportWebSocket } from '@/hooks/useDataExportWebSocket'


interface AuthProviderProps {
  children: React.ReactNode
}

/**
 * AuthProvider initializes authentication state on app load.
 *
 * It checks for an existing token and validates it by fetching the current user.
 * If the token is invalid or expired, it clears the auth state.
 *
 * This component should wrap the entire app (inside Redux Provider).
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const dispatch = useAppDispatch()
  const { token, isLoading } = useAppSelector((state) => state.auth)
  const [fetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [fetchUserPermissions] = useLazyGetUserPermissionsQuery()
  const [fetchCurrentSession] = useLazyGetCurrentSessionQuery()
  const [refreshToken] = useRefreshTokenMutation()
  const [resumeImpersonation] = useResumeImpersonationMutation()

  // Initialize WebSocket connection for real-time notifications
  // The hook handles auto-connect on auth and cleanup on logout
  useWebSocket()

  // Fetch feature flags on app initialization and store in Redux
  // The extraReducers in featureFlagsSlice automatically store the results
  // Only fetch when authenticated to avoid 401 errors
  useGetResolvedFeatureFlagsQuery(undefined, { skip: !token })

  // Listen for announcement events via WebSocket and update Redux store
  useAnnouncementWebSocket()

  // Listen for maintenance mode changes via WebSocket
  // Immediately updates maintenance state to show maintenance page
  useMaintenanceWebSocket()

  // Process WebSocket notification messages and display toasts
  // Called once here to avoid duplicate processing from multiple UI components
  useNotificationProcessor()

  // Listen for data export status updates via WebSocket
  // Invalidates cache and shows toast when exports complete or fail
  useDataExportWebSocket()

  useEffect(() => {
    async function bootstrap() {
      try {
        // Attempt silent refresh - browser sends httpOnly cookie automatically
        const result = await refreshToken().unwrap()
        dispatch(updateToken(result.access_token))

        // Validate user - must complete before isLoading becomes false
        await fetchCurrentUser().unwrap()

        // Fetch user permissions
        try {
          await fetchUserPermissions().unwrap()
        } catch {
          // Permissions fetch can fail silently - user will have empty permissions
        }

        // Check for active impersonation session (resume flow)
        // On page refresh, /auth/refresh restores the admin session (cookie is admin's).
        // If there's an active impersonation session, resume it.
        try {
          const sessionResult = await fetchCurrentSession().unwrap()
          if (sessionResult.active) {
            const resumed = await resumeImpersonation().unwrap()
            dispatch(setCredentials({ token: resumed.impersonation_token }))
            // Re-fetch user data for the impersonated user
            await fetchCurrentUser().unwrap()
            try {
              await fetchUserPermissions().unwrap()
            } catch {
              // Non-critical
            }
          }
        } catch {
          // No active impersonation - normal flow
        }

        // All auth data loaded
        dispatch(setLoading(false))
      } catch {
        // No valid cookie - user is not logged in
        dispatch(initializeAuth())
      }
    }

    // Only run on initial load
    if (isLoading) {
      bootstrap()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return <>{children}</>
}
