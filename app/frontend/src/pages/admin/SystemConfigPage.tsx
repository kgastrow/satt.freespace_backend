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
import { ShieldCheck } from 'lucide-react'
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  useGetSystemConfigsQuery,
  useCreateSystemConfigMutation,
  useUpdateSystemConfigMutation,
  useDeleteSystemConfigMutation,
  type SystemConfig,
} from '@/features/systemConfig/systemConfigApi'

export function SystemConfigPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [page, setPage] = useState(1)
  const pageSize = 50

  const createSchema = z.object({
    key: z
      .string()
      .min(1, t('admin:systemConfig.validation.keyRequired'))
      .max(100, t('admin:systemConfig.validation.keyTooLong'))
      .regex(/^[a-z0-9._-]+$/, t('admin:systemConfig.validation.keyFormat')),
    value: z.string().min(1, t('admin:systemConfig.validation.valueRequired')),
    description: z.string().optional(),
  })

  const editSchema = z.object({
    value: z.string().min(1, t('admin:systemConfig.validation.valueRequired')),
    description: z.string().optional(),
  })

  type CreateFormData = z.infer<typeof createSchema>
  type EditFormData = z.infer<typeof editSchema>

  const { data, isLoading } = useGetSystemConfigsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createConfig, { isLoading: isCreating }] = useCreateSystemConfigMutation()
  const [updateConfig, { isLoading: isUpdating }] = useUpdateSystemConfigMutation()
  const [deleteConfig, { isLoading: isDeleting }] = useDeleteSystemConfigMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<SystemConfig | null>(null)
  const [deletingConfig, setDeletingConfig] = useState<SystemConfig | null>(null)

  const createForm = useForm<CreateFormData>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      key: '',
      value: '',
      description: '',
    },
  })

  const editForm = useForm<EditFormData>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      value: '',
      description: '',
    },
  })

  const handleCreate = async (data: CreateFormData) => {
    try {
      // Try to parse as JSON, otherwise use as string
      let parsedValue: unknown = data.value
      try {
        parsedValue = JSON.parse(data.value)
      } catch {
        // Keep as string if not valid JSON
      }

      await createConfig({
        key: data.key,
        value: parsedValue,
        description: data.description || null,
      }).unwrap()
      toast.success(t('admin:systemConfig.toast.createSuccess'))
      setIsCreateOpen(false)
      createForm.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:systemConfig.toast.createError'))
    }
  }

  const handleEdit = async (data: EditFormData) => {
    if (!editingConfig) return
    try {
      // Try to parse as JSON, otherwise use as string
      let parsedValue: unknown = data.value
      try {
        parsedValue = JSON.parse(data.value)
      } catch {
        // Keep as string if not valid JSON
      }

      await updateConfig({
        key: editingConfig.key,
        body: {
          value: parsedValue,
          description: data.description || null,
        },
      }).unwrap()
      toast.success(t('admin:systemConfig.toast.updateSuccess'))
      setEditingConfig(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:systemConfig.toast.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!deletingConfig) return
    try {
      await deleteConfig(deletingConfig.key).unwrap()
      toast.success(t('admin:systemConfig.toast.deleteSuccess'))
      setDeletingConfig(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:systemConfig.toast.deleteError'))
    }
  }

  const openEditDialog = (config: SystemConfig) => {
    editForm.reset({
      value:
        typeof config.value === 'string' ? config.value : JSON.stringify(config.value, null, 2),
      description: config.description || '',
    })
    setEditingConfig(config)
  }

  const openCreateDialog = () => {
    createForm.reset({
      key: '',
      value: '',
      description: '',
    })
    setIsCreateOpen(true)
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-'
    return new Date(dateString).toLocaleString()
  }

  const formatValue = (value: unknown) => {
    if (typeof value === 'string') {
      return value.length > 50 ? value.substring(0, 50) + '...' : value
    }
    const jsonStr = JSON.stringify(value)
    return jsonStr.length > 50 ? jsonStr.substring(0, 50) + '...' : jsonStr
  }

  const getValueType = (value: unknown): string => {
    if (value === null) return 'null'
    if (Array.isArray(value)) return 'array'
    return typeof value
  }

  const columns: Column<SystemConfig>[] = [
    {
      key: 'key',
      header: t('admin:systemConfig.table.key'),
      cell: (config) => (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <code className="text-sm font-medium">{config.key}</code>
            </TooltipTrigger>
            {config.description && (
              <TooltipContent>
                <p className="max-w-xs">{config.description}</p>
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      ),
    },
    {
      key: 'value',
      header: t('admin:systemConfig.table.value'),
      cell: (config) => (
        <div className="flex items-center gap-2">
          {config.is_sensitive && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <ShieldCheck className="h-4 w-4 text-amber-500 shrink-0" />
                </TooltipTrigger>
                <TooltipContent>
                  <p>{t('admin:systemConfig.table.sensitive')}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
          <Badge variant="outline" className="text-xs">
            {getValueType(config.value)}
          </Badge>
          <code className="text-sm text-muted-foreground">{formatValue(config.value)}</code>
        </div>
      ),
    },
    {
      key: 'updated',
      header: t('admin:systemConfig.table.lastUpdated'),
      cell: (config) => (
        <div className="text-sm">
          <div>{formatDate(config.updated_time || config.created_time)}</div>
          {config.updated_by_email && (
            <div className="text-muted-foreground text-xs">{config.updated_by_email}</div>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (config) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(config)}>
              {t('admin:systemConfig.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => setDeletingConfig(config)}
              className="text-destructive"
            >
              {t('admin:systemConfig.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('admin:systemConfig.pageTitle')}
        description={t('admin:systemConfig.pageDescription')}
      >
        <Button onClick={openCreateDialog}>{t('admin:systemConfig.createButton')}</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('admin:systemConfig.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Config Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('admin:systemConfig.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('admin:systemConfig.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...createForm}>
            <form onSubmit={createForm.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={createForm.control}
                name="key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:systemConfig.createDialog.key')}</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder={t('admin:systemConfig.createDialog.keyPlaceholder')} />
                    </FormControl>
                    <FormDescription>
                      {t('admin:systemConfig.createDialog.keyDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={createForm.control}
                name="value"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:systemConfig.createDialog.value')}</FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        rows={4}
                        placeholder={t('admin:systemConfig.createDialog.valuePlaceholder')}
                        className="font-mono text-sm"
                      />
                    </FormControl>
                    <FormDescription>
                      {t('admin:systemConfig.createDialog.valueDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={createForm.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:systemConfig.createDialog.description')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                  {t('admin:systemConfig.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating
                    ? t('admin:systemConfig.createDialog.creating')
                    : t('admin:systemConfig.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Config Dialog */}
      <Dialog open={!!editingConfig} onOpenChange={() => setEditingConfig(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('admin:systemConfig.editDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('admin:systemConfig.editDialog.description', { key: editingConfig?.key })}
            </DialogDescription>
          </DialogHeader>
          <Form {...editForm}>
            <form onSubmit={editForm.handleSubmit(handleEdit)} className="space-y-4">
              <div>
                <FormLabel>{t('admin:systemConfig.editDialog.key')}</FormLabel>
                <code className="block mt-1 text-sm bg-muted p-2 rounded">{editingConfig?.key}</code>
              </div>
              <FormField
                control={editForm.control}
                name="value"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:systemConfig.editDialog.value')}</FormLabel>
                    <FormControl>
                      <Textarea
                        {...field}
                        rows={6}
                        className="font-mono text-sm"
                      />
                    </FormControl>
                    <FormDescription>
                      {t('admin:systemConfig.editDialog.valueDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={editForm.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('admin:systemConfig.editDialog.description')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} rows={2} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={() => setEditingConfig(null)}>
                  {t('admin:systemConfig.editDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating
                    ? t('admin:systemConfig.editDialog.saving')
                    : t('admin:systemConfig.editDialog.save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingConfig}
        onOpenChange={() => setDeletingConfig(null)}
        title={t('admin:systemConfig.deleteDialog.title')}
        description={t('admin:systemConfig.deleteDialog.description', { key: deletingConfig?.key })}
        confirmLabel={t('admin:systemConfig.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
