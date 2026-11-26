import { useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  useLoginMutation,
  useLogoutMutation,
  useLazyGetCurrentUserQuery,
  useLazyGetUserPermissionsQuery,
} from '@/features/auth/authApi'
import { logout as logoutAction, initializeAuth } from '@/features/auth/authSlice'
import {
  selectUser,
  selectToken,
  selectIsAuthenticated,
  selectIsLoading,
  selectTwoFactor,
  selectTwoFactorSetupRequired,
} from '@/features/auth/authSelectors'
import type { LoginRequest } from '@/types/auth'

/**
 * Transformed user interface with camelCase properties
 * Provides a stable interface abstraction over the backend User model
 *
 * BACKWARD COMPATIBILITY: Includes both snake_case and camelCase properties
 * to maintain compatibility with existing code while providing modern naming
 */
export interface AuthUser {
  id: string
  email: string
  // Modern camelCase properties
  firstName: string
  lastName: string
  fullName: string
  avatarUrl?: string | null
  fullAvatarUrl?: string | null
  isAdmin: boolean
  permissions: string[]
  roles: string[]
  organizationId: string
  // Backward-compatible snake_case properties (deprecated but maintained for compatibility)
  /** @deprecated Use firstName instead */
  first_name: string
  /** @deprecated Use lastName instead */
  last_name: string
  /** @deprecated Use organizationId instead */
  organization_id: string
  /** @deprecated Use isAdmin instead */
  is_admin: boolean
  /** @deprecated Use avatarUrl instead */
  avatar_url?: string | null
  /** @deprecated Use fullAvatarUrl instead */
  full_avatar_url?: string | null
}

/**
 * Custom hook for authentication operations
 * Provides login, logout, and auth state access with camelCase transformations
 */
export function useAuth() {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()

  // Use memoized selectors to prevent unnecessary re-renders
  const rawUser = useAppSelector(selectUser)
  const token = useAppSelector(selectToken)
  const isAuthenticated = useAppSelector(selectIsAuthenticated)
  const isLoading = useAppSelector(selectIsLoading)
  const twoFactor = useAppSelector(selectTwoFactor)
  const twoFactorSetupRequired = useAppSelector(selectTwoFactorSetupRequired)

  const [loginMutation, { isLoading: isLoggingIn, error: loginError }] =
    useLoginMutation()
  const [logoutMutation, { isLoading: isLoggingOut }] = useLogoutMutation()
  const [fetchCurrentUser] = useLazyGetCurrentUserQuery()
  const [fetchUserPermissions] = useLazyGetUserPermissionsQuery()

  /**
   * Transform raw user data to camelCase interface
   * Provides computed properties and stable interface
   * Includes both snake_case and camelCase properties for backward compatibility
   */
  const user: AuthUser | null = useMemo(() => {
    if (!rawUser) return null
    return {
      id: rawUser.id,
      email: rawUser.email,
      // Modern camelCase properties
      firstName: rawUser.first_name,
      lastName: rawUser.last_name,
      fullName: `${rawUser.first_name} ${rawUser.last_name}`.trim(),
      avatarUrl: rawUser.avatar_url,
      fullAvatarUrl: rawUser.full_avatar_url,
      isAdmin: rawUser.is_admin ?? false,
      permissions: rawUser.permissions ?? [],
      roles: rawUser.roles ?? [],
      organizationId: rawUser.organization_id,
      // Backward-compatible snake_case properties
      first_name: rawUser.first_name,
      last_name: rawUser.last_name,
      organization_id: rawUser.organization_id,
      is_admin: rawUser.is_admin ?? false,
      avatar_url: rawUser.avatar_url,
      full_avatar_url: rawUser.full_avatar_url,
    }
  }, [rawUser])

  /**
   * Login with credentials
   * On success, fetches current user and permissions, then redirects to home
   */
  const login = useCallback(
    async (credentials: LoginRequest) => {
      const result = await loginMutation(credentials)
      if ('data' in result) {
        // Fetch user data after successful login
        await fetchCurrentUser()
        // Fetch permissions before navigating to ensure permission-gated UI renders correctly
        try {
          await fetchUserPermissions()
        } catch {
          // Permissions fetch can fail silently - user will have empty permissions
        }
        navigate('/')
      }
      return result
    },
    [loginMutation, fetchCurrentUser, fetchUserPermissions, navigate]
  )

  /**
   * Logout the current user
   * Clears auth state and redirects to login
   * Cookie is cleared by backend on POST /auth/logout
   */
  const logout = useCallback(async () => {
    await logoutMutation()
    dispatch(logoutAction({ reason: 'manual' }))
    navigate('/login')
  }, [logoutMutation, dispatch, navigate])

  /**
   * Initialize auth state on app load
   * Validates existing token by fetching current user
   */
  const initAuth = useCallback(async () => {
    if (token) {
      try {
        await fetchCurrentUser().unwrap()
      } catch {
        // Token is invalid, clear auth state
        dispatch(logoutAction())
      }
    } else {
      dispatch(initializeAuth())
    }
  }, [token, fetchCurrentUser, dispatch])

  return {
    // State - user with camelCase properties
    user,
    token,
    isAuthenticated,
    isLoading,

    // 2FA state
    requiresTwoFactor: twoFactor?.required ?? false,
    requiresTwoFactorSetup: twoFactorSetupRequired ?? false,

    // Actions
    login,
    logout,
    initAuth,

    // Loading states
    isLoggingIn,
    isLoggingOut,

    // Errors
    loginError,
  }
}
