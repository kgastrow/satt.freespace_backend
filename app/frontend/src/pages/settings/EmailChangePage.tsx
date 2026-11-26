import { useState, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { getErrorMessage } from '@/types/api'
import {
  useInitiateEmailChangeMutation,
  useGetEmailChangeStatusQuery,
  useCancelEmailChangeMutation,
} from '@/features/user/emailChangeApi'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { IdentityVerificationModal } from '@/components/email-change/IdentityVerificationModal'
import { OtpEntryModal } from '@/components/email-change/OtpEntryModal'
import { useGetCurrentUserQuery } from '@/features/auth/authApi'

interface EmailChangeFormData {
  newEmail: string
}

export function EmailChangePage() {
  const { t } = useTranslation(['settings', 'auth', 'common', 'backend'])
  const { data: currentUser } = useGetCurrentUserQuery()
  const { data: statusData, refetch: refetchStatus } = useGetEmailChangeStatusQuery()
  const [initiateEmailChange, { isLoading: isInitiating }] = useInitiateEmailChangeMutation()
  const [cancelEmailChange, { isLoading: isCancelling }] = useCancelEmailChangeMutation()

  const [showIdentityModal, setShowIdentityModal] = useState(false)
  const [showOtpModal, setShowOtpModal] = useState(false)

  const emailChangeSchema = useMemo(
    () =>
      z.object({
        newEmail: z
          .string()
          .email(t('auth:validation.emailInvalid'))
          .min(1, t('auth:validation.emailRequired'))
          .refine(
            (email) => email !== currentUser?.email,
            t('settings:emailChange.validation.sameEmail')
          ),
      }),
    [t, currentUser?.email]
  )

  const form = useForm<EmailChangeFormData>({
    resolver: zodResolver(emailChangeSchema),
    defaultValues: {
      newEmail: '',
    },
  })

  const handleInitiate = async (data: EmailChangeFormData) => {
    try {
      await initiateEmailChange({ new_email: data.newEmail }).unwrap()
      await refetchStatus()
      setShowIdentityModal(true)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const handleIdentityVerified = async () => {
    setShowIdentityModal(false)
    await refetchStatus()
    setShowOtpModal(true)
  }

  const handleOtpVerified = async () => {
    setShowOtpModal(false)
    await refetchStatus()
    toast.success(t('settings:emailChange.messages.success'))
    form.reset()
  }

  const handleCancel = async () => {
    try {
      await cancelEmailChange().unwrap()
      await refetchStatus()
      toast.success(t('settings:emailChange.messages.cancelled'))
      setShowIdentityModal(false)
      setShowOtpModal(false)
      form.reset()
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const hasActiveRequest = statusData?.has_active_request

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:emailChange.title')}</CardTitle>
          <CardDescription>
            {t('settings:emailChange.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {hasActiveRequest && (
            <div className="mb-4 rounded-md bg-blue-50 dark:bg-blue-950/30 p-4">
              <p className="text-sm text-blue-900 dark:text-blue-100">
                {t('settings:emailChange.pendingRequest', {
                  email: statusData.new_email,
                  status: t(`settings:emailChange.status.${statusData.status}`),
                })}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleCancel}
                disabled={isCancelling}
                className="mt-2"
              >
                {isCancelling
                  ? t('settings:emailChange.buttons.cancelling')
                  : t('settings:emailChange.buttons.cancelRequest')}
              </Button>
            </div>
          )}

          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleInitiate)} className="space-y-4">
              <FormField
                control={form.control}
                name="newEmail"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:emailChange.fields.newEmail')}</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        autoComplete="email"
                        placeholder={currentUser?.email || ''}
                        disabled={hasActiveRequest}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t('settings:emailChange.fields.newEmailDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={isInitiating || hasActiveRequest}>
                  {isInitiating
                    ? t('settings:emailChange.buttons.continuing')
                    : t('settings:emailChange.buttons.continue')}
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>

      <IdentityVerificationModal
        open={showIdentityModal}
        onOpenChange={setShowIdentityModal}
        onVerified={handleIdentityVerified}
        onCancel={handleCancel}
      />

      <OtpEntryModal
        open={showOtpModal}
        onOpenChange={setShowOtpModal}
        onVerified={handleOtpVerified}
        onCancel={handleCancel}
        newEmail={statusData?.new_email || ''}
      />
    </div>
  )
}
