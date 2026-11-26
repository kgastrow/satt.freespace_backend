import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  useGetCronJobsQuery,
  useCreateCronJobMutation,
  useUpdateCronJobMutation,
  useDeleteCronJobMutation,
  useToggleCronJobMutation,
  useTriggerCronJobMutation,
  useGetCronJobExecutionsQuery,
  useGetCronJobConfigQuery,
  useUpdateCronJobConfigMutation,
} from '@/features/cronJobs/cronJobsApi'
import type { CronJob, CronJobConfigKey } from '@/types/cron-job'

export function CronJobsPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [page, setPage] = useState(1)
  const pageSize = 10

  const cronJobSchema = z.object({
    name: z.string().min(1, t('admin:cronJobs.validation.nameRequired')),
    description: z.string().optional(),
    code: z
      .string()
      .min(1, t('admin:cronJobs.validation.codeRequired'))
      .regex(/^[a-z0-9_]+$/, t('admin:cronJobs.validation.codeFormat')),
    schedule_expression: z
      .string()
      .min(1, t('admin:cronJobs.validation.scheduleExpressionRequired'))
      .regex(/^(\*|[0-5]?\d)(\s+(\*|[0-5]?\d)){4}$/, t('admin:cronJobs.validation.scheduleExpressionFormat')),
    is_active: z.boolean(),
    is_enabled_by_default_for_new_orgs: z.boolean(),
    is_platform_wide: z.boolean(),
  })

  type CronJobFormData = z.infer<typeof cronJobSchema>

  const { data, isLoading } = useGetCronJobsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createCronJob, { isLoading: isCreating }] = useCreateCronJobMutation()
  const [updateCronJob, { isLoading: isUpdating }] = useUpdateCronJobMutation()
  const [deleteCronJob, { isLoading: isDeleting }] = useDeleteCronJobMutation()
  const [toggleCronJob, { isLoading: isToggling }] = useToggleCronJobMutation()
  const [triggerCronJob, { isLoading: isTriggering }] = useTriggerCronJobMutation()
  const [updateCronJobConfig, { isLoading: isUpdatingConfig }] = useUpdateCronJobConfigMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingJob, setEditingJob] = useState<CronJob | null>(null)
  const [deletingJob, setDeletingJob] = useState<CronJob | null>(null)
  const [triggeringJob, setTriggeringJob] = useState<CronJob | null>(null)
  const [viewingExecutions, setViewingExecutions] = useState<CronJob | null>(null)

  const form = useForm<CronJobFormData>({
    resolver: zodResolver(cronJobSchema),
    defaultValues: {
      name: '',
      description: '',
      code: '',
      schedule_expression: '',
      is_active: true,
      is_enabled_by_default_for_new_orgs: false,
      is_platform_wide: true,
    },
  })

  const { data: executionsData } = useGetCronJobExecutionsQuery(
    {
      id: viewingExecutions?.id || '',
      params: { limit: 10, offset: 0 },
    },
    { skip: !viewingExecutions }
  )

  // Fetch config for the editing job
  const { data: configData } = useGetCronJobConfigQuery(editingJob?.id || '', {
    skip: !editingJob,
  })

  const handleCreate = async (data: CronJobFormData) => {
    try {
      await createCronJob({
        name: data.name,
        description: data.description || null,
        code: data.code,
        schedule_expression: data.schedule_expression,
        is_active: data.is_active,
        is_enabled_by_default_for_new_orgs: data.is_enabled_by_default_for_new_orgs,
        is_platform_wide: data.is_platform_wide,
      }).unwrap()
      toast.success(t('admin:cronJobs.toast.createSuccess'))
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.createError'))
    }
  }

  const handleEdit = async (data: CronJobFormData) => {
    if (!editingJob) return
    try {
      await updateCronJob({
        id: editingJob.id,
        body: {
          name: data.name,
          description: data.description || null,
          schedule_expression: data.schedule_expression,
          is_active: data.is_active,
          is_enabled_by_default_for_new_orgs: data.is_enabled_by_default_for_new_orgs,
        },
      }).unwrap()
      toast.success(t('admin:cronJobs.toast.updateSuccess'))
      setEditingJob(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!deletingJob) return
    try {
      await deleteCronJob(deletingJob.id).unwrap()
      toast.success(t('admin:cronJobs.toast.deleteSuccess'))
      setDeletingJob(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.deleteError'))
    }
  }

  const handleToggle = async (job: CronJob) => {
    try {
      await toggleCronJob({
        id: job.id,
        body: { is_active: !job.is_active },
      }).unwrap()
      toast.success(job.is_active ? t('admin:cronJobs.toast.deactivateSuccess') : t('admin:cronJobs.toast.activateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.toggleError'))
    }
  }

  const handleTrigger = async () => {
    if (!triggeringJob) return
    try {
      const result = await triggerCronJob(triggeringJob.id).unwrap()
      toast.success(result.message || t('admin:cronJobs.toast.triggerSuccess'))
      setTriggeringJob(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.triggerError'))
    }
  }

  const handleConfigUpdate = async (configKey: CronJobConfigKey, value: string) => {
    if (!editingJob) return
    try {
      await updateCronJobConfig({
        id: editingJob.id,
        body: { key: configKey.key, value },
      }).unwrap()
      toast.success(t('admin:cronJobs.toast.configUpdateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:cronJobs.toast.configUpdateError'))
    }
  }

  const openEditDialog = (job: CronJob) => {
    form.reset({
      name: job.name,
      description: job.description || '',
      code: job.code,
      schedule_expression: job.schedule_expression,
      is_active: job.is_active,
      is_enabled_by_default_for_new_orgs: job.is_enabled_by_default_for_new_orgs,
      is_platform_wide: job.is_platform_wide,
    })
    setEditingJob(job)
  }

  const openCreateDialog = () => {
    form.reset({
      name: '',
      description: '',
      code: '',
      schedule_expression: '',
      is_active: true,
      is_enabled_by_default_for_new_orgs: false,
      is_platform_wide: true,
    })
    setIsCreateOpen(true)
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return t('admin:cronJobs.status.never')
    return new Date(dateString).toLocaleString()
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'success':
        return <Badge variant="default">{t('admin:cronJobs.status.success')}</Badge>
      case 'error':
        return <Badge variant="destructive">{t('admin:cronJobs.status.error')}</Badge>
      case 'running':
        return <Badge>{t('admin:cronJobs.status.running')}</Badge>
      case 'pending':
        return <Badge variant="secondary">{t('admin:cronJobs.status.pending')}</Badge>
      default:
        return <Badge variant="secondary">{status}</Badge>
    }
  }

  const formatDuration = (ms: number | null | undefined) => {
    if (ms === null || ms === undefined) return '-'
    if (ms < 1000) return `${Math.round(ms)}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  }

  const formatFailureRate = (rate: number) => {
    if (rate === 0) return '0%'
    return `${rate.toFixed(1)}%`
  }

  const columns: Column<CronJob>[] = [
    {
      key: 'name',
      header: t('admin:cronJobs.table.name'),
      cell: (job) => (
        <div className="min-w-0 max-w-[250px]">
          <div className="font-medium truncate">{job.name}</div>
          {job.description && (
            <div className="text-sm text-muted-foreground break-words whitespace-normal">{job.description}</div>
          )}
        </div>
      ),
    },
    {
      key: 'code',
      header: t('admin:cronJobs.table.code'),
      cell: (job) => <code className="text-sm">{job.code}</code>,
    },
    {
      key: 'schedule',
      header: t('admin:cronJobs.table.schedule'),
      cell: (job) => (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <code className="text-sm">{job.schedule_expression}</code>
            </TooltipTrigger>
            <TooltipContent>
              <p>{t('admin:cronJobs.table.tooltipCronExpression')}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ),
    },
    {
      key: 'executions_24h',
      header: t('admin:cronJobs.table.executions24h'),
      cell: (job) => (
        <div className="text-sm tabular-nums">{job.executions_24h ?? 0}</div>
      ),
    },
    {
      key: 'failures_24h',
      header: t('admin:cronJobs.table.failures24h'),
      cell: (job) => (
        <div className="text-sm tabular-nums">
          {(job.failures_24h ?? 0) > 0 ? (
            <span className="text-destructive">{job.failures_24h}</span>
          ) : (
            job.failures_24h ?? 0
          )}
        </div>
      ),
    },
    {
      key: 'failure_rate',
      header: t('admin:cronJobs.table.failureRate'),
      cell: (job) => (
        <div className="text-sm tabular-nums">
          {(job.failure_rate ?? 0) > 10 ? (
            <span className="text-destructive">{formatFailureRate(job.failure_rate ?? 0)}</span>
          ) : (
            formatFailureRate(job.failure_rate ?? 0)
          )}
        </div>
      ),
    },
    {
      key: 'avg_duration',
      header: t('admin:cronJobs.table.avgDuration'),
      cell: (job) => (
        <div className="text-sm tabular-nums">{formatDuration(job.avg_duration_ms)}</div>
      ),
    },
    {
      key: 'status',
      header: t('admin:cronJobs.table.status'),
      cell: (job) => (
        <Badge variant={job.is_active ? 'default' : 'secondary'}>
          {job.is_active ? t('admin:cronJobs.status.active') : t('admin:cronJobs.status.inactive')}
        </Badge>
      ),
    },
    {
      key: 'last_run',
      header: t('admin:cronJobs.table.lastRun'),
      cell: (job) => (
        <div className="text-sm">
          <div>{formatDate(job.last_run_time)}</div>
          {job.last_run_status && job.last_run_time && (
            <div className="mt-1">{getStatusBadge(job.last_run_status)}</div>
          )}
        </div>
      ),
    },
    {
      key: 'next_run',
      header: t('admin:cronJobs.table.nextRun'),
      cell: (job) => <div className="text-sm">{formatDate(job.next_run_time)}</div>,
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (job) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(job)}>
              {t('admin:cronJobs.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleToggle(job)} disabled={isToggling}>
              {job.is_active ? t('admin:cronJobs.actions.deactivate') : t('admin:cronJobs.actions.activate')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setTriggeringJob(job)}>
              {t('admin:cronJobs.actions.triggerManually')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setViewingExecutions(job)}>
              {t('admin:cronJobs.actions.viewHistory')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => setDeletingJob(job)}
              className="text-destructive"
            >
              {t('admin:cronJobs.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  // Config section component for the edit dialog
  const ConfigSection = ({ configKeys }: { configKeys: CronJobConfigKey[] }) => {
    const [editingValues, setEditingValues] = useState<Record<string, string>>({})

    const getDisplayValue = (configKey: CronJobConfigKey) => {
      if (editingValues[configKey.key] !== undefined) {
        return editingValues[configKey.key]
      }
      return configKey.current_value?.toString() || configKey.default?.toString() || ''
    }

    const handleValueChange = (key: string, value: string) => {
      setEditingValues((prev) => ({ ...prev, [key]: value }))
    }

    const handleSave = async (configKey: CronJobConfigKey) => {
      const value = editingValues[configKey.key]
      if (value === undefined) return
      await handleConfigUpdate(configKey, value)
      setEditingValues((prev) => {
        const newValues = { ...prev }
        delete newValues[configKey.key]
        return newValues
      })
    }

    if (configKeys.length === 0) {
      return (
        <div className="text-sm text-muted-foreground py-4 text-center">
          {t('admin:cronJobs.config.noConfig')}
        </div>
      )
    }

    return (
      <div className="space-y-4">
        {configKeys.map((configKey) => {
          const hasChanges = editingValues[configKey.key] !== undefined
          return (
            <div key={configKey.key} className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor={configKey.key}>{configKey.label}</Label>
                {hasChanges && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => handleSave(configKey)}
                    disabled={isUpdatingConfig}
                  >
                    {isUpdatingConfig ? t('admin:cronJobs.config.saving') : t('admin:cronJobs.config.save')}
                  </Button>
                )}
              </div>
              <Input
                id={configKey.key}
                type={configKey.value_type === 'integer' ? 'number' : 'text'}
                value={getDisplayValue(configKey)}
                onChange={(e) => handleValueChange(configKey.key, e.target.value)}
                min={configKey.min_value ?? undefined}
                max={configKey.max_value ?? undefined}
              />
              <p className="text-sm text-muted-foreground">{configKey.description}</p>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t('admin:cronJobs.pageTitle')} description={t('admin:cronJobs.pageDescription')}>
        <Button onClick={openCreateDialog}>{t('admin:cronJobs.createButton')}</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('admin:cronJobs.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Cron Job Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin:cronJobs.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('admin:cronJobs.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.createDialog.name')}</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.createDialog.description')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.createDialog.code')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('admin:cronJobs.createDialog.codePlaceholder')} />
                    </FormControl>
                    <FormDescription>
                      {t('admin:cronJobs.createDialog.codeDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="schedule_expression"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.createDialog.scheduleExpression')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('admin:cronJobs.createDialog.scheduleExpressionPlaceholder')} />
                    </FormControl>
                    <FormDescription>
                      {t('admin:cronJobs.createDialog.scheduleExpressionDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex gap-4">
                <FormField
                  control={form.control}
                  name="is_active"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('admin:cronJobs.createDialog.active')}</FormLabel>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="is_platform_wide"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('admin:cronJobs.createDialog.platformWide')}</FormLabel>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="is_enabled_by_default_for_new_orgs"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('admin:cronJobs.createDialog.enableForNewOrgs')}</FormLabel>
                    </FormItem>
                  )}
                />
              </div>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('admin:cronJobs.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? t('admin:cronJobs.createDialog.creating') : t('admin:cronJobs.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Cron Job Dialog */}
      <Dialog open={!!editingJob} onOpenChange={() => setEditingJob(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin:cronJobs.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('admin:cronJobs.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEdit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.editDialog.name')}</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.editDialog.description')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.editDialog.code')}</FormLabel>
                    <FormControl>
                      <Input {...field} disabled />
                    </FormControl>
                    <FormDescription>{t('admin:cronJobs.editDialog.codeDisabledDescription')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="schedule_expression"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:cronJobs.editDialog.scheduleExpression')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('admin:cronJobs.editDialog.scheduleExpressionPlaceholder')} />
                    </FormControl>
                    <FormDescription>
                      {t('admin:cronJobs.editDialog.scheduleExpressionDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex gap-4">
                <FormField
                  control={form.control}
                  name="is_active"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('admin:cronJobs.editDialog.active')}</FormLabel>
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="is_enabled_by_default_for_new_orgs"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('admin:cronJobs.editDialog.enableForNewOrgs')}</FormLabel>
                    </FormItem>
                  )}
                />
              </div>

              {/* Configuration Section */}
              {configData && (
                <>
                  <Separator className="my-4" />
                  <div>
                    <h4 className="text-sm font-medium mb-3">{t('admin:cronJobs.config.title')}</h4>
                    <p className="text-sm text-muted-foreground mb-4">{t('admin:cronJobs.config.description')}</p>
                    <ConfigSection configKeys={configData.config_keys} />
                  </div>
                </>
              )}

              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingJob(null)}
                >
                  {t('admin:cronJobs.editDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? t('admin:cronJobs.editDialog.saving') : t('admin:cronJobs.editDialog.save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingJob}
        onOpenChange={() => setDeletingJob(null)}
        title={t('admin:cronJobs.deleteDialog.title')}
        description={t('admin:cronJobs.deleteDialog.description', { name: deletingJob?.name })}
        confirmLabel={t('admin:cronJobs.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />

      {/* Trigger Confirmation */}
      <ConfirmDialog
        open={!!triggeringJob}
        onOpenChange={() => setTriggeringJob(null)}
        title={t('admin:cronJobs.triggerDialog.title')}
        description={t('admin:cronJobs.triggerDialog.description', { name: triggeringJob?.name })}
        confirmLabel={t('admin:cronJobs.triggerDialog.trigger')}
        onConfirm={handleTrigger}
        isLoading={isTriggering}
      />

      {/* Execution History Dialog */}
      <Dialog open={!!viewingExecutions} onOpenChange={() => setViewingExecutions(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin:cronJobs.executionHistoryDialog.title', { name: viewingExecutions?.name })}</DialogTitle>
            <DialogDescription>{t('admin:cronJobs.executionHistoryDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            {executionsData?.items && executionsData.items.length > 0 ? (
              executionsData.items.map((execution) => (
                <div
                  key={execution.id}
                  className="p-4 border rounded-lg space-y-2"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {getStatusBadge(execution.status)}
                      <span className="text-sm text-muted-foreground">
                        {formatDate(execution.started_at)}
                      </span>
                    </div>
                    {execution.completed_at && (
                      <span className="text-sm text-muted-foreground">
                        {t('admin:cronJobs.executionHistoryDialog.completedAt', { time: formatDate(execution.completed_at) })}
                      </span>
                    )}
                  </div>
                  {execution.error_message && (
                    <div className="text-sm text-destructive">
                      {t('admin:cronJobs.executionHistoryDialog.error', { message: execution.error_message })}
                    </div>
                  )}
                  {execution.result && (
                    <div className="text-sm">
                      <pre className="bg-muted p-2 rounded overflow-x-auto">
                        {JSON.stringify(execution.result, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              ))
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                {t('admin:cronJobs.executionHistoryDialog.noHistory')}
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
