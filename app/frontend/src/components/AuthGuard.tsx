import { Navigate, useLocation } from 'react-router-dom'
import { useAppSelector } from '@/store/hooks'

interface AuthGuardProps {
  children: React.ReactNode
  /**
   * If true, requires user to be authenticated
   * If false, requires user to be unauthenticated (for login/register pages)
   */
  requireAuth?: boolean
  /**
   * Redirect path when auth requirement is not met
   */
  redirectTo?: string
}

/**
 * Route guard component that protects routes based on authentication status
 *
 * @example
 * // Protect a route - redirect to login if not authenticated
 * <AuthGuard requireAuth>
 *   <DashboardPage />
 * </AuthGuard>
 *
 * @example
 * // Guest-only route - redirect to home if authenticated
 * <AuthGuard requireAuth={false} redirectTo="/">
 *   <LoginPage />
 * </AuthGuard>
 */
export function AuthGuard({
  children,
  requireAuth = true,
  redirectTo,
}: AuthGuardProps) {
  const location = useLocation()
  const { isAuthenticated, isLoading } = useAppSelector((state) => state.auth)

  // Show nothing while loading auth state
  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  // Require authentication
  if (requireAuth && !isAuthenticated) {
    // Save the attempted URL for redirecting after login
    return <Navigate to={redirectTo ?? '/login'} state={{ from: location }} replace />
  }

  // Require no authentication (guest-only pages like login)
  if (!requireAuth && isAuthenticated) {
    return <Navigate to={redirectTo ?? '/'} replace />
  }

  return <>{children}</>
}

/**
 * Higher-order component version of AuthGuard
 */
export function withAuthGuard<P extends object>(
  Component: React.ComponentType<P>,
  options?: Omit<AuthGuardProps, 'children'>
) {
  return function WrappedComponent(props: P) {
    return (
      <AuthGuard {...options}>
        <Component {...props} />
      </AuthGuard>
    )
  }
}
