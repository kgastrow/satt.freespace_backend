import { useCallback } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  useStartImpersonationMutation,
  useEndImpersonationMutation,
} from '@/features/impersonation/impersonationApi'
import { setCredentials } from '@/features/auth/authSlice'
import { clearImpersonation } from '@/features/impersonation/impersonationSlice'
import {
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
} from '@/features/auth/authApi'
import { api } from '@/store/api'
import { selectUser } from '@/features/auth/authSelectors'
import {
  selectIsImpersonating,
  selectOriginalUser,
  selectTargetUser,
  selectSessionId,
  selectSessionStartedAt,
} from '@/features/impersonation/impersonationSelectors'

/**
 * Custom hook for impersonation operations
 * Provides startImpersonation, endImpersonation, and impersonation state access
 */
export function useImpersonation() {
  const dispatch = useAppDispatch()

  // Use memoized selectors to prevent unnecessary re-renders
  const isImpersonating = useAppSelector(selectIsImpersonating)
  const originalUser = useAppSelector(selectOriginalUser)
  const targetUser = useAppSelector(selectTargetUser)
  const sessionId = useAppSelector(selectSessionId)
  const sessionStartedAt = useAppSelector(selectSessionStartedAt)

  const currentUser = useAppSelector(selectUser)

  const [startImpersonationMutation, { isLoading: isStarting, error: startError }] =
    useStartImpersonationMutation()
  const [endImpersonationMutation, { isLoading: isEnding, error: endError }] =
    useEndImpersonationMutation()

  // Lazy queries to refetch user info after token swap
  const [refetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [refetchPermissions] = useLazyGetUserPermissionsQuery()

  /**
   * Start impersonating a user
   * Stores original admin tokens and switches to impersonation token
   * Then refetches user info to update auth state with impersonated user
   */
  const startImpersonation = useCallback(
    async (userId: string) => {
      const result = await startImpersonationMutation(userId)
      if ('data' in result && result.data) {
        // Switch to impersonation token
        // Note: impersonation tokens don't have refresh tokens - admin's cookie stays untouched
        dispatch(
          setCredentials({
            token: result.data.impersonation_token,
          })
        )

        // Invalidate cached user data so fresh data is fetched with the new impersonation token
        dispatch(api.util.invalidateTags(['User', 'UserPermissions']))

        // CRITICAL: Refetch current user to update auth state with impersonated user's info
        // This ensures PermissionGate and navigation see the impersonated user, not the admin
        // Run in parallel since these are independent fetches
        await Promise.all([refetchCurrentUser(), refetchPermissions()])
      }
      return result
    },
    [startImpersonationMutation, dispatch, refetchCurrentUser, refetchPermissions]
  )

  /**
   * End current impersonation session
   * Restores original admin tokens and refetches admin user info
   */
  const endImpersonation = useCallback(async () => {
    const result = await endImpersonationMutation()
    if ('data' in result && result.data) {
      // IMPORTANT: Order matters here!
      // 1. First update the token so subsequent API calls use admin's token
      // Admin's refresh cookie was never touched during impersonation
      dispatch(
        setCredentials({
          token: result.data.access_token,
        })
      )

      // 2. Clear impersonation state
      dispatch(clearImpersonation())

      // 3. Invalidate cached user data so fresh data is fetched with new token
      dispatch(api.util.invalidateTags(['User', 'UserPermissions']))

      // 4. Refetch user info to restore admin's info in auth state
      // This uses the NEW admin token because we updated it in step 1
      // Run in parallel since these are independent fetches
      await Promise.all([refetchCurrentUser(), refetchPermissions()])
    }
    return result
  }, [endImpersonationMutation, dispatch, refetchCurrentUser, refetchPermissions])

  return {
    // State
    isImpersonating,
    originalUser,
    // When impersonating, currentUser from auth state IS the target user
    targetUser: isImpersonating ? currentUser : targetUser,
    sessionId,
    sessionStartedAt,

    // Actions
    startImpersonation,
    endImpersonation,

    // Loading states
    isStarting,
    isEnding,

    // Errors
    startError,
    endError,
  }
}
