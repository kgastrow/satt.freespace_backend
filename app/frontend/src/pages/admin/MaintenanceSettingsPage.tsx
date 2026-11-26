import { useTranslation } from 'react-i18next'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { Wrench, AlertCircle, Clock, Calendar, History } from 'lucide-react'
import {
  useGetMaintenanceConfigQuery,
  useUpdateMaintenanceMutation,
  useGetMaintenanceHistoryQuery,
} from '@/features/maintenance'
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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { getErrorMessage } from '@/types/api'
import type { MaintenanceHistoryItem } from '@/features/maintenance/maintenanceApi'

const createMaintenanceSchema = (t: (key: string) => string) =>
  z
    .object({
      enabled: z.boolean(),
      message: z.string().max(500, t('admin:maintenance.validation.messageMaxLength')),
      scheduled_start: z.string().optional(),
      scheduled_end: z.string().optional(),
      allow_super_admin: z.boolean(),
    })
    .refine(
      (data) => {
        if (data.scheduled_start && data.scheduled_end) {
          return new Date(data.scheduled_end) > new Date(data.scheduled_start)
        }
        return true
      },
      {
        message: t('admin:maintenance.validation.endAfterStart'),
        path: ['scheduled_end'],
      }
    )
    .refine(
      (data) => {
        if (data.scheduled_start && !data.enabled) {
          return new Date(data.scheduled_start) > new Date()
        }
        return true
      },
      {
        message: t('admin:maintenance.validation.startInFuture'),
        path: ['scheduled_start'],
      }
    )

type MaintenanceFormData = z.infer<ReturnType<typeof createMaintenanceSchema>>

function getStatusBadgeVariant(
  status: MaintenanceHistoryItem['status']
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'active':
      return 'destructive'
    case 'completed':
      return 'default'
    case 'scheduled':
      return 'secondary'
    case 'cancelled':
      return 'outline'
    default:
      return 'default'
  }
}

function formatDateTime(dateString: string | null): string {
  if (!dateString) return '-'
  return new Date(dateString).toLocaleString()
}

function getUserDisplayName(user: MaintenanceHistoryItem['started_by']): string {
  if (!user) return '-'
  if (user.first_name || user.last_name) {
    return `${user.first_name || ''} ${user.last_name || ''}`.trim()
  }
  return user.email
}

/**
 * Convert a UTC ISO string to a local datetime-local input value
 * datetime-local expects format: "YYYY-MM-DDTHH:mm"
 */
function utcToLocalDatetimeInput(utcString: string): string {
  const date = new Date(utcString)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
}

/**
 * Convert a local datetime-local input value to a UTC ISO string
 */
function localDatetimeInputToUtc(localString: string): string {
  return new Date(localString).toISOString()
}

export function MaintenanceSettingsPage() {
  const { t } = useTranslation(['admin', 'common', 'backend'])

  const {
    data: config,
    isLoading: isLoadingConfig,
    error: configError,
  } = useGetMaintenanceConfigQuery()

  const [updateMaintenance, { isLoading: isUpdating }] = useUpdateMaintenanceMutation()

  const { data: historyData, isLoading: isLoadingHistory } = useGetMaintenanceHistoryQuery({
    limit: 10,
    offset: 0,
  })

  const maintenanceSchema = createMaintenanceSchema(t)

  const form = useForm<MaintenanceFormData>({
    resolver: zodResolver(maintenanceSchema),
    defaultValues: {
      enabled: false,
      message: '',
      scheduled_start: '',
      scheduled_end: '',
      allow_super_admin: true,
    },
    values: config
      ? {
          enabled: config.enabled,
          message: config.message || '',
          scheduled_start: config.scheduled_start
            ? utcToLocalDatetimeInput(config.scheduled_start)
            : '',
          scheduled_end: config.scheduled_end
            ? utcToLocalDatetimeInput(config.scheduled_end)
            : '',
          allow_super_admin: config.allow_super_admin,
        }
      : undefined,
  })

  const onSubmit = async (data: MaintenanceFormData) => {
    try {
      await updateMaintenance({
        enabled: data.enabled,
        message: data.message || null,
        scheduled_start: data.scheduled_start ? localDatetimeInputToUtc(data.scheduled_start) : null,
        scheduled_end: data.scheduled_end ? localDatetimeInputToUtc(data.scheduled_end) : null,
        allow_super_admin: data.allow_super_admin,
      }).unwrap()
      toast.success(t('admin:maintenance.updateSuccess'))
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const enabled = useWatch({ control: form.control, name: 'enabled' })

  if (isLoadingConfig) {
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

  if (configError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {t('admin:maintenance.pageTitle')}
          </h1>
          <p className="text-muted-foreground">{t('admin:maintenance.pageDescription')}</p>
        </div>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('common:error')}</AlertTitle>
          <AlertDescription>{getErrorMessage(configError, t)}</AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!config) {
    return null
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">
          {t('admin:maintenance.pageTitle')}
        </h1>
        <p className="text-muted-foreground">{t('admin:maintenance.pageDescription')}</p>
      </div>

      {config.enabled && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('admin:maintenance.activeAlert.title')}</AlertTitle>
          <AlertDescription>
            {t('admin:maintenance.activeAlert.description')}
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5" />
            {t('admin:maintenance.settingsCard.title')}
          </CardTitle>
          <CardDescription>{t('admin:maintenance.settingsCard.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              <FormField
                control={form.control}
                name="enabled"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">
                        {t('admin:maintenance.fields.enabled.label')}
                      </FormLabel>
                      <FormDescription>
                        {t('admin:maintenance.fields.enabled.description')}
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
                name="message"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:maintenance.fields.message.label')}</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder={t('admin:maintenance.fields.message.placeholder')}
                        className="resize-none"
                        rows={4}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {t('admin:maintenance.fields.message.description')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="space-y-4 rounded-lg border p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-5 w-5" />
                    <h3 className="font-medium">{t('admin:maintenance.schedulingSection')}</h3>
                  </div>
                  {(form.watch('scheduled_start') || form.watch('scheduled_end')) && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        form.setValue('scheduled_start', '')
                        form.setValue('scheduled_end', '')
                      }}
                    >
                      {t('admin:maintenance.actions.clearSchedule')}
                    </Button>
                  )}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="scheduled_start"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {t('admin:maintenance.fields.scheduledStart.label')}
                        </FormLabel>
                        <FormControl>
                          <Input type="datetime-local" {...field} disabled={enabled} />
                        </FormControl>
                        <FormDescription>
                          {t('admin:maintenance.fields.scheduledStart.description')}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="scheduled_end"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {t('admin:maintenance.fields.scheduledEnd.label')}
                        </FormLabel>
                        <FormControl>
                          <Input type="datetime-local" {...field} disabled={enabled} />
                        </FormControl>
                        <FormDescription>
                          {t('admin:maintenance.fields.scheduledEnd.description')}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </div>

              <FormField
                control={form.control}
                name="allow_super_admin"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">
                        {t('admin:maintenance.fields.allowSuperAdmin.label')}
                      </FormLabel>
                      <FormDescription>
                        {t('admin:maintenance.fields.allowSuperAdmin.description')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <Button type="submit" disabled={isUpdating}>
                {isUpdating
                  ? t('admin:maintenance.actions.saving')
                  : t('admin:maintenance.actions.save')}
              </Button>
            </form>
          </Form>
        </CardContent>
      </Card>

      {config.scheduled_start && !config.enabled && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              {t('admin:maintenance.scheduledCard.title')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">
                  {t('admin:maintenance.scheduledCard.startTime')}
                </span>
                <span className="font-medium">
                  {new Date(config.scheduled_start).toLocaleString()}
                </span>
              </div>
              {config.scheduled_end && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">
                    {t('admin:maintenance.scheduledCard.endTime')}
                  </span>
                  <span className="font-medium">
                    {new Date(config.scheduled_end).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <History className="h-5 w-5" />
            {t('admin:maintenance.historyCard.title')}
          </CardTitle>
          <CardDescription>{t('admin:maintenance.historyCard.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingHistory ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : historyData?.items && historyData.items.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('admin:maintenance.history.status')}</TableHead>
                  <TableHead>{t('admin:maintenance.history.scheduledStart')}</TableHead>
                  <TableHead>{t('admin:maintenance.history.actualStart')}</TableHead>
                  <TableHead>{t('admin:maintenance.history.actualEnd')}</TableHead>
                  <TableHead>{t('admin:maintenance.history.startedBy')}</TableHead>
                  <TableHead>{t('admin:maintenance.history.endedBy')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {historyData.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <Badge variant={getStatusBadgeVariant(item.status)}>
                        {t(`admin:maintenance.history.statuses.${item.status}`)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDateTime(item.scheduled_start)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDateTime(item.actual_start)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {formatDateTime(item.actual_end)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {getUserDisplayName(item.started_by)}
                    </TableCell>
                    <TableCell className="text-sm">
                      {getUserDisplayName(item.ended_by)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">
              {t('admin:maintenance.history.noHistory')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
