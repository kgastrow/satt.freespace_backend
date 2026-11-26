import { useState, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { Eye, EyeOff } from 'lucide-react'
import { toast } from '@/lib/toast'
import { getErrorMessage } from '@/types/api'
import { useVerifyIdentityMutation } from '@/features/user/emailChangeApi'
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
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  InputOTPSeparator,
} from '@/components/ui/input-otp'

interface IdentityVerificationModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onVerified: () => void
  onCancel: () => void
}

type VerificationMethod = 'password' | '2fa'

interface PasswordFormData {
  password: string
}

interface TwoFactorFormData {
  code: string
}

export function IdentityVerificationModal({
  open,
  onOpenChange,
  onVerified,
  onCancel,
}: IdentityVerificationModalProps) {
  const { t } = useTranslation(['settings', 'auth', 'common', 'backend'])
  const [verifyIdentity, { isLoading: isVerifying }] = useVerifyIdentityMutation()
  const [verificationMethod, setVerificationMethod] = useState<VerificationMethod>('password')
  const [showPassword, setShowPassword] = useState(false)

  const passwordSchema = useMemo(
    () =>
      z.object({
        password: z.string().min(1, t('auth:validation.passwordRequired')),
      }),
    [t]
  )

  const twoFactorSchema = useMemo(
    () =>
      z.object({
        code: z.string().length(6, t('auth:validation.otpLength')),
      }),
    [t]
  )

  const passwordForm = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
    defaultValues: {
      password: '',
    },
  })

  const twoFactorForm = useForm<TwoFactorFormData>({
    resolver: zodResolver(twoFactorSchema),
    defaultValues: {
      code: '',
    },
  })

  const handlePasswordSubmit = async (data: PasswordFormData) => {
    try {
      await verifyIdentity({
        verification_method: 'password',
        verification_value: data.password,
      }).unwrap()
      toast.success(t('settings:emailChange.messages.identityVerified'))
      passwordForm.reset()
      onVerified()
    } catch (error: unknown) {
      const errorMessage = getErrorMessage(error, t)
      passwordForm.setError('password', { message: errorMessage })
    }
  }

  const handleTwoFactorSubmit = async (data: TwoFactorFormData) => {
    try {
      await verifyIdentity({
        verification_method: 'totp',
        verification_value: data.code,
      }).unwrap()
      toast.success(t('settings:emailChange.messages.identityVerified'))
      twoFactorForm.reset()
      onVerified()
    } catch (error: unknown) {
      const errorMessage = getErrorMessage(error, t)
      twoFactorForm.setError('code', { message: errorMessage })
    }
  }

  const handleCancel = () => {
    passwordForm.reset()
    twoFactorForm.reset()
    onCancel()
  }

  const handleOpenChange = (newOpen: boolean) => {
    if (!newOpen) {
      handleCancel()
    }
    onOpenChange(newOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('settings:emailChange.identityModal.title')}</DialogTitle>
          <DialogDescription>
            {t('settings:emailChange.identityModal.description')}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={verificationMethod} onValueChange={(v) => setVerificationMethod(v as VerificationMethod)}>
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="password">
              {t('settings:emailChange.identityModal.tabs.password')}
            </TabsTrigger>
            <TabsTrigger value="2fa">
              {t('settings:emailChange.identityModal.tabs.twoFactor')}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="password" className="mt-4">
            <Form {...passwordForm}>
              <form onSubmit={passwordForm.handleSubmit(handlePasswordSubmit)} className="space-y-4">
                <FormField
                  control={passwordForm.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('settings:emailChange.identityModal.fields.password')}</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type={showPassword ? 'text' : 'password'}
                            autoComplete="current-password"
                            {...field}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            className="absolute right-1 top-1/2 -translate-y-1/2"
                            onClick={() => setShowPassword(!showPassword)}
                          >
                            {showPassword ? (
                              <EyeOff className="size-4" />
                            ) : (
                              <Eye className="size-4" />
                            )}
                            <span className="sr-only">
                              {showPassword
                                ? t('settings:emailChange.identityModal.hidePassword')
                                : t('settings:emailChange.identityModal.showPassword')}
                            </span>
                          </Button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <DialogFooter>
                  <Button type="button" variant="outline" onClick={handleCancel}>
                    {t('common:buttons.cancel')}
                  </Button>
                  <Button type="submit" disabled={isVerifying}>
                    {isVerifying
                      ? t('settings:emailChange.identityModal.buttons.verifying')
                      : t('settings:emailChange.identityModal.buttons.verify')}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </TabsContent>

          <TabsContent value="2fa" className="mt-4">
            <Form {...twoFactorForm}>
              <form onSubmit={twoFactorForm.handleSubmit(handleTwoFactorSubmit)} className="space-y-4">
                <FormField
                  control={twoFactorForm.control}
                  name="code"
                  render={({ field }) => (
                    <FormItem className="flex flex-col items-center">
                      <FormLabel>{t('settings:emailChange.identityModal.fields.twoFactorCode')}</FormLabel>
                      <FormControl>
                        <InputOTP
                          maxLength={6}
                          value={field.value}
                          onChange={field.onChange}
                          className="gap-2"
                        >
                          <InputOTPGroup>
                            <InputOTPSlot index={0} />
                            <InputOTPSlot index={1} />
                            <InputOTPSlot index={2} />
                          </InputOTPGroup>
                          <InputOTPSeparator />
                          <InputOTPGroup>
                            <InputOTPSlot index={3} />
                            <InputOTPSlot index={4} />
                            <InputOTPSlot index={5} />
                          </InputOTPGroup>
                        </InputOTP>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <DialogFooter>
                  <Button type="button" variant="outline" onClick={handleCancel}>
                    {t('common:buttons.cancel')}
                  </Button>
                  <Button type="submit" disabled={isVerifying}>
                    {isVerifying
                      ? t('settings:emailChange.identityModal.buttons.verifying')
                      : t('settings:emailChange.identityModal.buttons.verify')}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
