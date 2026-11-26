import { useEffect } from 'react'
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
import { PasswordRequirements } from '@/components/password'
import { useRegisterMutation } from '@/features/auth/authApi'
import { useValidateInvitationTokenQuery } from '@/features/users/usersApi'
import { getErrorMessage } from '@/types/api'
import { useTranslation } from 'react-i18next'
import { createPasswordSchema } from '@/lib/password-validation'
import { Badge } from '@/components/ui/badge'

const createRegisterSchema = (t: (key: string) => string, emailReadonly: boolean) =>
  z
    .object({
      email: emailReadonly
        ? z.string().email()
        : z.string().email(t('auth:validation.emailInvalid')),
      password: createPasswordSchema(t),
      confirmPassword: z.string(),
    })
    .refine((data) => data.password === data.confirmPassword, {
      message: t('auth:validation.passwordsNoMatch'),
      path: ['confirmPassword'],
    })

type RegisterFormData = z.infer<ReturnType<typeof createRegisterSchema>>

export function RegisterPage() {
  const { t } = useTranslation(['translation', 'backend'])
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [register, { isLoading }] = useRegisterMutation()

  const inviteToken = searchParams.get('invite_token') || undefined
  const orgSlugFromUrl = searchParams.get('org') || undefined

  // Validate invitation token if present
  const { data: inviteData, isError: inviteError } = useValidateInvitationTokenQuery(
    inviteToken ?? '',
    { skip: !inviteToken }
  )

  const isInvited = !!inviteToken && !!inviteData && !inviteError
  const invitedEmail = inviteData?.email ?? ''

  const form = useForm<RegisterFormData>({
    resolver: zodResolver(createRegisterSchema(t, isInvited)),
    defaultValues: {
      email: '',
      password: '',
      confirmPassword: '',
    },
  })

  // Pre-fill email from invitation
  useEffect(() => {
    if (isInvited && invitedEmail) {
      form.setValue('email', invitedEmail, { shouldValidate: true })
    }
  }, [isInvited, invitedEmail, form])

  const orgSlug = orgSlugFromUrl ?? inviteData?.organization_slug ?? import.meta.env.VITE_ORG_SLUG ?? ''

  const onSubmit = async (data: RegisterFormData) => {
    try {
      const payload: {
        email: string
        password: string
        organization_slug: string
        invite_token?: string
      } = {
        email: data.email,
        password: data.password,
        organization_slug: orgSlug,
      }
      if (inviteToken) {
        payload.invite_token = inviteToken
      }

      const result = await register(payload).unwrap()

      toast.success(t('auth:register.successMessage'), { category: 'auth' })

      if (result.requires_verification) {
        navigate('/verify-email', { state: { email: data.email } })
      } else {
        // Invited users are already verified — go straight to login
        navigate('/login', { state: { email: data.email } })
      }
    } catch (error: unknown) {
      form.setError('root', { message: getErrorMessage(error, t) })
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center gap-2">
            <CardTitle className="text-2xl font-bold">{t('auth:register.title')}</CardTitle>
            {isInvited && (
              <Badge variant="secondary">{t('auth:register.invitedBadge')}</Badge>
            )}
          </div>
          <CardDescription>
            {isInvited
              ? t('auth:register.invitedSubtitle')
              : t('auth:register.subtitle')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              {form.formState.errors.root && (
                <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                  {form.formState.errors.root.message}
                </div>
              )}

              {inviteToken && inviteError && (
                <div className="rounded-md bg-destructive/15 p-3 text-sm text-destructive">
                  {t('auth:register.inviteInvalid')}
                </div>
              )}

              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('auth:register.email')}</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        placeholder={t('auth:register.emailPlaceholder')}
                        readOnly={isInvited}
                        className={isInvited ? 'cursor-not-allowed opacity-60' : ''}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('auth:register.password')}</FormLabel>
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
                    <FormLabel>{t('auth:register.confirmPassword')}</FormLabel>
                    <FormControl>
                      <Input type="password" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? t('auth:register.submitting') : t('auth:register.submit')}
              </Button>
            </form>
          </Form>
        </CardContent>
        <CardFooter className="flex justify-center">
          <p className="text-sm text-muted-foreground">
            {t('auth:register.haveAccount')}{' '}
            <Link to="/login" className="text-primary hover:underline">
              {t('auth:register.signIn')}
            </Link>
          </p>
        </CardFooter>
      </Card>
    </div>
  )
}
