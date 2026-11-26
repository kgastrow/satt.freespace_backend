import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
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
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import {
  useGetAdminUserTypesQuery,
  useCreateUserTypeMutation,
  useUpdateUserTypeMutation,
  useDeleteUserTypeMutation,
  type UserType,
  type CreateUserTypeRequest,
  type UpdateUserTypeRequest,
} from '@/store/api/onboardingApi'

interface UserTypeFormData {
  name: string
  code: string
  description: string
  is_active: boolean
  requires_onboarding: boolean
  requires_manual_review: boolean
  is_default: boolean
  display_order: number
}

interface FormFieldsProps {
  formData: UserTypeFormData
  setFormData: React.Dispatch<React.SetStateAction<UserTypeFormData>>
  t: (key: string) => string
}

function FormFields({ formData, setFormData, t }: FormFieldsProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="name">{t('userTypes.form.name')}</Label>
          <Input
            id="name"
            value={formData.name}
            onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
            placeholder={t('userTypes.form.namePlaceholder')}
            required
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="code">{t('userTypes.form.code')}</Label>
          <Input
            id="code"
            value={formData.code}
            onChange={(e) => setFormData((prev) => ({ ...prev, code: e.target.value }))}
            placeholder={t('userTypes.form.codePlaceholder')}
            required
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="description">{t('userTypes.form.description')}</Label>
        <Textarea
          id="description"
          value={formData.description}
          onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
          placeholder={t('userTypes.form.descriptionPlaceholder')}
          rows={2}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="display_order">{t('userTypes.form.displayOrder')}</Label>
        <Input
          id="display_order"
          type="number"
          value={formData.display_order}
          onChange={(e) => setFormData((prev) => ({ ...prev, display_order: parseInt(e.target.value) || 0 }))}
          min={0}
        />
      </div>

      <div className="space-y-4 pt-2">
        <div className="flex items-center justify-between">
          <div>
            <Label>{t('userTypes.form.isActive')}</Label>
            <p className="text-sm text-muted-foreground">{t('userTypes.form.isActiveDescription')}</p>
          </div>
          <Switch
            checked={formData.is_active}
            onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, is_active: checked }))}
          />
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label>{t('userTypes.form.isDefault')}</Label>
            <p className="text-sm text-muted-foreground">{t('userTypes.form.isDefaultDescription')}</p>
          </div>
          <Switch
            checked={formData.is_default}
            onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, is_default: checked }))}
          />
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label>{t('userTypes.form.requiresOnboarding')}</Label>
            <p className="text-sm text-muted-foreground">{t('userTypes.form.requiresOnboardingDescription')}</p>
          </div>
          <Switch
            checked={formData.requires_onboarding}
            onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, requires_onboarding: checked }))}
          />
        </div>

        <div className="flex items-center justify-between">
          <div>
            <Label>{t('userTypes.form.requiresManualReview')}</Label>
            <p className="text-sm text-muted-foreground">{t('userTypes.form.requiresManualReviewDescription')}</p>
          </div>
          <Switch
            checked={formData.requires_manual_review}
            onCheckedChange={(checked) => setFormData((prev) => ({ ...prev, requires_manual_review: checked }))}
            disabled={!formData.requires_onboarding}
          />
        </div>
      </div>
    </div>
  )
}

const defaultFormData: UserTypeFormData = {
  name: '',
  code: '',
  description: '',
  is_active: true,
  requires_onboarding: true,
  requires_manual_review: false,
  is_default: false,
  display_order: 0,
}

export function UserTypesPage() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()

  const { data, isLoading } = useGetAdminUserTypesQuery()
  const [createUserType, { isLoading: isCreating }] = useCreateUserTypeMutation()
  const [updateUserType, { isLoading: isUpdating }] = useUpdateUserTypeMutation()
  const [deleteUserType, { isLoading: isDeleting }] = useDeleteUserTypeMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingType, setEditingType] = useState<UserType | null>(null)
  const [deletingType, setDeletingType] = useState<UserType | null>(null)
  const [formData, setFormData] = useState<UserTypeFormData>(defaultFormData)

  const resetForm = () => {
    setFormData(defaultFormData)
  }

  const openCreateDialog = () => {
    resetForm()
    setIsCreateOpen(true)
  }

  const openEditDialog = (userType: UserType) => {
    setFormData({
      name: userType.name,
      code: userType.code,
      description: userType.description || '',
      is_active: userType.is_active,
      requires_onboarding: userType.requires_onboarding,
      requires_manual_review: userType.requires_manual_review,
      is_default: userType.is_default,
      display_order: userType.display_order,
    })
    setEditingType(userType)
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const request: CreateUserTypeRequest = {
        name: formData.name,
        code: formData.code,
        description: formData.description || undefined,
        is_active: formData.is_active,
        requires_onboarding: formData.requires_onboarding,
        requires_manual_review: formData.requires_manual_review,
        is_default: formData.is_default,
        display_order: formData.display_order,
      }
      await createUserType(request).unwrap()
      toast.success(t('userTypes.toast.createSuccess'))
      setIsCreateOpen(false)
      resetForm()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('userTypes.toast.createError'))
    }
  }

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingType) return

    try {
      const request: UpdateUserTypeRequest = {
        name: formData.name,
        code: formData.code,
        description: formData.description || null,
        is_active: formData.is_active,
        requires_onboarding: formData.requires_onboarding,
        requires_manual_review: formData.requires_manual_review,
        is_default: formData.is_default,
        display_order: formData.display_order,
      }
      await updateUserType({ id: editingType.id, data: request }).unwrap()
      toast.success(t('userTypes.toast.updateSuccess'))
      setEditingType(null)
      resetForm()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('userTypes.toast.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!deletingType) return

    try {
      await deleteUserType(deletingType.id).unwrap()
      toast.success(t('userTypes.toast.deleteSuccess'))
      setDeletingType(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('userTypes.toast.deleteError'))
    }
  }

  const columns: Column<UserType>[] = [
    {
      key: 'name',
      header: t('userTypes.table.name'),
      cell: (type) => (
        <div>
          <div className="font-medium">{type.name}</div>
          <div className="text-sm text-muted-foreground">
            <code>{type.code}</code>
          </div>
        </div>
      ),
    },
    {
      key: 'description',
      header: t('userTypes.table.description'),
      cell: (type) => (
        <div className="max-w-[250px] truncate">
          {type.description || <span className="text-muted-foreground">-</span>}
        </div>
      ),
    },
    {
      key: 'status',
      header: t('userTypes.table.status'),
      cell: (type) => (
        <div className="flex flex-wrap gap-1">
          <Badge variant={type.is_active ? 'default' : 'secondary'}>
            {type.is_active ? t('userTypes.table.active') : t('userTypes.table.inactive')}
          </Badge>
          {type.is_default && (
            <Badge variant="outline">{t('userTypes.table.default')}</Badge>
          )}
        </div>
      ),
    },
    {
      key: 'onboarding',
      header: t('userTypes.table.onboarding'),
      cell: (type) => (
        <div className="flex flex-wrap gap-1">
          {type.requires_onboarding ? (
            <>
              <Badge variant="outline">{t('userTypes.table.requiresOnboarding')}</Badge>
              {type.requires_manual_review && (
                <Badge variant="outline">{t('userTypes.table.manualReview')}</Badge>
              )}
            </>
          ) : (
            <span className="text-muted-foreground">-</span>
          )}
        </div>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[100px]',
      cell: (type) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(type)}>
              {t('userTypes.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate(`/platform-admin/user-types/${type.id}/steps`)}>
              {t('userTypes.actions.manageSteps')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingType(type)}
              className="text-destructive"
            >
              {t('userTypes.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('userTypes.pageTitle')}
        description={t('userTypes.pageDescription')}
      >
        <Button onClick={openCreateDialog}>{t('userTypes.createButton')}</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('userTypes.emptyMessage')}
      />

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('userTypes.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('userTypes.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate}>
            <FormFields formData={formData} setFormData={setFormData} t={t} />
            <div className="flex justify-end gap-2 mt-6">
              <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={isCreating}>
                {isCreating ? t('common.creating') : t('common.create')}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingType} onOpenChange={() => setEditingType(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('userTypes.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('userTypes.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleUpdate}>
            <FormFields formData={formData} setFormData={setFormData} t={t} />
            <div className="flex justify-end gap-2 mt-6">
              <Button type="button" variant="outline" onClick={() => setEditingType(null)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" disabled={isUpdating}>
                {isUpdating ? t('common.saving') : t('common.save')}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingType}
        onOpenChange={() => setDeletingType(null)}
        title={t('userTypes.deleteDialog.title')}
        description={t('userTypes.deleteDialog.description', { name: deletingType?.name })}
        confirmLabel={t('userTypes.deleteDialog.confirm')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
