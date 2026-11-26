import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { NumberField } from '@/features/sites/components/NumberField'
import { NotificationWindowEditor } from '@/features/sites/components/NotificationWindowEditor'
import { useGetSiteConfigQuery, useUpdateSiteConfigMutation } from '@/features/sites/sitesApi'
import { useSitePermissions } from '@/features/sites/permissions'
import { getServerError } from '@/features/sites/errors'
import { normaliseWindow } from '@/features/sites/notificationWindow'
import {
  createSiteSettingsSchema,
  type SiteSettingsFormValues,
} from '@/features/sites/siteSettingsSchema'
import type { Site, SiteConfig } from '@/types/site'

function toFormValues(config: SiteConfig): SiteSettingsFormValues {
  return {
    trigger_pct: config.trigger_pct,
    reset_pct: config.reset_pct,
    change_points: config.change_points,
    change_direction: config.change_direction,
    stabilisation_s: config.stabilisation_s,
    recommendation_margin: config.recommendation_margin,
    stale_limit_s: config.stale_limit_s,
    partial_is_stale: config.partial_is_stale,
    recovery_push: config.recovery_push,
    zone_advisory: config.zone_advisory,
    zone_reset_gap: config.zone_reset_gap,
    notification_window: config.notification_window.map((rule) => ({ ...rule })),
    cooldown_s: config.cooldown_s,
    daily_cap: config.daily_cap,
    push_expiry_s: config.push_expiry_s,
  }
}

interface SwitchFieldProps {
  form: ReturnType<typeof useForm<SiteSettingsFormValues>>
  name: 'partial_is_stale' | 'recovery_push' | 'zone_advisory'
  label: string
  description: string
  disabled: boolean
}

function SwitchField({ form, name, label, description, disabled }: SwitchFieldProps) {
  return (
    <FormField
      control={form.control}
      name={name}
      render={({ field }) => (
        <FormItem className="flex items-center justify-between gap-4 space-y-0">
          <div className="space-y-1">
            <FormLabel>{label}</FormLabel>
            <FormDescription>{description}</FormDescription>
          </div>
          <FormControl>
            <Switch checked={field.value} onCheckedChange={field.onChange} disabled={disabled} />
          </FormControl>
        </FormItem>
      )}
    />
  )
}

function SiteSettings({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { data: config, isLoading, error } = useGetSiteConfigQuery(site.id)

  if (isLoading) return <Skeleton className="h-96 w-full" />
  if (error || !config) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('sites:settings.loadError')}</AlertTitle>
        <AlertDescription>{getServerError(error, t).message}</AlertDescription>
      </Alert>
    )
  }
  return <SiteSettingsForm site={site} config={config} />
}

function SiteSettingsForm({ site, config }: { site: Site; config: SiteConfig }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { canWrite } = useSitePermissions()
  const [updateConfig, { isLoading: isSaving }] = useUpdateSiteConfigMutation()
  const [serverError, setServerError] = useState<{ message: string; detail: string | null } | null>(
    null
  )

  const schema = useMemo(() => createSiteSettingsSchema(t), [t])
  const form = useForm<SiteSettingsFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toFormValues(config),
  })

  // Follow the server copy after a save or refetch.
  useEffect(() => {
    form.reset(toFormValues(config))
  }, [config, form])

  const onSubmit = async (values: SiteSettingsFormValues) => {
    setServerError(null)
    try {
      await updateConfig({
        id: site.id,
        data: {
          ...values,
          change_direction: values.change_direction as SiteConfig['change_direction'],
          notification_window: normaliseWindow(values.notification_window),
        },
      }).unwrap()
      toast.success(t('sites:settings.saved'))
    } catch (err) {
      setServerError(getServerError(err, t))
    }
  }

  const readOnly = !canWrite

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6" noValidate>
        {readOnly && (
          <Alert>
            <AlertDescription>{t('sites:readOnlyNotice')}</AlertDescription>
          </Alert>
        )}
        {serverError && (
          <Alert variant="destructive" role="alert">
            <AlertTitle>{serverError.message}</AlertTitle>
            {serverError.detail && <AlertDescription>{serverError.detail}</AlertDescription>}
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle>{t('sites:settings.trigger.title')}</CardTitle>
            <CardDescription>{t('sites:settings.trigger.description')}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <NumberField control={form.control} name="trigger_pct" disabled={readOnly} suffix="%"
              label={t('sites:settings.fields.trigger_pct.label')}
              description={t('sites:settings.fields.trigger_pct.help')} />
            <NumberField control={form.control} name="reset_pct" disabled={readOnly} suffix="%"
              label={t('sites:settings.fields.reset_pct.label')}
              description={t('sites:settings.fields.reset_pct.help')} />
            <NumberField control={form.control} name="change_points" disabled={readOnly}
              label={t('sites:settings.fields.change_points.label')}
              description={t('sites:settings.fields.change_points.help')} />
            <FormField
              control={form.control}
              name="change_direction"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:settings.fields.change_direction.label')}</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange} disabled={readOnly}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="RISING">
                        {t('sites:settings.fields.change_direction.RISING')}
                      </SelectItem>
                      <SelectItem value="BOTH">
                        {t('sites:settings.fields.change_direction.BOTH')}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>{t('sites:settings.fields.change_direction.help')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <NumberField control={form.control} name="stabilisation_s" disabled={readOnly}
              suffix={t('sites:units.seconds')}
              label={t('sites:settings.fields.stabilisation_s.label')}
              description={t('sites:settings.fields.stabilisation_s.help')} />
            <NumberField control={form.control} name="recommendation_margin" disabled={readOnly}
              suffix={t('sites:units.bays')}
              label={t('sites:settings.fields.recommendation_margin.label')}
              description={t('sites:settings.fields.recommendation_margin.help')} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('sites:settings.data.title')}</CardTitle>
            <CardDescription>{t('sites:settings.data.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <NumberField control={form.control} name="stale_limit_s" disabled={readOnly}
              suffix={t('sites:units.seconds')}
              label={t('sites:settings.fields.stale_limit_s.label')}
              description={t('sites:settings.fields.stale_limit_s.help')} />
            <SwitchField form={form} name="partial_is_stale" disabled={readOnly}
              label={t('sites:settings.fields.partial_is_stale.label')}
              description={t('sites:settings.fields.partial_is_stale.help')} />
            <SwitchField form={form} name="recovery_push" disabled={readOnly}
              label={t('sites:settings.fields.recovery_push.label')}
              description={t('sites:settings.fields.recovery_push.help')} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('sites:settings.zoneAdvisory.title')}</CardTitle>
            <CardDescription>{t('sites:settings.zoneAdvisory.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <SwitchField form={form} name="zone_advisory" disabled={readOnly}
              label={t('sites:settings.fields.zone_advisory.label')}
              description={t('sites:settings.fields.zone_advisory.help')} />
            <NumberField control={form.control} name="zone_reset_gap" disabled={readOnly}
              suffix={t('sites:units.points')}
              label={t('sites:settings.fields.zone_reset_gap.label')}
              description={t('sites:settings.fields.zone_reset_gap.help')} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('sites:settings.window.title')}</CardTitle>
            <CardDescription>
              {t('sites:settings.window.description', { timeZone: site.time_zone })}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FormField
              control={form.control}
              name="notification_window"
              render={({ field }) => (
                <FormItem>
                  <NotificationWindowEditor
                    value={field.value}
                    onChange={field.onChange}
                    disabled={readOnly}
                  />
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t('sites:settings.limits.title')}</CardTitle>
            <CardDescription>{t('sites:settings.limits.description')}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <NumberField control={form.control} name="cooldown_s" disabled={readOnly}
              suffix={t('sites:units.seconds')}
              label={t('sites:settings.fields.cooldown_s.label')}
              description={t('sites:settings.fields.cooldown_s.help')} />
            <NumberField control={form.control} name="daily_cap" disabled={readOnly}
              label={t('sites:settings.fields.daily_cap.label')}
              description={t('sites:settings.fields.daily_cap.help')} />
            <NumberField control={form.control} name="push_expiry_s" disabled={readOnly}
              suffix={t('sites:units.seconds')}
              label={t('sites:settings.fields.push_expiry_s.label')}
              description={t('sites:settings.fields.push_expiry_s.help')} />
          </CardContent>
        </Card>

        {canWrite && (
          <div className="flex gap-2">
            <Button type="submit" disabled={isSaving}>
              {isSaving ? t('sites:actions.saving') : t('sites:actions.save')}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={isSaving || !form.formState.isDirty}
              onClick={() => {
                setServerError(null)
                form.reset(toFormValues(config))
              }}
            >
              {t('sites:actions.discard')}
            </Button>
          </div>
        )}
      </form>
    </Form>
  )
}

export function SiteSettingsPage() {
  return <SiteDetailShell>{(site) => <SiteSettings site={site} />}</SiteDetailShell>
}
