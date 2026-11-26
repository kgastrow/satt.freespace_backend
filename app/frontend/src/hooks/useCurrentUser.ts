import { useAuth, type AuthUser } from './useAuth'

/**
 * Simple hook for accessing current user data
 * Returns null if not authenticated
 *
 * @example
 * const user = useCurrentUser()
 * if (user) {
 *   console.log(user.fullName, user.email)
 * }
 */
export function useCurrentUser(): AuthUser | null {
  const { user } = useAuth()
  return user
}

/**
 * Hook for checking if user is authenticated
 * Returns both authentication status and loading state
 *
 * @example
 * const { isAuthenticated, isLoading } = useIsAuthenticated()
 * if (isLoading) return <Spinner />
 * if (!isAuthenticated) return <LoginPrompt />
 */
export function useIsAuthenticated() {
  const { isAuthenticated, isLoading } = useAuth()
  return { isAuthenticated, isLoading }
}
