import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useAppSelector } from '@/store/hooks'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
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
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  useGetRolesQuery,
  useCreateRoleMutation,
  useUpdateRoleMutation,
  useDeleteRoleMutation,
  type Role,
} from '@/features/roles/rolesApi'

const roleSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  is_default_on_registration: z.boolean(),
})

type RoleFormData = z.infer<typeof roleSchema>

export function RolesPage() {
  const { t } = useTranslation('admin')
  const { user: currentUser } = useAppSelector((state) => state.auth)
  const isSuperAdmin = currentUser?.is_admin === true
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data, isLoading } = useGetRolesQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createRole, { isLoading: isCreating }] = useCreateRoleMutation()
  const [updateRole, { isLoading: isUpdating }] = useUpdateRoleMutation()
  const [deleteRole, { isLoading: isDeleting }] = useDeleteRoleMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingRole, setEditingRole] = useState<Role | null>(null)
  const [deletingRole, setDeletingRole] = useState<Role | null>(null)

  const form = useForm<RoleFormData>({
    resolver: zodResolver(roleSchema),
    defaultValues: {
      name: '',
      description: '',
      is_default_on_registration: false,
    },
  })

  const handleCreate = async (data: RoleFormData) => {
    try {
      await createRole({
        name: data.name,
        description: data.description || undefined,
        is_default_on_registration: data.is_default_on_registration,
      }).unwrap()
      toast.success(t('roles.toast.createSuccess'))
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('roles.toast.createError'))
    }
  }

  const handleEdit = async (data: RoleFormData) => {
    if (!editingRole) return
    try {
      await updateRole({
        id: editingRole.id,
        data: {
          name: data.name,
          description: data.description || undefined,
          is_default_on_registration: data.is_default_on_registration,
        },
      }).unwrap()
      toast.success(t('roles.toast.updateSuccess'))
      setEditingRole(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('roles.toast.updateError'))
    }
  }

  const handleDelete = async () => {
    if (!deletingRole) return
    try {
      await deleteRole(deletingRole.id).unwrap()
      toast.success(t('roles.toast.deleteSuccess'))
      setDeletingRole(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('roles.toast.deleteError'))
    }
  }

  const openEditDialog = (role: Role) => {
    form.reset({
      name: role.name,
      description: role.description || '',
      is_default_on_registration: role.is_default_on_registration ?? false,
    })
    setEditingRole(role)
  }

  const openCreateDialog = () => {
    form.reset({
      name: '',
      description: '',
      is_default_on_registration: false,
    })
    setIsCreateOpen(true)
  }

  const columns: Column<Role>[] = [
    {
      key: 'name',
      header: t('roles.table.name'),
      cell: (role) => role.name,
    },
    {
      key: 'description',
      header: t('roles.table.description'),
      cell: (role) => role.description || '-',
    },
    {
      key: 'default',
      header: t('roles.table.defaultOnRegistration'),
      cell: (role) =>
        role.is_default_on_registration ? (
          <Badge variant="secondary">{t('roles.table.default')}</Badge>
        ) : null,
    },
    {
      key: 'created',
      header: t('roles.table.created'),
      cell: (role) => new Date(role.created_time).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (role) =>
        isSuperAdmin ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                ...
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => openEditDialog(role)}>
                {t('roles.actions.edit')}
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setDeletingRole(role)}
                className="text-destructive"
              >
                {t('roles.actions.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null,
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('roles.pageTitle')}
        description={t('roles.pageDescription')}
      >
        {isSuperAdmin && (
          <Button onClick={openCreateDialog}>{t('roles.createButton')}</Button>
        )}
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('roles.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Role Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('roles.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('roles.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('roles.createDialog.name')}</FormLabel>
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
                    <FormLabel>{t('roles.createDialog.descriptionLabel')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="is_default_on_registration"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel>{t('roles.form.defaultOnRegistration')}</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        {t('roles.form.defaultOnRegistrationDescription')}
                      </p>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('roles.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? t('roles.createDialog.creating') : t('roles.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Role Dialog */}
      <Dialog open={!!editingRole} onOpenChange={() => setEditingRole(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('roles.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('roles.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEdit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('roles.editDialog.name')}</FormLabel>
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
                    <FormLabel>{t('roles.editDialog.descriptionLabel')}</FormLabel>
                    <FormControl>
                      <Textarea {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="is_default_on_registration"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                    <div className="space-y-0.5">
                      <FormLabel>{t('roles.form.defaultOnRegistration')}</FormLabel>
                      <p className="text-sm text-muted-foreground">
                        {t('roles.form.defaultOnRegistrationDescription')}
                      </p>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingRole(null)}
                >
                  {t('roles.editDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? t('roles.editDialog.saving') : t('roles.editDialog.save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingRole}
        onOpenChange={() => setDeletingRole(null)}
        title={t('roles.deleteDialog.title')}
        description={t('roles.deleteDialog.description', { name: deletingRole?.name })}
        confirmLabel={t('roles.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
