import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
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
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { useRequestPasswordResetMutation } from '@/features/auth/authApi'
import { useTranslation } from 'react-i18next'

const createForgotPasswordSchema = (t: (key: string) => string) =>
  z.object({
    email: z.string().email(t('auth:validation.emailInvalid')),
  })

type ForgotPasswordFormData = z.infer<ReturnType<typeof createForgotPasswordSchema>>

export function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [submitted, setSubmitted] = useState(false)
  const [requestReset, { isLoading }] = useRequestPasswordResetMutation()

  const form = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(createForgotPasswordSchema(t)),
    defaultValues: {
      email: '',
    },
  })

  const onSubmit = async (data: ForgotPasswordFormData) => {
    try {
      await requestReset({
        email: data.email,
        organization_slug: import.meta.env.VITE_ORG_SLUG || '',
      }).unwrap()
    } catch {
      // Always show success for security reasons
    }
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold">{t('auth:forgotPassword.checkEmailTitle')}</CardTitle>
            <CardDescription>
              {t('auth:forgotPassword.checkEmailSubtitle')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Alert>
              <AlertDescription>
                {t('auth:forgotPassword.checkInbox')}
              </AlertDescription>
            </Alert>
          </CardContent>
          <CardFooter className="flex justify-center">
            <Link to="/login" className="text-primary hover:underline">
              {t('auth:forgotPassword.backToSignIn')}
            </Link>
          </CardFooter>
        </Card>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold">{t('auth:forgotPassword.title')}</CardTitle>
          <CardDescription>
            {t('auth:forgotPassword.subtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('auth:forgotPassword.email')}</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        placeholder={t('auth:forgotPassword.emailPlaceholder')}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? t('auth:forgotPassword.submitting') : t('auth:forgotPassword.submit')}
              </Button>
            </form>
          </Form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            {t('auth:forgotPassword.rememberPassword')}{' '}
            <Link to="/login" className="text-primary hover:underline">
              {t('auth:forgotPassword.backToSignIn')}
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
