import { useState } from 'react'
import { toast } from '@/lib/toast'
import { useTranslation } from 'react-i18next'
import { Plus, Trash2, Edit } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  useGetRateLimitsQuery,
  useCreateRateLimitMutation,
  useUpdateRateLimitMutation,
  useDeleteRateLimitMutation,
} from '@/features/apiKeys/rateLimitsApi'
import type { components } from '@/types/api-generated'

type RateLimitResponse = components['schemas']['RateLimitResponse']

export function ApiKeyRateLimitsPage() {
  const { t } = useTranslation('settings')
  const { data, isLoading, error } = useGetRateLimitsQuery()
  const rateLimits = data?.items
  const [createRateLimit, { isLoading: isCreating }] = useCreateRateLimitMutation()
  const [updateRateLimit, { isLoading: isUpdating }] = useUpdateRateLimitMutation()
  const [deleteRateLimit, { isLoading: isDeleting }] = useDeleteRateLimitMutation()

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [selectedRateLimit, setSelectedRateLimit] = useState<RateLimitResponse | null>(null)

  const [createForm, setCreateForm] = useState({
    permission_code: '',
    requests_per_minute: 60,
    burst_limit: 100,
  })

  const [editForm, setEditForm] = useState({
    requests_per_minute: 60,
    burst_limit: 100,
  })

  const handleCreate = async () => {
    if (!createForm.permission_code.trim()) {
      toast.error(t('rateLimits.messages.permissionCodeRequired'))
      return
    }

    if (createForm.requests_per_minute <= 0 || createForm.burst_limit <= 0) {
      toast.error(t('rateLimits.messages.invalidValues'))
      return
    }

    try {
      await createRateLimit({
        permission_code: createForm.permission_code,
        requests_per_minute: createForm.requests_per_minute,
        burst_limit: createForm.burst_limit,
      }).unwrap()

      setShowCreateDialog(false)
      setCreateForm({ permission_code: '', requests_per_minute: 60, burst_limit: 100 })
      toast.success(t('rateLimits.messages.createSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('rateLimits.messages.createError'))
    }
  }

  const handleUpdate = async () => {
    if (!selectedRateLimit) return

    if (editForm.requests_per_minute <= 0 || editForm.burst_limit <= 0) {
      toast.error(t('rateLimits.messages.invalidValues'))
      return
    }

    try {
      await updateRateLimit({
        id: selectedRateLimit.id,
        data: {
          requests_per_minute: editForm.requests_per_minute,
          burst_limit: editForm.burst_limit,
        },
      }).unwrap()

      setShowEditDialog(false)
      setSelectedRateLimit(null)
      toast.success(t('rateLimits.messages.updateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('rateLimits.messages.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!selectedRateLimit) return

    try {
      await deleteRateLimit(selectedRateLimit.id).unwrap()
      setShowDeleteConfirm(false)
      setSelectedRateLimit(null)
      toast.success(t('rateLimits.messages.deleteSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('rateLimits.messages.deleteError'))
    }
  }

  const openEditDialog = (rateLimit: RateLimitResponse) => {
    setSelectedRateLimit(rateLimit)
    setEditForm({
      requests_per_minute: rateLimit.requests_per_minute,
      burst_limit: rateLimit.burst_limit,
    })
    setShowEditDialog(true)
  }

  const openDeleteDialog = (rateLimit: RateLimitResponse) => {
    setSelectedRateLimit(rateLimit)
    setShowDeleteConfirm(true)
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-64 mb-2" />
          <Skeleton className="h-4 w-96 mb-6" />
        </div>
        <Card>
          <CardHeader>
            <Skeleton className="h-6 w-48" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-64 w-full" />
          </CardContent>
        </Card>
      </div>
    )
  }

  if (error) {
    const apiError = error as { status?: number; data?: { detail?: string } }
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('rateLimits.title')}
          description={t('rateLimits.description')}
        />
        <Alert variant="destructive">
          <AlertTitle>{t('rateLimits.alerts.error.title')}</AlertTitle>
          <AlertDescription>
            {apiError.data?.detail || t('rateLimits.alerts.error.description')}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('rateLimits.title')}
        description={t('rateLimits.description')}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle>{t('rateLimits.sections.list.title')}</CardTitle>
            <CardDescription className="mt-1.5">
              {t('rateLimits.sections.list.description')}
            </CardDescription>
          </div>
          <Button onClick={() => setShowCreateDialog(true)}>
            <Plus className="h-4 w-4 mr-2" />
            {t('rateLimits.buttons.create')}
          </Button>
        </CardHeader>
        <CardContent>
          {!rateLimits || rateLimits.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <p>{t('rateLimits.table.empty')}</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('rateLimits.table.permissionCode')}</TableHead>
                  <TableHead>{t('rateLimits.table.requestsPerMinute')}</TableHead>
                  <TableHead>{t('rateLimits.table.burstLimit')}</TableHead>
                  <TableHead>{t('rateLimits.table.updated')}</TableHead>
                  <TableHead className="text-right">{t('rateLimits.table.actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rateLimits.map((rateLimit: RateLimitResponse) => (
                  <TableRow key={rateLimit.id}>
                    <TableCell className="font-medium">
                      <code className="rounded bg-muted px-2 py-1 text-sm">
                        {rateLimit.permission_code}
                      </code>
                    </TableCell>
                    <TableCell>{rateLimit.requests_per_minute}</TableCell>
                    <TableCell>{rateLimit.burst_limit}</TableCell>
                    <TableCell>
                      {new Date(rateLimit.updated_time).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      })}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openEditDialog(rateLimit)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openDeleteDialog(rateLimit)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create Rate Limit Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('rateLimits.dialogs.create.title')}</DialogTitle>
            <DialogDescription>
              {t('rateLimits.dialogs.create.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="permission_code">{t('rateLimits.fields.permissionCode')}</Label>
              <Input
                id="permission_code"
                value={createForm.permission_code}
                onChange={(e) => setCreateForm({ ...createForm, permission_code: e.target.value })}
                placeholder={t('rateLimits.fields.permissionCodePlaceholder')}
              />
              <p className="text-sm text-muted-foreground mt-1">
                {t('rateLimits.fields.permissionCodeHelp')}
              </p>
            </div>
            <div>
              <Label htmlFor="requests_per_minute">{t('rateLimits.fields.requestsPerMinute')}</Label>
              <Input
                id="requests_per_minute"
                type="number"
                min="1"
                value={createForm.requests_per_minute}
                onChange={(e) => setCreateForm({ ...createForm, requests_per_minute: parseInt(e.target.value) || 1 })}
              />
              <p className="text-sm text-muted-foreground mt-1">
                {t('rateLimits.fields.requestsPerMinuteHelp')}
              </p>
            </div>
            <div>
              <Label htmlFor="burst_limit">{t('rateLimits.fields.burstLimit')}</Label>
              <Input
                id="burst_limit"
                type="number"
                min="1"
                value={createForm.burst_limit}
                onChange={(e) => setCreateForm({ ...createForm, burst_limit: parseInt(e.target.value) || 1 })}
              />
              <p className="text-sm text-muted-foreground mt-1">
                {t('rateLimits.fields.burstLimitHelp')}
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              {t('rateLimits.buttons.cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={isCreating}>
              {isCreating ? t('rateLimits.buttons.creating') : t('rateLimits.buttons.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Rate Limit Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('rateLimits.dialogs.edit.title')}</DialogTitle>
            <DialogDescription>
              {t('rateLimits.dialogs.edit.description', { permissionCode: selectedRateLimit?.permission_code })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="edit-requests_per_minute">{t('rateLimits.fields.requestsPerMinute')}</Label>
              <Input
                id="edit-requests_per_minute"
                type="number"
                min="1"
                value={editForm.requests_per_minute}
                onChange={(e) => setEditForm({ ...editForm, requests_per_minute: parseInt(e.target.value) || 1 })}
              />
            </div>
            <div>
              <Label htmlFor="edit-burst_limit">{t('rateLimits.fields.burstLimit')}</Label>
              <Input
                id="edit-burst_limit"
                type="number"
                min="1"
                value={editForm.burst_limit}
                onChange={(e) => setEditForm({ ...editForm, burst_limit: parseInt(e.target.value) || 1 })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              {t('rateLimits.buttons.cancel')}
            </Button>
            <Button onClick={handleUpdate} disabled={isUpdating}>
              {isUpdating ? t('rateLimits.buttons.updating') : t('rateLimits.buttons.update')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title={t('rateLimits.dialogs.delete.title')}
        description={t('rateLimits.dialogs.delete.description', { permissionCode: selectedRateLimit?.permission_code })}
        confirmLabel={t('rateLimits.dialogs.delete.confirmLabel')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
