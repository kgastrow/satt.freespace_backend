import { useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { getErrorMessage } from '@/types/api'
import { useChangePasswordMutation } from '@/features/user/userApi'
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PasswordRequirements } from '@/components/password'
import { createPasswordSchema } from '@/lib/password-validation'

interface ChangePasswordFormData {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}

export function PasswordPage() {
  const { t } = useTranslation(['settings', 'auth', 'common', 'backend'])
  const [changePassword, { isLoading: isChangingPassword }] = useChangePasswordMutation()
  const [passwordError, setPasswordError] = useState<string | null>(null)

  const changePasswordSchema = useMemo(
    () =>
      z
        .object({
          currentPassword: z.string().min(1, t('auth:validation.currentPasswordRequired')),
          newPassword: createPasswordSchema(t),
          confirmPassword: z.string(),
        })
        .refine((data) => data.newPassword === data.confirmPassword, {
          message: t('auth:validation.passwordsNoMatch'),
          path: ['confirmPassword'],
        }),
    [t]
  )

  const form = useForm<ChangePasswordFormData>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
  })

  const handleSubmit = async (data: ChangePasswordFormData) => {
    setPasswordError(null)
    try {
      await changePassword({
        current_password: data.currentPassword,
        new_password: data.newPassword,
      }).unwrap()
      toast.success(t('settings:profile.messages.passwordUpdateSuccess'))
      form.reset()
    } catch (error: unknown) {
      setPasswordError(getErrorMessage(error, t))
    }
  }

  return (
    <div className="max-w-2xl">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:profile.sections.changePassword.title')}</CardTitle>
          <CardDescription>
            {t('settings:profile.sections.changePassword.securityNote')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
              {(form.formState.errors.root || passwordError) && (
                <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                  {form.formState.errors.root?.message || passwordError}
                </div>
              )}

              <FormField
                control={form.control}
                name="currentPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:profile.fields.currentPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="current-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="newPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:profile.fields.newPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <PasswordRequirements control={form.control} name="newPassword" />
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:profile.fields.confirmPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" autoComplete="new-password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex justify-end pt-2">
                <Button type="submit" disabled={isChangingPassword}>
                  {isChangingPassword
                    ? t('settings:profile.buttons.updating')
                    : t('settings:profile.buttons.updatePassword')}
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}
