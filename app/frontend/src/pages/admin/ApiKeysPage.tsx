import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { toast } from '@/lib/toast'
import { useTranslation } from 'react-i18next'
import { Copy, Plus, Trash2, Edit, Key } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
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
import { DatePicker } from '@/components/ui/date-picker'
import {
  useGetApiKeysQuery,
  useCreateApiKeyMutation,
  useUpdateApiKeyMutation,
  useDeleteApiKeyMutation,
  useGetAssignablePermissionsQuery,
} from '@/features/apiKeys'
import { usePermission } from '@/hooks/usePermission'
import { ApiKeyPermissionSelector } from '@/components/permissions/ApiKeyPermissionSelector'
import type { components } from '@/types/api-generated'

type ApiKeyResponse = components['schemas']['ApiKeyDetailResponse']

export function ApiKeysPage() {
  const { t } = useTranslation('settings')
  const { canWrite, canDelete } = usePermission('api_keys')
  const isApiKeysEnabled = useFeatureFlag('api_keys')

  // All hooks must be called before any conditional returns
  const { data, isLoading, error } = useGetApiKeysQuery()
  const apiKeys = data?.items
  const { data: permissionsData, isLoading: isLoadingPermissions } = useGetAssignablePermissionsQuery()
  const [createApiKey, { isLoading: isCreating }] = useCreateApiKeyMutation()
  const [updateApiKey, { isLoading: isUpdating }] = useUpdateApiKeyMutation()
  const [deleteApiKey, { isLoading: isDeleting }] = useDeleteApiKeyMutation()

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showKeyDialog, setShowKeyDialog] = useState(false)
  const [selectedKey, setSelectedKey] = useState<ApiKeyResponse | null>(null)
  const [createdKey, setCreatedKey] = useState<string | null>(null)

  const [createForm, setCreateForm] = useState({
    name: '',
    expires_at: '',
    permissions: [] as string[],
  })

  const [editForm, setEditForm] = useState({
    name: '',
  })

  // Redirect if feature flag is disabled
  if (!isApiKeysEnabled) {
    return <Navigate to="/dashboard" replace />
  }

  const handleCreate = async () => {
    if (!createForm.name.trim()) {
      toast.error(t('apiKeys.messages.nameRequired'))
      return
    }

    // Convert date to ISO string with time set to 23:59:59
    let expiresAt: string | undefined
    if (createForm.expires_at) {
      const date = new Date(createForm.expires_at)
      date.setHours(23, 59, 59, 999)
      expiresAt = date.toISOString()
    }

    try {
      const result = await createApiKey({
        name: createForm.name,
        expires_at: expiresAt,
        permissions: createForm.permissions,
      }).unwrap()

      setCreatedKey(result.key)
      setShowCreateDialog(false)
      setShowKeyDialog(true)
      setCreateForm({ name: '', expires_at: '', permissions: [] })
      toast.success(t('apiKeys.messages.createSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('apiKeys.messages.createError'))
    }
  }

  const handlePermissionToggle = (permissionCode: string, checked: boolean) => {
    setCreateForm((prev) => ({
      ...prev,
      permissions: checked
        ? [...prev.permissions, permissionCode]
        : prev.permissions.filter((code) => code !== permissionCode),
    }))
  }

  const handleUpdate = async () => {
    if (!selectedKey || !editForm.name.trim()) {
      toast.error(t('apiKeys.messages.nameRequired'))
      return
    }

    try {
      await updateApiKey({
        id: selectedKey.id,
        data: {
          name: editForm.name,
        },
      }).unwrap()

      setShowEditDialog(false)
      setSelectedKey(null)
      toast.success(t('apiKeys.messages.updateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('apiKeys.messages.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!selectedKey) return

    try {
      await deleteApiKey(selectedKey.id).unwrap()
      setShowDeleteConfirm(false)
      setSelectedKey(null)
      toast.success(t('apiKeys.messages.deleteSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('apiKeys.messages.deleteError'))
    }
  }

  const openEditDialog = (key: ApiKeyResponse) => {
    setSelectedKey(key)
    setEditForm({
      name: key.name,
    })
    setShowEditDialog(true)
  }

  const openDeleteDialog = (key: ApiKeyResponse) => {
    setSelectedKey(key)
    setShowDeleteConfirm(true)
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success(t('apiKeys.messages.copied'))
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return t('apiKeys.table.never')
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    })
  }

  const isExpired = (expiresAt: string | null) => {
    if (!expiresAt) return false
    return new Date(expiresAt) < new Date()
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
          title={t('apiKeys.title')}
          description={t('apiKeys.description')}
        />
        <Alert variant="destructive">
          <AlertTitle>{t('apiKeys.alerts.error.title')}</AlertTitle>
          <AlertDescription>
            {apiError.data?.detail || t('apiKeys.alerts.error.description')}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('apiKeys.title')}
        description={t('apiKeys.description')}
      />

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
          <div>
            <CardTitle>{t('apiKeys.sections.list.title')}</CardTitle>
            <CardDescription className="mt-1.5">
              {t('apiKeys.sections.list.description')}
            </CardDescription>
          </div>
          {canWrite && (
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4 mr-2" />
              {t('apiKeys.buttons.create')}
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {!apiKeys || apiKeys.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Key className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>{t('apiKeys.table.empty')}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('apiKeys.table.name')}</TableHead>
                  <TableHead>{t('apiKeys.table.prefix')}</TableHead>
                  <TableHead>{t('apiKeys.table.permissions')}</TableHead>
                  <TableHead>{t('apiKeys.table.created')}</TableHead>
                  <TableHead>{t('apiKeys.table.expires')}</TableHead>
                  <TableHead>{t('apiKeys.table.lastUsed')}</TableHead>
                  <TableHead className="text-right">{t('apiKeys.table.actions')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {apiKeys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell>
                      <code className="rounded bg-muted px-2 py-1 text-sm">
                        {key.prefix}...
                      </code>
                    </TableCell>
                    <TableCell>
                      {key.permissions && key.permissions.length > 0 ? (
                        <span className="text-sm text-muted-foreground">
                          {key.permissions.length} {key.permissions.length === 1 ? 'permission' : 'permissions'}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">{t('apiKeys.table.noPermissions')}</span>
                      )}
                    </TableCell>
                    <TableCell>{formatDate(key.created_time)}</TableCell>
                    <TableCell>
                      {key.expires_at ? (
                        <span className={isExpired(key.expires_at) ? 'text-destructive' : ''}>
                          {formatDate(key.expires_at)}
                          {isExpired(key.expires_at) && (
                            <Badge variant="destructive" className="ml-2 text-xs">
                              {t('apiKeys.status.expired')}
                            </Badge>
                          )}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">{t('apiKeys.table.never')}</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {key.last_used_at ? formatDate(key.last_used_at) : (
                        <span className="text-muted-foreground">{t('apiKeys.table.neverUsed')}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        {canWrite && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openEditDialog(key)}
                          >
                            <Edit className="h-4 w-4" />
                          </Button>
                        )}
                        {canDelete && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openDeleteDialog(key)}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create API Key Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('apiKeys.dialogs.create.title')}</DialogTitle>
            <DialogDescription>
              {t('apiKeys.dialogs.create.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="name">{t('apiKeys.fields.name')}</Label>
              <Input
                id="name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder={t('apiKeys.fields.namePlaceholder')}
              />
            </div>
            <div>
              <Label htmlFor="expires_at">{t('apiKeys.fields.expiresAt')}</Label>
              <DatePicker
                value={createForm.expires_at}
                onChange={(value) => setCreateForm({ ...createForm, expires_at: value || '' })}
                placeholder={t('apiKeys.fields.expiresAtHelp')}
                minDate={new Date()}
                dateFormat="PP"
              />
              <p className="text-sm text-muted-foreground mt-1">
                {t('apiKeys.fields.expiresAtHelp')}
              </p>
            </div>
            <div>
              <Label>{t('apiKeys.fields.permissions')}</Label>
              <p className="text-sm text-muted-foreground mb-2">
                {t('apiKeys.fields.permissionsHelp')}
              </p>
              <ApiKeyPermissionSelector
                permissions={permissionsData?.permissions || []}
                selectedPermissionIds={createForm.permissions}
                onToggle={handlePermissionToggle}
                isLoading={isLoadingPermissions}
                readOnly={false}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowCreateDialog(false)}>
              {t('apiKeys.buttons.cancel')}
            </Button>
            <Button onClick={handleCreate} disabled={isCreating}>
              {isCreating ? t('apiKeys.buttons.creating') : t('apiKeys.buttons.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Show Created Key Dialog */}
      <Dialog open={showKeyDialog} onOpenChange={setShowKeyDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('apiKeys.dialogs.showKey.title')}</DialogTitle>
            <DialogDescription>
              {t('apiKeys.dialogs.showKey.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <Alert>
              <AlertTitle>{t('apiKeys.dialogs.showKey.warning')}</AlertTitle>
              <AlertDescription>
                {t('apiKeys.dialogs.showKey.warningDescription')}
              </AlertDescription>
            </Alert>
            <div className="flex items-center gap-2">
              <Input
                readOnly
                value={createdKey || ''}
                className="font-mono text-sm"
              />
              <Button
                variant="outline"
                size="icon"
                onClick={() => copyToClipboard(createdKey || '')}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={() => setShowKeyDialog(false)}>
              {t('apiKeys.buttons.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit API Key Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('apiKeys.dialogs.edit.title')}</DialogTitle>
            <DialogDescription>
              {t('apiKeys.dialogs.edit.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="edit-name">{t('apiKeys.fields.name')}</Label>
              <Input
                id="edit-name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
              />
            </div>
            <div>
              <Label>{t('apiKeys.fields.permissions')}</Label>
              <p className="text-sm text-muted-foreground mb-2">
                {t('apiKeys.fields.permissionsReadOnlyHelp')}
              </p>
              <ApiKeyPermissionSelector
                permissions={
                  (permissionsData?.permissions || []).filter((p) =>
                    selectedKey?.permissions?.includes(p.code)
                  )
                }
                selectedPermissionIds={selectedKey?.permissions || []}
                onToggle={() => {}}
                isLoading={isLoadingPermissions}
                readOnly={true}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              {t('apiKeys.buttons.cancel')}
            </Button>
            <Button onClick={handleUpdate} disabled={isUpdating}>
              {isUpdating ? t('apiKeys.buttons.updating') : t('apiKeys.buttons.update')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title={t('apiKeys.dialogs.delete.title')}
        description={t('apiKeys.dialogs.delete.description', { name: selectedKey?.name })}
        confirmLabel={t('apiKeys.dialogs.delete.confirmLabel')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
