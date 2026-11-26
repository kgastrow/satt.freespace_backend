import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { SSOButtonGroup } from '@/components/sso'
import { useCheckEmailMutation } from '@/features/auth/authApi'
import { useGetEnabledSSOProvidersQuery } from '@/features/auth/ssoApi'
import { useAuth } from '@/hooks/useAuth'
import { getErrorMessage } from '@/types/api'
import { toast } from '@/lib/toast'

// Step 1: Email only
const createEmailSchema = (t: (key: string) => string) =>
  z.object({
    email: z.string().email(t('auth:validation.emailInvalid')),
  })

// Step 2: Password (only if password auth is available)
const createPasswordSchema = (t: (key: string) => string) =>
  z.object({
    password: z.string().min(1, t('auth:validation.passwordRequired')),
  })

type EmailFormData = z.infer<ReturnType<typeof createEmailSchema>>
type PasswordFormData = z.infer<ReturnType<typeof createPasswordSchema>>

interface LoginFormProps extends React.ComponentProps<'div'> {
  organizationSlug: string
}

type LoginStep = 'email' | 'auth'

export function LoginForm({
  className,
  organizationSlug,
  ...props
}: LoginFormProps) {
  const { t } = useTranslation(['auth', 'backend'])
  const { login, isLoggingIn } = useAuth()
  const [checkEmail, { isLoading: isCheckingEmail }] = useCheckEmailMutation()
  const { data: enabledProviders } = useGetEnabledSSOProvidersQuery({ orgSlug: organizationSlug })

  const [step, setStep] = useState<LoginStep>('email')
  const [email, setEmail] = useState('')
  const [authMethods, setAuthMethods] = useState<string[]>([])
  const [accountExists, setAccountExists] = useState(true)

  // SSO enabled for the org (shown on step 1)
  const orgHasSSOEnabled = enabledProviders?.providers && enabledProviders.providers.length > 0

  // Auth methods for specific user (shown on step 2)
  const hasPasswordAuth = authMethods.includes('password')
  const ssoProviders = authMethods.filter((m) => m !== 'password')
  const hasSSOAuth = ssoProviders.length > 0

  // Email form (Step 1)
  const emailForm = useForm<EmailFormData>({
    resolver: zodResolver(createEmailSchema(t)),
    defaultValues: { email: '' },
  })

  // Password form (Step 2)
  const passwordForm = useForm<PasswordFormData>({
    resolver: zodResolver(createPasswordSchema(t)),
    defaultValues: { password: '' },
  })

  const handleEmailSubmit = async (data: EmailFormData) => {
    try {
      const result = await checkEmail({
        email: data.email,
        organization_slug: organizationSlug,
      }).unwrap()

      setEmail(data.email)
      setAccountExists(result.exists)
      setAuthMethods(result.auth_methods)
      setStep('auth')
    } catch (err) {
      toast.error(getErrorMessage(err, t), { category: 'auth' })
    }
  }

  const handlePasswordSubmit = async (data: PasswordFormData) => {
    const result = await login({
      email,
      password: data.password,
      organization_slug: organizationSlug,
    })

    if ('error' in result) {
      toast.error(getErrorMessage(result.error, t), { category: 'auth' })
    }
  }

  const handleBack = () => {
    setStep('email')
    setAuthMethods([])
    passwordForm.reset()
  }

  // Step 1: Email Entry
  if (step === 'email') {
    return (
      <div className={cn('w-full max-w-xs', className)} {...props}>
        <form
          onSubmit={emailForm.handleSubmit(handleEmailSubmit)}
          className={cn('flex flex-col gap-6')}
        >
          <div className="flex flex-col items-center gap-2 text-center">
            <h1 className="text-2xl font-bold">{t('auth:login.title')}</h1>
            <p className="text-balance text-sm text-muted-foreground">
              {t('auth:login.enterEmail')}
            </p>
          </div>
          <div className="grid gap-6">
            <div className="grid gap-2">
              <Label htmlFor="email">{t('auth:login.email')}</Label>
              <Input
                id="email"
                type="email"
                placeholder={t('auth:login.emailPlaceholder')}
                autoComplete="email"
                autoFocus
                disabled={isCheckingEmail}
                {...emailForm.register('email')}
              />
              {emailForm.formState.errors.email && (
                <p className="text-sm text-destructive">
                  {emailForm.formState.errors.email.message}
                </p>
              )}
            </div>
            <Button
              type="submit"
              className="w-full"
              disabled={isCheckingEmail}
              aria-busy={isCheckingEmail}
            >
              {isCheckingEmail ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('auth:login.checking')}
                </>
              ) : (
                t('auth:login.continue')
              )}
            </Button>
            {orgHasSSOEnabled && (
              <>
                <div className="relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t after:border-border">
                  <span className="relative z-10 bg-background px-2 text-muted-foreground">
                    {t('auth:login.orContinueWith')}
                  </span>
                </div>
                <SSOButtonGroup organizationSlug={organizationSlug} />
              </>
            )}
          </div>
          <div className="text-center text-sm">
            {t('auth:login.noAccount')}{' '}
            <Link to="/register" className="underline underline-offset-4">
              {t('auth:login.signUp')}
            </Link>
          </div>
        </form>
      </div>
    )
  }

  // Step 2: Auth Methods (Password and/or SSO)
  return (
    <div className={cn('w-full max-w-xs', className)} {...props}>
      <div className="flex flex-col gap-6">
        <div className="flex flex-col items-center gap-2 text-center">
          <h1 className="text-2xl font-bold">{t('auth:login.title')}</h1>
          <p className="text-sm text-muted-foreground">{email}</p>
          <button
            type="button"
            onClick={handleBack}
            className="flex items-center gap-1 text-sm text-primary hover:underline"
          >
            <ArrowLeft className="h-3 w-3" />
            {t('auth:login.changeEmail')}
          </button>
        </div>

        {!accountExists ? (
          // Account doesn't exist
          <div className="grid gap-4">
            <p className="text-center text-sm text-muted-foreground">
              {t('auth:login.noAccountFound')}
            </p>
            <Button asChild className="w-full">
              <Link to="/register">{t('auth:login.createAccount')}</Link>
            </Button>
          </div>
        ) : (
          // Account exists - show available auth methods
          <div className="grid gap-6">
            {hasPasswordAuth && (
              <form onSubmit={passwordForm.handleSubmit(handlePasswordSubmit)}>
                <div className="grid gap-4">
                  <div className="grid gap-2">
                    <div className="flex items-center">
                      <Label htmlFor="password">{t('auth:login.password')}</Label>
                      <Link
                        to="/forgot-password"
                        tabIndex={-1}
                        className="ml-auto text-sm underline-offset-4 hover:underline"
                      >
                        {t('auth:login.forgotPassword')}
                      </Link>
                    </div>
                    <Input
                      id="password"
                      type="password"
                      autoComplete="current-password"
                      autoFocus
                      disabled={isLoggingIn}
                      {...passwordForm.register('password')}
                    />
                    {passwordForm.formState.errors.password && (
                      <p className="text-sm text-destructive">
                        {passwordForm.formState.errors.password.message}
                      </p>
                    )}
                  </div>
                  <Button
                    type="submit"
                    className="w-full"
                    disabled={isLoggingIn}
                    aria-busy={isLoggingIn}
                  >
                    {isLoggingIn ? t('auth:login.submitting') : t('auth:login.submit')}
                  </Button>
                </div>
              </form>
            )}

            {hasPasswordAuth && hasSSOAuth && (
              <div className="relative text-center text-sm after:absolute after:inset-0 after:top-1/2 after:z-0 after:flex after:items-center after:border-t after:border-border">
                <span className="relative z-10 bg-background px-2 text-muted-foreground">
                  {t('auth:login.orContinueWith')}
                </span>
              </div>
            )}

            {hasSSOAuth && (
              <SSOButtonGroup organizationSlug={organizationSlug} />
            )}

            {!hasPasswordAuth && hasSSOAuth && (
              <p className="text-center text-sm text-muted-foreground">
                {t('auth:login.ssoOnlyAccount')}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
