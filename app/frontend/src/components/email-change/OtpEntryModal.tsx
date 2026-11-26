import { useState, useEffect, useMemo, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { getErrorMessage } from '@/types/api'
import { useVerifyOTPMutation, useResendOTPMutation } from '@/features/user/emailChangeApi'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Button } from '@/components/ui/button'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from '@/components/ui/input-otp'

interface OtpEntryModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onVerified: () => void
  onCancel: () => void
  newEmail: string
}

interface OtpFormData {
  otpCode: string
}

const RESEND_COOLDOWN_SECONDS = 60

export function OtpEntryModal({
  open,
  onOpenChange,
  onVerified,
  onCancel,
  newEmail,
}: OtpEntryModalProps) {
  const { t } = useTranslation(['settings', 'auth', 'common', 'backend'])
  const [verifyOTP, { isLoading: isVerifying }] = useVerifyOTPMutation()
  const [resendOTP, { isLoading: isResending }] = useResendOTPMutation()
  const [resendCooldown, setResendCooldown] = useState(0)

  const otpSchema = useMemo(
    () =>
      z.object({
        otpCode: z.string().length(6, t('auth:validation.otpLength')),
      }),
    [t]
  )

  const form = useForm<OtpFormData>({
    resolver: zodResolver(otpSchema),
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

  const handleSubmit = useCallback(async (data: OtpFormData) => {
    try {
      await verifyOTP({ otp_code: data.otpCode }).unwrap()
      toast.success(t('settings:emailChange.messages.otpVerified'))
      form.reset()
      onVerified()
    } catch (error: unknown) {
      const errorMessage = getErrorMessage(error, t)
      form.setError('otpCode', { message: errorMessage })
    }
  }, [verifyOTP, t, form, onVerified])

  const handleResend = async () => {
    if (resendCooldown > 0) return

    try {
      await resendOTP().unwrap()
      toast.success(t('settings:emailChange.messages.otpResent'))
      setResendCooldown(RESEND_COOLDOWN_SECONDS)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const handleCancel = () => {
    form.reset()
    setResendCooldown(0)
    onCancel()
  }

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      handleCancel()
    }
    onOpenChange(newOpen)
  }

  // Auto-submit when 6 digits are entered
  useEffect(() => {
    const subscription = form.watch((value, { name }) => {
      if (name === 'otpCode' && value.otpCode?.length === 6) {
        form.handleSubmit(handleSubmit)()
      }
    })
    return () => subscription.unsubscribe()
  }, [form, handleSubmit])

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('settings:emailChange.otpModal.title')}</DialogTitle>
          <DialogDescription>
            {t('settings:emailChange.otpModal.description', { email: newEmail })}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
            <FormField
              control={form.control}
              name="otpCode"
              render={({ field }) => (
                <FormItem className="flex flex-col items-center">
                  <FormLabel>{t('settings:emailChange.otpModal.fields.otpCode')}</FormLabel>
                  <FormControl>
                    <InputOTP
                      maxLength={6}
                      value={field.value}
                      onChange={field.onChange}
                      className="gap-2"
                      autoFocus
                    >
                      <InputOTPGroup>
                        <InputOTPSlot index={0} className="h-12 w-12 text-lg" />
                        <InputOTPSlot index={1} className="h-12 w-12 text-lg" />
                        <InputOTPSlot index={2} className="h-12 w-12 text-lg" />
                      </InputOTPGroup>
                      <InputOTPSeparator />
                      <InputOTPGroup>
                        <InputOTPSlot index={3} className="h-12 w-12 text-lg" />
                        <InputOTPSlot index={4} className="h-12 w-12 text-lg" />
                        <InputOTPSlot index={5} className="h-12 w-12 text-lg" />
                      </InputOTPGroup>
                    </InputOTP>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="text-center text-sm text-muted-foreground">
              {resendCooldown > 0 ? (
                <p>{t('settings:emailChange.otpModal.resendCountdown', { seconds: resendCooldown })}</p>
              ) : (
                <p>
                  {t('settings:emailChange.otpModal.noCode')}{' '}
                  <Button
                    type="button"
                    variant="link"
                    onClick={handleResend}
                    disabled={isResending}
                    className="h-auto p-0"
                  >
                    {isResending
                      ? t('settings:emailChange.otpModal.buttons.resending')
                      : t('settings:emailChange.otpModal.buttons.resend')}
                  </Button>
                </p>
              )}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={handleCancel}>
                {t('common:buttons.cancel')}
              </Button>
              <Button type="submit" disabled={isVerifying}>
                {isVerifying
                  ? t('settings:emailChange.otpModal.buttons.verifying')
                  : t('settings:emailChange.otpModal.buttons.verify')}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
