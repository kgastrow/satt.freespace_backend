import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { PermissionMatrix } from '@/components/permissions/PermissionMatrix'
import { UserTypePermissionMatrix } from '@/components/permissions/UserTypePermissionMatrix'
import { PermissionDialog } from '@/components/permissions/PermissionDialog'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  useGetPermissionsQuery,
  useCreatePermissionMutation,
  useUpdatePermissionMutation,
  useDeletePermissionMutation,
  useGetPermissionMatrixQuery,
  useAssignPermissionMutation,
  useRevokePermissionMutation,
  useGetExtendedPermissionMatrixQuery,
  useAssignUserTypePermissionMutation,
  useRevokeUserTypePermissionMutation,
} from '@/features/permissions/permissionsApi'
import type { Permission } from '@/features/permissions/types'

/**
 * Permissions management page for super admins
 * Contains three tabs:
 * 1. Permissions List - CRUD for permissions
 * 2. Role Permissions - Assign/revoke permissions to global roles
 * 3. User Type Permissions - Assign/revoke permissions to user types
 */
export function PermissionsPage() {
  const { t } = useTranslation('admin')
  const [activeTab, setActiveTab] = useState('permissions')

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('permissions.title', 'Permission Management')}
        description={t('permissions.description', 'Manage system permissions and role assignments')}
      />

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="permissions">{t('permissions.tabs.permissions', 'Permissions')}</TabsTrigger>
          <TabsTrigger value="role-permissions">{t('permissions.tabs.rolePermissions', 'Role Permissions')}</TabsTrigger>
          <TabsTrigger value="user-type-permissions">{t('permissions.tabs.userTypePermissions', 'User Type Permissions')}</TabsTrigger>
        </TabsList>

        <TabsContent value="permissions" className="mt-6">
          <PermissionsListTab />
        </TabsContent>

        <TabsContent value="role-permissions" className="mt-6">
          <RolePermissionsTab />
        </TabsContent>

        <TabsContent value="user-type-permissions" className="mt-6">
          <UserTypePermissionsTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

/**
 * Tab content for managing permissions (CRUD)
 */
function PermissionsListTab() {
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data, isLoading } = useGetPermissionsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createPermission, { isLoading: isCreating }] =
    useCreatePermissionMutation()
  const [updatePermission, { isLoading: isUpdating }] =
    useUpdatePermissionMutation()
  const [deletePermission, { isLoading: isDeleting }] =
    useDeletePermissionMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingPermission, setEditingPermission] = useState<Permission | null>(
    null
  )
  const [deletingPermission, setDeletingPermission] =
    useState<Permission | null>(null)

  const handleCreate = async (formData: {
    code: string
    name: string
    description?: string
  }) => {
    try {
      await createPermission({
        code: formData.code,
        name: formData.name,
        description: formData.description || undefined,
        display_order: 0, // Default display order
      }).unwrap()
      toast.success('Permission created successfully')
      setIsCreateOpen(false)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: unknown } }
      const detail = apiError.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to create permission')
    }
  }

  const handleEdit = async (formData: {
    code: string
    name: string
    description?: string
  }) => {
    if (!editingPermission) return
    try {
      await updatePermission({
        id: editingPermission.id,
        data: {
          name: formData.name,
          description: formData.description || undefined,
        },
      }).unwrap()
      toast.success('Permission updated successfully')
      setEditingPermission(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: unknown } }
      const detail = apiError.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to update permission')
    }
  }

  const handleDelete = async () => {
    if (!deletingPermission) return
    try {
      await deletePermission(deletingPermission.id).unwrap()
      toast.success('Permission deleted successfully')
      setDeletingPermission(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: unknown } }
      const detail = apiError.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to delete permission')
    }
  }

  const columns: Column<Permission>[] = [
    {
      key: 'code',
      header: 'Code',
      cell: (permission) => (
        <code className="rounded bg-muted px-2 py-1 text-sm">
          {permission.code}
        </code>
      ),
    },
    {
      key: 'name',
      header: 'Name',
      cell: (permission) => permission.name,
    },
    {
      key: 'description',
      header: 'Description',
      cell: (permission) => (
        <span className="text-muted-foreground">
          {permission.description || '-'}
        </span>
      ),
    },
    {
      key: 'resource',
      header: 'Resource',
      cell: (permission) => permission.resource,
    },
    {
      key: 'action',
      header: 'Action',
      cell: (permission) => permission.action,
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (permission) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setEditingPermission(permission)}>
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingPermission(permission)}
              className="text-destructive"
            >
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setIsCreateOpen(true)}>Create Permission</Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage="No permissions found"
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Permission Dialog */}
      <PermissionDialog
        open={isCreateOpen}
        onOpenChange={setIsCreateOpen}
        onSubmit={handleCreate}
        isLoading={isCreating}
      />

      {/* Edit Permission Dialog */}
      <PermissionDialog
        open={!!editingPermission}
        onOpenChange={(open) => !open && setEditingPermission(null)}
        permission={editingPermission}
        onSubmit={handleEdit}
        isLoading={isUpdating}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingPermission}
        onOpenChange={() => setDeletingPermission(null)}
        title="Delete Permission"
        description={`Are you sure you want to delete the permission "${deletingPermission?.name}"? This will remove it from all roles that have it assigned.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}

/**
 * Tab content for the role permission matrix view
 * Displays the global permission matrix for all roles
 */
function RolePermissionsTab() {
  const { t } = useTranslation('admin')
  // Fetch global permission matrix (roles are system-wide)
  const { data: matrixData, isLoading: isLoadingMatrix } =
    useGetPermissionMatrixQuery()

  const [assignPermission, { isLoading: isAssigning }] =
    useAssignPermissionMutation()
  const [revokePermission, { isLoading: isRevoking }] =
    useRevokePermissionMutation()

  const isToggling = isAssigning || isRevoking

  const handleToggle = async (
    roleId: string,
    permissionId: string,
    checked: boolean
  ) => {
    try {
      if (checked) {
        await assignPermission({
          role_id: roleId,
          permission_id: permissionId,
        }).unwrap()
        toast.success(t('permissions.rolePermissions.assignSuccess', 'Permission assigned successfully'))
      } else {
        await revokePermission({
          role_id: roleId,
          permission_id: permissionId,
        }).unwrap()
        toast.success(t('permissions.rolePermissions.revokeSuccess', 'Permission revoked successfully'))
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(
        apiError.data?.detail ||
          t('permissions.rolePermissions.error', `Failed to ${checked ? 'assign' : 'revoke'} permission`)
      )
    }
  }

  return (
    <div className="space-y-6">
      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('permissions.rolePermissions.title', 'Role Permissions')}</CardTitle>
          <CardDescription>
            {t('permissions.rolePermissions.description', 'Manage permissions for global roles. These permissions apply across all organizations. Users inherit permissions through their role assignments within each organization.')}
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Permission Matrix */}
      <PermissionMatrix
        permissions={matrixData?.permissions || []}
        roles={matrixData?.roles || []}
        onToggle={handleToggle}
        isLoading={isLoadingMatrix}
        isToggling={isToggling}
      />
    </div>
  )
}

/**
 * Tab content for the user type permission matrix view
 * Displays permissions assigned to user types
 */
function UserTypePermissionsTab() {
  const { t } = useTranslation('admin')
  // Fetch extended permission matrix (includes user types)
  const { data: matrixData, isLoading: isLoadingMatrix } =
    useGetExtendedPermissionMatrixQuery()

  const [assignPermission, { isLoading: isAssigning }] =
    useAssignUserTypePermissionMutation()
  const [revokePermission, { isLoading: isRevoking }] =
    useRevokeUserTypePermissionMutation()

  const isToggling = isAssigning || isRevoking

  const handleToggle = async (
    userTypeId: string,
    permissionId: string,
    checked: boolean
  ) => {
    try {
      if (checked) {
        await assignPermission({
          user_type_id: userTypeId,
          permission_id: permissionId,
        }).unwrap()
        toast.success(t('permissions.userTypePermissions.assignSuccess', 'Permission assigned successfully'))
      } else {
        await revokePermission({
          user_type_id: userTypeId,
          permission_id: permissionId,
        }).unwrap()
        toast.success(t('permissions.userTypePermissions.revokeSuccess', 'Permission revoked successfully'))
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(
        apiError.data?.detail ||
          t('permissions.userTypePermissions.error', `Failed to ${checked ? 'assign' : 'revoke'} permission`)
      )
    }
  }

  return (
    <div className="space-y-6">
      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle>{t('permissions.userTypePermissions.title', 'User Type Permissions')}</CardTitle>
          <CardDescription>
            {t('permissions.userTypePermissions.description', 'Manage permissions for user types. Users with a specific user type will automatically have these permissions in addition to their role permissions.')}
          </CardDescription>
        </CardHeader>
      </Card>

      {/* User Type Permission Matrix */}
      <UserTypePermissionMatrix
        permissions={matrixData?.permissions || []}
        userTypes={matrixData?.user_types || []}
        onToggle={handleToggle}
        isLoading={isLoadingMatrix}
        isToggling={isToggling}
      />
    </div>
  )
}
