import { useTranslation } from 'react-i18next'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { Shield, AlertCircle, Users } from 'lucide-react'
import {
  useGetOrganizationTwoFactorSettingsQuery,
  useUpdateOrganizationTwoFactorSettingsMutation,
  useGetUsersWithout2FAQuery,
} from '@/store/api/twoFactorApi'
import { usePermission } from '@/hooks/usePermission'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { getErrorMessage } from '@/types/api'

const twoFactorSettingsSchema = z.object({
  two_factor_policy: z.enum(['disabled', 'optional', 'mandatory']),
  grace_period_days: z.number().int().min(1).max(30),
  two_factor_app_name: z.string().max(100).optional().nullable(),
})

type TwoFactorSettingsFormData = z.infer<typeof twoFactorSettingsSchema>

export function TwoFactorSettingsPage() {
  const { t } = useTranslation(['admin', 'common', 'backend'])
  const { canWrite } = usePermission('two_factor')

  const {
    data: settings,
    isLoading: isLoadingSettings,
    error: settingsError,
  } = useGetOrganizationTwoFactorSettingsQuery()

  const {
    data: usersWithout2FA,
  } = useGetUsersWithout2FAQuery(undefined, {
    skip: settings?.two_factor_policy !== 'mandatory',
  })

  const [updateSettings, { isLoading: isUpdating }] =
    useUpdateOrganizationTwoFactorSettingsMutation()

  const form = useForm<TwoFactorSettingsFormData>({
    resolver: zodResolver(twoFactorSettingsSchema),
    defaultValues: {
      two_factor_policy: 'disabled',
      grace_period_days: 7,
      two_factor_app_name: null,
    },
    values: settings
      ? {
          two_factor_policy: settings.two_factor_policy,
          grace_period_days: settings.grace_period_days,
          two_factor_app_name: settings.two_factor_app_name,
        }
      : undefined,
  })

  const onSubmit = async (data: TwoFactorSettingsFormData) => {
    try {
      await updateSettings(data).unwrap()
      toast.success(t('admin:twoFactor.updateSuccess'))
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const selectedPolicy = useWatch({ control: form.control, name: 'two_factor_policy' })

  if (isLoadingSettings) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-64" />
          <Skeleton className="mt-2 h-4 w-96" />
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-64" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  if (settingsError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t('admin:twoFactor.pageTitle')}
          </h1>
          <p className="text-muted-foreground">{t('admin:twoFactor.pageDescription')}</p>
        </div>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('common:error')}</AlertTitle>
          <AlertDescription>{getErrorMessage(settingsError, t)}</AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!settings) {
    return null
  }

  // Check if 2FA is allowed by super admin
  if (!settings.two_factor_allowed) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t('admin:twoFactor.pageTitle')}
          </h1>
          <p className="text-muted-foreground">{t('admin:twoFactor.pageDescription')}</p>
        </div>
        <Alert>
          <Shield className="h-4 w-4" />
          <AlertTitle>{t('admin:twoFactor.notAllowed.title')}</AlertTitle>
          <AlertDescription>
            {t('admin:twoFactor.notAllowed.description')}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t('admin:twoFactor.pageTitle')}
        </h1>
        <p className="text-muted-foreground">{t('admin:twoFactor.pageDescription')}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {t('admin:twoFactor.settingsCard.title')}
          </CardTitle>
          <CardDescription>
            {t('admin:twoFactor.settingsCard.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <FormField
                control={form.control}
                name="two_factor_policy"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:twoFactor.fields.policy.label')}</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      value={field.value}
                      disabled={!canWrite}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue
                            placeholder={t('admin:twoFactor.fields.policy.placeholder')}
                          />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="disabled">
                          {t('admin:twoFactor.fields.policy.options.disabled')}
                        </SelectItem>
                        <SelectItem value="optional">
                          {t('admin:twoFactor.fields.policy.options.optional')}
                        </SelectItem>
                        <SelectItem value="mandatory">
                          {t('admin:twoFactor.fields.policy.options.mandatory')}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {t('admin:twoFactor.fields.policy.description')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="two_factor_app_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('admin:twoFactor.fields.appName.label')}
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder={t('admin:twoFactor.fields.appName.placeholder')}
                        {...field}
                        value={field.value ?? ''}
                        onChange={(e) => field.onChange(e.target.value || null)}
                        disabled={!canWrite}
                      />
                    </FormControl>
                    <FormDescription>
                      {t('admin:twoFactor.fields.appName.description')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {selectedPolicy === 'mandatory' && (
                <FormField
                  control={form.control}
                  name="grace_period_days"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        {t('admin:twoFactor.fields.gracePeriod.label')}
                      </FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min="1"
                          max="30"
                          {...field}
                          disabled={!canWrite}
                        />
                      </FormControl>
                      <FormDescription>
                        {t('admin:twoFactor.fields.gracePeriod.description')}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {canWrite && (
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating
                    ? t('admin:twoFactor.actions.saving')
                    : t('admin:twoFactor.actions.save')}
                </Button>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      {settings.two_factor_policy === 'mandatory' &&
        settings.enforcement_start_time && (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>{t('admin:twoFactor.enforcementAlert.title')}</AlertTitle>
            <AlertDescription>
              {t('admin:twoFactor.enforcementAlert.description', {
                date: new Date(settings.enforcement_start_time).toLocaleDateString(),
              })}
            </AlertDescription>
          </Alert>
        )}

      {settings.two_factor_policy === 'mandatory' && usersWithout2FA && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              {t('admin:twoFactor.usersCard.title')}
            </CardTitle>
            <CardDescription>
              {t('admin:twoFactor.usersCard.description', {
                count: usersWithout2FA.total,
              })}
            </CardDescription>
          </CardHeader>
          {usersWithout2FA.total > 0 && (
            <CardContent>
              <div className="space-y-2">
                {usersWithout2FA.users.map((user) => (
                  <div
                    key={user.id}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div>
                      <p className="font-medium">
                        {user.first_name} {user.last_name}
                      </p>
                      <p className="text-sm text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  )
}
