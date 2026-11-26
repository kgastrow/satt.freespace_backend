import { useState, useEffect } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormMessage,
} from '@/components/ui/form'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from '@/components/ui/input-otp'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  useVerifyEmailOTPMutation,
  useSendVerificationEmailMutation,
} from '@/features/auth/authApi'
import { useLazyGetTwoFactorPolicyQuery } from '@/store/api/twoFactorApi'
import { getErrorMessage } from '@/types/api'
import { useTranslation, Trans } from 'react-i18next'

// Rate limit is 3/minute, so 20 seconds between sends
const RESEND_COOLDOWN_SECONDS = 20

const createVerifySchema = (t: (key: string) => string) =>
  z.object({
    otpCode: z.string().length(6, t('auth:validation.otpLength')),
  })

type VerifyFormData = z.infer<ReturnType<typeof createVerifySchema>>

export function VerifyEmailPage() {
  const { t } = useTranslation(['auth', 'backend'])
  const navigate = useNavigate()
  const location = useLocation()
  const email = (location.state as { email?: string })?.email || ''

  const [verifyEmail, { isLoading: isVerifying }] = useVerifyEmailOTPMutation()
  const [sendVerification, { isLoading: isSending }] =
    useSendVerificationEmailMutation()
  const [getTwoFactorPolicy] = useLazyGetTwoFactorPolicyQuery()
  const [resendCooldown, setResendCooldown] = useState(RESEND_COOLDOWN_SECONDS)

  const form = useForm<VerifyFormData>({
    resolver: zodResolver(createVerifySchema(t)),
    defaultValues: {
      otpCode: '',
    },
  })

  // Countdown timer effect
  useEffect(() => {
    if (resendCooldown <= 0) return

    const timer = setInterval(() => {
      setResendCooldown((prev) => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1000)

    return () => clearInterval(timer)
  }, [resendCooldown])

  // Redirect if no email provided
  useEffect(() => {
    if (!email) {
      navigate('/register')
    }
  }, [email, navigate])

  const onSubmit = async (data: VerifyFormData) => {
    const organizationSlug = import.meta.env.VITE_ORG_SLUG || ''
    try {
      await verifyEmail({
        email,
        otp_code: data.otpCode,
        organization_slug: organizationSlug,
      }).unwrap()

      toast.success(t('auth:verifyEmail.successMessage'), { category: 'auth' })

      // Check if 2FA setup should be offered/required
      try {
        const policy = await getTwoFactorPolicy().unwrap()
        if (policy.two_factor_available && !policy.user_has_2fa) {
          // Redirect to 2FA setup page if available and not already set up
          navigate('/setup-2fa')
          return
        }
      } catch {
        // If policy check fails, just continue to dashboard
      }

      // User is now logged in automatically, navigate to app
      navigate('/')
    } catch (error: unknown) {
      form.setError('otpCode', { message: getErrorMessage(error, t) })
    }
  }

  const handleResend = async () => {
    if (resendCooldown > 0) return

    const organizationSlug = import.meta.env.VITE_ORG_SLUG || ''
    try {
      await sendVerification({ email, organization_slug: organizationSlug }).unwrap()
      toast.success(t('auth:verifyEmail.resendSuccess'), { category: 'auth' })
      setResendCooldown(RESEND_COOLDOWN_SECONDS)
    } catch {
      toast.error(t('auth:verifyEmail.resendError'), { category: 'auth' })
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1 text-center">
          <CardTitle className="text-2xl font-bold">{t('auth:verifyEmail.title')}</CardTitle>
          <CardDescription>
            <Trans
              i18nKey="auth:verifyEmail.subtitleWithEmail"
              values={{ email }}
              components={{ strong: <strong className="text-foreground" /> }}
            />
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <FormField
                control={form.control}
                name="otpCode"
                render={({ field }) => (
                  <FormItem className="flex flex-col items-center">
                    <FormControl>
                      <InputOTP
                        maxLength={6}
                        value={field.value}
                        onChange={field.onChange}
                        className="gap-2"
                      >
                        <InputOTPGroup>
                          <InputOTPSlot index={0} className="h-14 w-12 text-xl" />
                          <InputOTPSlot index={1} className="h-14 w-12 text-xl" />
                          <InputOTPSlot index={2} className="h-14 w-12 text-xl" />
                        </InputOTPGroup>
                        <InputOTPSeparator />
                        <InputOTPGroup>
                          <InputOTPSlot index={3} className="h-14 w-12 text-xl" />
                          <InputOTPSlot index={4} className="h-14 w-12 text-xl" />
                          <InputOTPSlot index={5} className="h-14 w-12 text-xl" />
                        </InputOTPGroup>
                      </InputOTP>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button
                type="submit"
                className="w-full"
                disabled={isVerifying}
              >
                {isVerifying ? t('auth:verifyEmail.submitting') : t('auth:verifyEmail.submit')}
              </Button>

              <div className="text-center text-sm text-muted-foreground">
                {resendCooldown > 0 ? (
                  <p>{t('auth:verifyEmail.resendCountdown', { seconds: resendCooldown })}</p>
                ) : (
                  <p>
                    {t('auth:verifyEmail.noCode')}{' '}
                    <Button
                      type="button"
                      variant="link"
                      onClick={handleResend}
                      disabled={isSending}
                      className="h-auto p-0"
                    >
                      {isSending ? t('auth:verifyEmail.resending') : t('auth:verifyEmail.resend')}
                    </Button>
                  </p>
                )}
              </div>
            </form>
          </Form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            <Link to="/register" className="text-primary hover:underline">
              {t('auth:verifyEmail.backToRegistration')}
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
