import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
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
import { PasswordRequirements } from '@/components/password'
import { useConfirmPasswordResetMutation } from '@/features/auth/authApi'
import { getErrorMessage } from '@/types/api'
import { useTranslation } from 'react-i18next'
import { createPasswordSchema } from '@/lib/password-validation'

const createResetPasswordSchema = (t: (key: string) => string) =>
  z
    .object({
      password: createPasswordSchema(t),
      confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t('auth:validation.passwordsNoMatch'),
      path: ['confirmPassword'],
    })

type ResetPasswordFormData = z.infer<ReturnType<typeof createResetPasswordSchema>>

export function ResetPasswordPage() {
  const { t } = useTranslation(['translation', 'backend'])
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')

  const [confirmReset, { isLoading }] = useConfirmPasswordResetMutation()

  const form = useForm<ResetPasswordFormData>({
    resolver: zodResolver(createResetPasswordSchema(t)),
    defaultValues: {
      password: '',
      confirmPassword: '',
    },
  })

  if (!token) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold">{t('auth:resetPassword.invalidTitle')}</CardTitle>
            <CardDescription>
              {t('auth:resetPassword.invalidSubtitle')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Alert variant="destructive">
              <AlertDescription>
                {t('auth:resetPassword.invalidMessage')}
              </AlertDescription>
            </Alert>
          </CardContent>
          <CardFooter className="flex justify-center">
            <Link
              to="/forgot-password"
              className="text-primary hover:underline"
            >
              {t('auth:resetPassword.requestNewLink')}
            </Link>
          </CardFooter>
        </Card>
      </div>
    )
  }

  const onSubmit = async (data: ResetPasswordFormData) => {
    try {
      await confirmReset({
        token,
        new_password: data.password,
        organization_slug: import.meta.env.VITE_ORG_SLUG || '',
      }).unwrap()

      toast.success(t('auth:resetPassword.successMessage'), { category: 'auth' })
      navigate('/login', {
        state: { message: t('auth:resetPassword.successInfo') },
      })
    } catch (error: unknown) {
      form.setError('root', { message: getErrorMessage(error, t) })
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold">{t('auth:resetPassword.title')}</CardTitle>
          <CardDescription>{t('auth:resetPassword.subtitle')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              {form.formState.errors.root && (
                <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                  {form.formState.errors.root.message}
                </div>
              )}

              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('auth:resetPassword.newPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <PasswordRequirements control={form.control} name="password" />
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="confirmPassword"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('auth:resetPassword.confirmNewPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? t('auth:resetPassword.submitting') : t('auth:resetPassword.submit')}
              </Button>
            </form>
          </Form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            <Link to="/login" className="text-primary hover:underline">
              {t('auth:resetPassword.backToSignIn')}
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
