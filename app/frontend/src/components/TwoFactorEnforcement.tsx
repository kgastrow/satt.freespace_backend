import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Shield, AlertTriangle } from 'lucide-react'
import { useGetTwoFactorPolicyQuery } from '@/store/api/twoFactorApi'
import { useAppSelector } from '@/store/hooks'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

interface TwoFactorEnforcementProps {
  children: React.ReactNode
}

/**
 * Component that enforces mandatory 2FA setup.
 * When 2FA is mandatory and the user hasn't set it up, this component:
 * - Shows a blocking modal that cannot be dismissed
 * - Redirects to the 2FA setup page when the user clicks setup
 *
 * During the grace period, shows a warning banner instead of blocking.
 */
export function TwoFactorEnforcement({ children }: TwoFactorEnforcementProps) {
  const { t } = useTranslation(['auth'])
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated } = useAppSelector((state) => state.auth)

  const { data: policy, isLoading } = useGetTwoFactorPolicyQuery(undefined, {
    skip: !isAuthenticated,
  })

  // Check if we're within the grace period
  const isWithinGracePeriod = (() => {
    if (!policy?.enforcement_deadline) return true
    const deadline = new Date(policy.enforcement_deadline)
    return new Date() < deadline
  })()

  // Determine if we should block the user
  const shouldBlock = policy?.requires_setup && !isWithinGracePeriod

  // Determine if we should show a warning (within grace period)
  const shouldWarn = policy?.requires_setup && isWithinGracePeriod

  // Calculate days remaining in grace period
  const daysRemaining = (() => {
    if (!policy?.enforcement_deadline) return null
    const deadline = new Date(policy.enforcement_deadline)
    const now = new Date()
    const diff = deadline.getTime() - now.getTime()
    return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)))
  })()

  const handleSetup = () => {
    navigate('/setup-2fa')
  }

  // Don't render anything while loading
  if (isLoading) {
    return <>{children}</>
  }

  // If we're already on the setup page, don't show enforcement
  if (location.pathname === '/setup-2fa') {
    return <>{children}</>
  }

  return (
    <>
      {/* Warning banner during grace period */}
      {shouldWarn && !shouldBlock && (
        <Alert variant="destructive" className="m-4 mb-0">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('auth:twoFactorEnforcement.warningTitle')}</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            <span>
              {t('auth:twoFactorEnforcement.warningDescription', { days: daysRemaining })}
            </span>
            <Button variant="outline" size="sm" onClick={handleSetup} className="ml-4">
              {t('auth:twoFactorEnforcement.setupNow')}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Blocking modal when grace period expired */}
      <Dialog open={shouldBlock} modal>
        <DialogContent
          className="sm:max-w-md"
          onPointerDownOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          showCloseButton={false}
        >
          <DialogHeader className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
              <Shield className="h-6 w-6 text-destructive" />
            </div>
            <DialogTitle>{t('auth:twoFactorEnforcement.blockTitle')}</DialogTitle>
            <DialogDescription>
              {t('auth:twoFactorEnforcement.blockDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="mt-4">
            <Button className="w-full" onClick={handleSetup}>
              {t('auth:twoFactorEnforcement.setupButton')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {children}
    </>
  )
}
