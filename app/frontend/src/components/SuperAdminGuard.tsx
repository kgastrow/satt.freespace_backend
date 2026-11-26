import { Navigate, useLocation } from 'react-router-dom'
import { useAppSelector } from '@/store/hooks'
import { useImpersonation } from '@/hooks/useImpersonation'

interface SuperAdminGuardProps {
  children: React.ReactNode
  redirectTo?: string
}

/**
 * Route guard that requires user to have super admin privileges
 * Checks for is_admin flag (super admin status from backend)
 * NOTE: Super admin access is blocked during impersonation - admin should
 * experience the app as the impersonated user
 */
export function SuperAdminGuard({
  children,
  redirectTo = '/dashboard',
}: SuperAdminGuardProps) {
  const location = useLocation()
  const { user, isAuthenticated, isLoading } = useAppSelector((state) => state.auth)
  const { isImpersonating } = useImpersonation()

  if (isLoading) {
    return (
      <div className="flex min-h-[400px] items-center justify-center">
        <div className="animate-pulse text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Super admins have is_admin=true on the backend
  // BUT during impersonation, super admin access is blocked
  const isSuperAdmin = user?.is_admin === true && !isImpersonating

  if (!isSuperAdmin) {
    return <Navigate to={redirectTo} replace />
  }

  return <>{children}</>
}
