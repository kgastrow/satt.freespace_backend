import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Switch } from '@/components/ui/switch'
import { WebPushCard } from '@/components/notifications/WebPushCard'
import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { CardSkeleton } from '@/components/skeletons'
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
import {
  useGetUserPreferencesQuery,
  useUpdateUserPreferencesMutation,
  useGetCategoryPreferencesQuery,
  useUpdateCategoryPreferenceMutation,
} from '@/features/notifications/notificationsApi'

const preferencesSchema = z.object({
  email_enabled: z.boolean(),
  sms_enabled: z.boolean(),
  whatsapp_enabled: z.boolean(),
  in_app_enabled: z.boolean(),
  web_push_enabled: z.boolean(),
  quiet_hours_enabled: z.boolean(),
  quiet_hours_start: z.string().optional(),
  quiet_hours_end: z.string().optional(),
  quiet_hours_timezone: z.string(),
})

type PreferencesFormData = z.infer<typeof preferencesSchema>

const timezones = [
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Anchorage',
  'Pacific/Honolulu',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Australia/Sydney',
  'UTC',
]

const timeOptions = Array.from({ length: 24 }, (_, i) => {
  const hour = i.toString().padStart(2, '0')
  return { value: `${hour}:00`, label: `${hour}:00` }
})

export function NotificationsPage() {
  const { t } = useTranslation('settings')
  const { data: preferences, isLoading: isLoadingPreferences } = useGetUserPreferencesQuery()
  const { data: categoryPreferences, isLoading: isLoadingCategories } =
    useGetCategoryPreferencesQuery()
  const [updatePreferences, { isLoading: isUpdating }] = useUpdateUserPreferencesMutation()
  const [updateCategoryPreference] = useUpdateCategoryPreferenceMutation()

  const form = useForm<PreferencesFormData>({
    resolver: zodResolver(preferencesSchema),
    defaultValues: {
      email_enabled: true,
      sms_enabled: false,
      whatsapp_enabled: false,
      in_app_enabled: true,
      web_push_enabled: false,
      quiet_hours_enabled: false,
      quiet_hours_start: '22:00',
      quiet_hours_end: '07:00',
      quiet_hours_timezone: 'America/New_York',
    },
  })

  const quietHoursEnabled = useWatch({ control: form.control, name: 'quiet_hours_enabled' })
  const webPushEnabled = useWatch({ control: form.control, name: 'web_push_enabled' })

  useEffect(() => {
    if (preferences) {
      form.reset({
        email_enabled: preferences.email_enabled,
        sms_enabled: preferences.sms_enabled,
        whatsapp_enabled: preferences.whatsapp_enabled,
        in_app_enabled: preferences.in_app_enabled,
        web_push_enabled: preferences.web_push_enabled,
        quiet_hours_enabled: preferences.quiet_hours_enabled,
        quiet_hours_start: preferences.quiet_hours_start || '22:00',
        quiet_hours_end: preferences.quiet_hours_end || '07:00',
        quiet_hours_timezone: preferences.quiet_hours_timezone,
      })
    }
  }, [preferences, form])

  const handleSubmit = async (data: PreferencesFormData) => {
    try {
      await updatePreferences(data).unwrap()
      toast.success(t('notifications.messages.updateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('notifications.messages.updateError'))
    }
  }

  const handleCategoryToggle = async (
    categoryId: string,
    channel: 'email' | 'sms' | 'whatsapp' | 'in_app',
    currentValue: boolean
  ) => {
    try {
      await updateCategoryPreference({
        category_id: categoryId,
        data: { [`${channel}_enabled`]: !currentValue },
      }).unwrap()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('notifications.messages.categoryUpdateError'))
    }
  }

  if (isLoadingPreferences) {
    return (
      <div className="space-y-4 max-w-2xl">
        <Skeleton className="h-8 w-64 mb-2" />
        <CardSkeleton variant="default" />
        <CardSkeleton variant="default" />
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Global Channel Settings */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('notifications.sections.channels.title')}</CardTitle>
              <CardDescription>
                {t('notifications.sections.channels.description')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <FormField
                control={form.control}
                name="email_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.channels.email.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.channels.email.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="sms_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.channels.sms.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.channels.sms.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="whatsapp_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.channels.whatsapp.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.channels.whatsapp.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="in_app_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.channels.inApp.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.channels.inApp.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {/* The ACCOUNT half of push. The device half is WebPushCard
                  below: both have to be on before anything is delivered. */}
              <FormField
                control={form.control}
                name="web_push_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.channels.webPush.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.channels.webPush.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <WebPushCard channelEnabled={webPushEnabled} />

          {/* Quiet Hours */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('notifications.sections.quietHours.title')}</CardTitle>
              <CardDescription>
                {t('notifications.sections.quietHours.description')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <FormField
                control={form.control}
                name="quiet_hours_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel className="text-sm">{t('notifications.quietHours.enable.label')}</FormLabel>
                      <FormDescription className="text-xs">
                        {t('notifications.quietHours.enable.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {quietHoursEnabled && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-2">
                  <FormField
                    control={form.control}
                    name="quiet_hours_start"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-sm">{t('notifications.quietHours.startTime')}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('notifications.quietHours.selectTime')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {timeOptions.map((time) => (
                              <SelectItem key={time.value} value={time.value}>
                                {time.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="quiet_hours_end"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-sm">{t('notifications.quietHours.endTime')}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('notifications.quietHours.selectTime')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {timeOptions.map((time) => (
                              <SelectItem key={time.value} value={time.value}>
                                {time.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="quiet_hours_timezone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-sm">{t('notifications.quietHours.timezone')}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('notifications.quietHours.selectTimezone')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {timezones.map((tz) => (
                              <SelectItem key={tz} value={tz}>
                                {tz.replace('_', ' ')}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Category Preferences */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">{t('notifications.sections.categories.title')}</CardTitle>
              <CardDescription>
                {t('notifications.sections.categories.description')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingCategories ? (
                <div className="space-y-3">
                  {Array.from({ length: 2 }).map((_, i) => (
                    <Skeleton key={i} className="h-16 w-full" />
                  ))}
                </div>
              ) : categoryPreferences?.items.length === 0 ? (
                <p className="text-muted-foreground text-center py-4 text-sm">
                  {t('notifications.messages.noCategories')}
                </p>
              ) : (
                <div className="space-y-3">
                  {categoryPreferences?.items
                    .filter((item) => item.category.user_configurable)
                    .map((item) => (
                      <div
                        key={item.category.id}
                        className="flex flex-col sm:flex-row sm:items-center justify-between rounded-lg border p-3 gap-3"
                      >
                        <div>
                          <p className="font-medium text-sm">{item.category.name}</p>
                          {item.category.description && (
                            <p className="text-xs text-muted-foreground">
                              {item.category.description}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-3 flex-wrap">
                          <label className="flex items-center gap-1.5 text-xs">
                            <Checkbox
                              checked={item.email_enabled}
                              onCheckedChange={() =>
                                handleCategoryToggle(item.category.id, 'email', item.email_enabled)
                              }
                            />
                            {t('notifications.categoryChannels.email')}
                          </label>
                          <label className="flex items-center gap-1.5 text-xs">
                            <Checkbox
                              checked={item.sms_enabled}
                              onCheckedChange={() =>
                                handleCategoryToggle(item.category.id, 'sms', item.sms_enabled)
                              }
                            />
                            {t('notifications.categoryChannels.sms')}
                          </label>
                          <label className="flex items-center gap-1.5 text-xs">
                            <Checkbox
                              checked={item.whatsapp_enabled}
                              onCheckedChange={() =>
                                handleCategoryToggle(item.category.id, 'whatsapp', item.whatsapp_enabled)
                              }
                            />
                            {t('notifications.categoryChannels.whatsapp')}
                          </label>
                          <label className="flex items-center gap-1.5 text-xs">
                            <Checkbox
                              checked={item.in_app_enabled}
                              onCheckedChange={() =>
                                handleCategoryToggle(item.category.id, 'in_app', item.in_app_enabled)
                              }
                            />
                            {t('notifications.categoryChannels.inApp')}
                          </label>
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button type="submit" disabled={isUpdating}>
              {isUpdating ? t('notifications.buttons.saving') : t('notifications.buttons.savePreferences')}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
