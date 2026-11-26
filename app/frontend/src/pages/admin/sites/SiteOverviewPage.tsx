import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Trash2 } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { getErrorMessage } from '@/types/api'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import {
  useDeleteSiteMutation,
  useUpdateSiteConfigMutation,
  useUpdateSiteMutation,
} from '@/features/sites/sitesApi'
import { useSitePermissions } from '@/features/sites/permissions'
import { getServerError } from '@/features/sites/errors'
import { formatDateTime } from '@/features/sites/format'
import {
  createSiteIdentitySchema,
  type SiteIdentityFormValues,
} from '@/features/sites/siteSettingsSchema'
import type { Site } from '@/types/site'

function SiteOverview({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const navigate = useNavigate()
  const { canWrite } = useSitePermissions()
  const [updateSite, { isLoading: isSavingSite }] = useUpdateSiteMutation()
  const [updateConfig, { isLoading: isSavingConfig }] = useUpdateSiteConfigMutation()
  const [deleteSite, { isLoading: isDeleting }] = useDeleteSiteMutation()
  const [managedConfirm, setManagedConfirm] = useState<boolean | null>(null)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [formError, setFormError] = useState<{ message: string; detail: string | null } | null>(
    null
  )

  const form = useForm<SiteIdentityFormValues>({
    resolver: zodResolver(createSiteIdentitySchema(t)),
    defaultValues: { name: site.name, fcm_topic: site.fcm_topic, time_zone: site.time_zone },
  })

  useEffect(() => {
    form.reset({ name: site.name, fcm_topic: site.fcm_topic, time_zone: site.time_zone })
  }, [site, form])

  const onSubmit = async (values: SiteIdentityFormValues) => {
    setFormError(null)
    try {
      if (values.name.trim() !== site.name || values.fcm_topic !== site.fcm_topic) {
        await updateSite({
          id: site.id,
          data: { name: values.name.trim(), fcm_topic: values.fcm_topic },
        }).unwrap()
      }
      if (values.time_zone !== site.time_zone) {
        await updateConfig({ id: site.id, data: { time_zone: values.time_zone } }).unwrap()
      }
      toast.success(t('sites:overview.saved'))
    } catch (error) {
      setFormError(getServerError(error, t))
    }
  }

  const setListed = async (listed: boolean) => {
    try {
      await updateConfig({ id: site.id, data: { listed } }).unwrap()
      toast.success(t('sites:overview.listedSaved'))
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const confirmManaged = async () => {
    if (managedConfirm === null) return
    try {
      await updateConfig({ id: site.id, data: { managed: managedConfirm } }).unwrap()
      toast.success(
        managedConfirm ? t('sites:overview.managedOn') : t('sites:overview.managedOff')
      )
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    } finally {
      setManagedConfirm(null)
    }
  }

  const handleDelete = async () => {
    try {
      await deleteSite(site.id).unwrap()
      toast.success(t('sites:overview.deleted'))
      navigate('/admin/sites')
    } catch (error) {
      toast.error(getErrorMessage(error, t))
      setDeleteOpen(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>{t('sites:overview.identityTitle')}</CardTitle>
          <CardDescription>{t('sites:overview.identityDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              {formError && (
                <Alert variant="destructive">
                  <AlertTitle>{formError.message}</AlertTitle>
                  {formError.detail && <AlertDescription>{formError.detail}</AlertDescription>}
                </Alert>
              )}
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('sites:fields.name')}</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={!canWrite} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="space-y-2">
                <Label htmlFor="site-slug">{t('sites:fields.slug')}</Label>
                <Input id="site-slug" value={site.slug} readOnly className="font-mono" />
                <p className="text-sm text-muted-foreground">{t('sites:fields.slugReadOnly')}</p>
              </div>
              <FormField
                control={form.control}
                name="fcm_topic"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('sites:fields.topic')}</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={!canWrite} className="font-mono" />
                    </FormControl>
                    <FormDescription>{t('sites:fields.topicHelp')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="time_zone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('sites:fields.timeZone')}</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={!canWrite} />
                    </FormControl>
                    <FormDescription>{t('sites:fields.timeZoneHelp')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {canWrite && (
                <Button type="submit" disabled={isSavingSite || isSavingConfig}>
                  {isSavingSite || isSavingConfig ? t('sites:actions.saving') : t('sites:actions.save')}
                </Button>
              )}
            </form>
          </Form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('sites:overview.modeTitle')}</CardTitle>
          <CardDescription>{t('sites:overview.modeDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <Label htmlFor="site-managed">{t('sites:fields.managed')}</Label>
              <p className="text-sm text-muted-foreground">{t('sites:fields.managedHelp')}</p>
            </div>
            <Switch
              id="site-managed"
              checked={site.managed}
              disabled={!canWrite || isSavingConfig}
              onCheckedChange={(checked) => setManagedConfirm(checked)}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <Label htmlFor="site-listed">{t('sites:fields.listed')}</Label>
              <p className="text-sm text-muted-foreground">{t('sites:fields.listedHelp')}</p>
            </div>
            <Switch
              id="site-listed"
              checked={site.listed}
              disabled={!canWrite || isSavingConfig}
              onCheckedChange={setListed}
            />
          </div>
          <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">
              {t('sites:overview.created', { date: formatDateTime(site.created_time) ?? '-' })}
            </Badge>
            <Badge variant="outline">
              {t('sites:overview.updated', { date: formatDateTime(site.updated_time) ?? '-' })}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {canWrite && (
        <Card className="border-destructive/50">
          <CardHeader>
            <CardTitle>{t('sites:overview.dangerTitle')}</CardTitle>
            <CardDescription>{t('sites:overview.dangerDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
              <Trash2 className="mr-2 h-4 w-4" />
              {t('sites:overview.delete')}
            </Button>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={managedConfirm !== null}
        onOpenChange={(open) => !open && setManagedConfirm(null)}
        title={
          managedConfirm
            ? t('sites:overview.managedConfirmOn.title')
            : t('sites:overview.managedConfirmOff.title')
        }
        description={
          managedConfirm
            ? t('sites:overview.managedConfirmOn.description', { name: site.name })
            : t('sites:overview.managedConfirmOff.description', { name: site.name })
        }
        confirmLabel={
          managedConfirm
            ? t('sites:overview.managedConfirmOn.confirm')
            : t('sites:overview.managedConfirmOff.confirm')
        }
        onConfirm={confirmManaged}
        isLoading={isSavingConfig}
      />

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={t('sites:overview.deleteConfirm.title')}
        description={t('sites:overview.deleteConfirm.description', { name: site.name })}
        confirmLabel={t('sites:overview.deleteConfirm.confirm')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}

export function SiteOverviewPage() {
  return <SiteDetailShell>{(site) => <SiteOverview site={site} />}</SiteDetailShell>
}
