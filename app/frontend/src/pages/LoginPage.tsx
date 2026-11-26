import { useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GalleryVerticalEnd } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/hooks/useAuth'
import { LoginForm } from '@/components/LoginForm'
import { TwoFactorVerification } from '@/components/auth/TwoFactorVerification'
import { useAppSelector } from '@/store/hooks'
import { toast } from '@/lib/toast'

const ORG_SLUG = import.meta.env.VITE_ORG_SLUG as string

export function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAuthenticated } = useAuth()
  const requires2FA = useAppSelector((state) => state.auth.twoFactor.required)
  const twoFactorSetupRequired = useAppSelector(
    (state) => state.auth.twoFactorSetupRequired
  )
  const enforcementActive = useAppSelector((state) => state.auth.enforcementActive)

  // Redirect to 2FA setup if required due to mandatory policy
  useEffect(() => {
    if (isAuthenticated && twoFactorSetupRequired && enforcementActive) {
      toast.info(t('auth:twoFactor.enforcementRequired'))
      navigate('/settings/two-factor')
    }
  }, [isAuthenticated, twoFactorSetupRequired, enforcementActive, navigate, t])

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated && !twoFactorSetupRequired) {
      navigate('/dashboard')
    }
  }, [isAuthenticated, twoFactorSetupRequired, navigate])

  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-center gap-2 md:justify-start">
          <Link to="/" className="flex items-center gap-2 font-medium">
            <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GalleryVerticalEnd className="size-4" />
            </div>
            {t('common:app.name')}
          </Link>
        </div>
        <div className="flex flex-1 items-center justify-center">
          {requires2FA ? (
            <TwoFactorVerification />
          ) : (
            <LoginForm organizationSlug={ORG_SLUG} />
          )}
        </div>
      </div>
      <div className="relative hidden bg-muted lg:block">
        <img
          src="/placeholder.svg"
          alt={t('auth:login.coverAlt')}
          className="absolute inset-0 h-full w-full object-cover dark:brightness-[0.2] dark:grayscale"
        />
      </div>
    </div>
  )
}
