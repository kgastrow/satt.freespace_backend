import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from '@/components/ui/input-otp'
import { useSendPhoneOtpMutation, useVerifyPhoneOtpMutation } from '@/store/api/onboardingApi'

interface PhoneVerificationStepProps {
  onComplete: () => void
  onBack?: () => void
}

const createPhoneSchema = (t: (key: string) => string) =>
  z.object({
    phone: z.string().min(1, t('phoneVerification.validation.phoneRequired')),
  })

const createOtpSchema = (t: (key: string) => string) =>
  z.object({
    otp: z.string().length(6, t('phoneVerification.validation.otpLength')),
  })

// Separate component for OTP verification to isolate form lifecycle
function OtpVerificationForm({
  phone,
  onComplete,
  onBack,
  onResend,
  isSending,
}: {
  phone: string
  onComplete: () => void
  onBack: () => void
  onResend: () => Promise<void>
  isSending: boolean
}) {
  const { t } = useTranslation('onboarding')
  const [countdown, setCountdown] = useState(300) // 5 minutes
  const [verifyOtp, { isLoading: isVerifying }] = useVerifyPhoneOtpMutation()

  const form = useForm({
    resolver: zodResolver(createOtpSchema(t)),
    defaultValues: { otp: '' },
  })

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  const handleVerify = async (data: { otp: string }) => {
    try {
      await verifyOtp({ phone, otp: data.otp }).unwrap()
      toast.success(t('phoneVerification.verified'))
      onComplete()
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('phoneVerification.errors.verifyFailed'))
      form.setError('otp', { message: t('phoneVerification.errors.invalidOtp') })
    }
  }

  const handleResendClick = async () => {
    await onResend()
    setCountdown(300)
    form.reset()
  }

  const formatCountdown = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">{t('phoneVerification.verifyTitle')}</h2>
        <p className="text-muted-foreground mt-2">
          {t('phoneVerification.verifyDescription', { phone })}
        </p>
      </div>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleVerify)} className="space-y-6">
          <FormField
            control={form.control}
            name="otp"
            render={({ field }) => (
              <FormItem className="flex flex-col items-center">
                <InputOTP
                  maxLength={6}
                  value={field.value}
                  onChange={field.onChange}
                  className="gap-2"
                  autoFocus
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
                <FormMessage />
                <p className="text-sm text-muted-foreground mt-2">
                  {countdown > 0
                    ? t('phoneVerification.expiresIn', { time: formatCountdown(countdown) })
                    : t('phoneVerification.expired')}
                </p>
              </FormItem>
            )}
          />

          <Button type="submit" className="w-full" disabled={isVerifying || countdown === 0}>
            {isVerifying ? t('phoneVerification.verifying') : t('phoneVerification.verify')}
          </Button>

          <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
            {countdown > 0 ? (
              <p>{t('phoneVerification.resendDisabled', { time: formatCountdown(countdown) })}</p>
            ) : (
              <Button
                type="button"
                variant="link"
                onClick={handleResendClick}
                disabled={isSending}
                className="h-auto p-0"
              >
                {isSending ? t('phoneVerification.sending') : t('phoneVerification.resend')}
              </Button>
            )}
            <Button
              type="button"
              variant="link"
              onClick={onBack}
              className="h-auto p-0"
            >
              {t('phoneVerification.changePhone')}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}

export function PhoneVerificationStep({ onComplete, onBack }: PhoneVerificationStepProps) {
  const { t } = useTranslation('onboarding')
  const [otpSent, setOtpSent] = useState(false)
  const [phone, setPhone] = useState('')
  const [sendOtp, { isLoading: isSending }] = useSendPhoneOtpMutation()

  const phoneForm = useForm({
    resolver: zodResolver(createPhoneSchema(t)),
    defaultValues: { phone: '' },
  })

  const handleSendOtp = async (data: { phone: string }) => {
    try {
      await sendOtp({ phone: data.phone }).unwrap()
      setPhone(data.phone)
      setOtpSent(true)
      toast.success(t('phoneVerification.otpSent'))
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('phoneVerification.errors.sendFailed'))
    }
  }

  const handleResend = async () => {
    try {
      await sendOtp({ phone }).unwrap()
      toast.success(t('phoneVerification.otpResent'))
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('phoneVerification.errors.sendFailed'))
    }
  }

  if (!otpSent) {
    return (
      <div className="space-y-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold">{t('phoneVerification.title')}</h2>
          <p className="text-muted-foreground mt-2">{t('phoneVerification.description')}</p>
        </div>

        <Form {...phoneForm}>
          <form onSubmit={phoneForm.handleSubmit(handleSendOtp)} className="space-y-6">
            <FormField
              control={phoneForm.control}
              name="phone"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('phoneVerification.phoneLabel')}</FormLabel>
                  <FormControl>
                    <Input type="tel" placeholder="+1234567890" {...field} />
                  </FormControl>
                  <FormDescription>{t('phoneVerification.phoneDescription')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button type="submit" className="w-full" disabled={isSending}>
              {isSending ? t('phoneVerification.sending') : t('phoneVerification.sendOtp')}
            </Button>

            {onBack && (
              <div className="text-center">
                <Button type="button" variant="link" onClick={onBack} className="h-auto p-0">
                  {t('common:buttons.back')}
                </Button>
              </div>
            )}
          </form>
        </Form>
      </div>
    )
  }

  return (
    <OtpVerificationForm
      phone={phone}
      onComplete={onComplete}
      onBack={() => setOtpSent(false)}
      onResend={handleResend}
      isSending={isSending}
    />
  )
}
