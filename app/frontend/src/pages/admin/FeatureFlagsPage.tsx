import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FeatureFlagForm } from '@/components/feature-flags/FeatureFlagForm'
import { FeatureFlagOverrideDialog } from '@/components/feature-flags/FeatureFlagOverrideDialog'
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
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  useGetFeatureFlagsQuery,
  useCreateFeatureFlagMutation,
  useUpdateFeatureFlagMutation,
  useDeleteFeatureFlagMutation,
  type FeatureFlag,
  type CreateFeatureFlagRequest,
  type UpdateFeatureFlagRequest,
} from '@/features/featureFlags/featureFlagsApi'

export function FeatureFlagsPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data, isLoading } = useGetFeatureFlagsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createFeatureFlag, { isLoading: isCreating }] =
    useCreateFeatureFlagMutation()
  const [updateFeatureFlag, { isLoading: isUpdating }] =
    useUpdateFeatureFlagMutation()
  const [deleteFeatureFlag, { isLoading: isDeleting }] =
    useDeleteFeatureFlagMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingFlag, setEditingFlag] = useState<FeatureFlag | null>(null)
  const [deletingFlag, setDeletingFlag] = useState<FeatureFlag | null>(null)
  const [overrideFlag, setOverrideFlag] = useState<FeatureFlag | null>(null)

  const handleCreate = async (data: CreateFeatureFlagRequest) => {
    try {
      await createFeatureFlag(data).unwrap()
      toast.success(t('featureFlags.toast.createSuccess'))
      setIsCreateOpen(false)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('featureFlags.toast.createError'))
      throw error
    }
  }

  const handleUpdate = async (data: UpdateFeatureFlagRequest) => {
    if (!editingFlag) return

    try {
      await updateFeatureFlag({ id: editingFlag.id, data }).unwrap()
      toast.success(t('featureFlags.toast.updateSuccess'))
      setEditingFlag(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('featureFlags.toast.updateError'))
      throw error
    }
  }

  const handleDelete = async () => {
    if (!deletingFlag) return

    try {
      await deleteFeatureFlag(deletingFlag.id).unwrap()
      toast.success(t('featureFlags.toast.deleteSuccess'))
      setDeletingFlag(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('featureFlags.toast.deleteError'))
    }
  }

  const columns: Column<FeatureFlag>[] = [
    {
      key: 'key',
      header: t('featureFlags.table.key'),
      cell: (flag) => <code className="text-sm">{flag.key}</code>,
    },
    {
      key: 'name',
      header: t('featureFlags.table.name'),
      cell: (flag) => flag.name,
    },
    {
      key: 'description',
      header: t('featureFlags.table.description'),
      cell: (flag) => (
        <div className="max-w-[300px] truncate">
          {flag.description || t('featureFlags.table.noDescription')}
        </div>
      ),
    },
    {
      key: 'default_enabled',
      header: t('featureFlags.table.defaultEnabled'),
      cell: (flag) => (
        <Badge variant={flag.default_enabled ? 'default' : 'secondary'}>
          {flag.default_enabled
            ? t('featureFlags.table.enabled')
            : t('featureFlags.table.disabled')}
        </Badge>
      ),
    },
    {
      key: 'overrides',
      header: t('featureFlags.table.overrides'),
      cell: (flag) => {
        const overrides = flag.overrides || []
        if (overrides.length === 0) {
          return <span className="text-muted-foreground">—</span>
        }
        return (
          <div className="flex flex-wrap gap-1 max-w-[250px]">
            {overrides.map((override) => (
              <Badge
                key={override.organization_id}
                variant={override.enabled ? 'default' : 'secondary'}
                className="text-xs"
              >
                {override.organization_name}
              </Badge>
            ))}
          </div>
        )
      },
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[100px]',
      cell: (flag) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setEditingFlag(flag)}>
              {t('featureFlags.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setOverrideFlag(flag)}>
              {t('featureFlags.actions.overrides')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingFlag(flag)}
              className="text-destructive"
            >
              {t('featureFlags.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('featureFlags.pageTitle')}
        description={t('featureFlags.pageDescription')}
      >
        <Button onClick={() => setIsCreateOpen(true)}>
          {t('featureFlags.createButton')}
        </Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('featureFlags.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Feature Flag Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('featureFlags.createDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('featureFlags.createDialog.description')}
            </DialogDescription>
          </DialogHeader>
          <FeatureFlagForm
            onSubmit={handleCreate}
            onCancel={() => setIsCreateOpen(false)}
            isSubmitting={isCreating}
          />
        </DialogContent>
      </Dialog>

      {/* Edit Feature Flag Dialog */}
      <Dialog open={!!editingFlag} onOpenChange={() => setEditingFlag(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('featureFlags.editDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('featureFlags.editDialog.description')}
            </DialogDescription>
          </DialogHeader>
          {editingFlag && (
            <FeatureFlagForm
              initialData={editingFlag}
              onSubmit={handleUpdate}
              onCancel={() => setEditingFlag(null)}
              isSubmitting={isUpdating}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingFlag}
        onOpenChange={() => setDeletingFlag(null)}
        title={t('featureFlags.deleteDialog.title')}
        description={t(
          'featureFlags.deleteDialog.description',
          { name: deletingFlag?.name }
        )}
        confirmLabel={t('featureFlags.deleteDialog.confirm')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />

      {/* Override Management Dialog */}
      {overrideFlag && (
        <FeatureFlagOverrideDialog
          flagId={overrideFlag.id}
          flagName={overrideFlag.name}
          open={!!overrideFlag}
          onOpenChange={() => setOverrideFlag(null)}
        />
      )}
    </div>
  )
}
