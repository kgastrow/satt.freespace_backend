import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Shield } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { toast } from '@/lib/toast'
import { usePermission } from '@/hooks/usePermission'
import { useAuth } from '@/hooks/useAuth'
import {
  useGetRolesQuery,
  useGetUserRolesQuery,
  useAssignRoleMutation,
  useRevokeRoleMutation,
} from '@/features/roles/rolesApi'
import type { UserFullDetail } from '@/features/users/usersApi'

interface UserRolesCardProps {
  user: UserFullDetail
}

export function UserRolesCard({ user }: UserRolesCardProps) {
  const { t } = useTranslation('admin')
  const { t: tBackend } = useTranslation('backend')
  const { canWrite } = usePermission('roles')
  const { user: currentUser } = useAuth()
  const isSuperAdmin = currentUser?.isAdmin === true

  const { data: userRoles, isLoading: isLoadingUserRoles } = useGetUserRolesQuery({ userId: user.id })
  const { data: allRoles, isLoading: isLoadingAllRoles } = useGetRolesQuery({ limit: 100, offset: 0 })
  const [assignRole] = useAssignRoleMutation()
  const [revokeRole] = useRevokeRoleMutation()
  const [updatingRoleIds, setUpdatingRoleIds] = useState<Set<string>>(new Set())

  // Check if this is self-assignment (assigning roles to yourself)
  const isSelfAssignment = currentUser?.id === user.id
  const canModifyRoles = canWrite && (isSuperAdmin || !isSelfAssignment)

  const assignedRoleIds = new Set(userRoles?.items?.map((r) => r.role_id) || [])

  const handleToggleRole = async (roleId: string, isCurrentlyAssigned: boolean) => {
    if (!canModifyRoles) {
      toast.error(tBackend('user_role.self_assignment_forbidden'))
      return
    }

    setUpdatingRoleIds((prev) => new Set(prev).add(roleId))

    try {
      if (isCurrentlyAssigned) {
        await revokeRole({ user_id: user.id, role_id: roleId }).unwrap()
        toast.success(t('users.toast.roleRevokeSuccess'))
      } else {
        await assignRole({ user_id: user.id, role_id: roleId }).unwrap()
        toast.success(t('users.toast.roleAssignSuccess'))
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string; detail_code?: string } }
      if (apiError.data?.detail_code === 'user_role.self_assignment_forbidden') {
        toast.error(tBackend('user_role.self_assignment_forbidden'))
      } else if (apiError.data?.detail_code === 'user_role.hierarchy_violation') {
        toast.error(tBackend('user_role.hierarchy_violation'))
      } else {
        toast.error(apiError.data?.detail || t('users.toast.roleAssignError'))
      }
    } finally {
      setUpdatingRoleIds((prev) => {
        const next = new Set(prev)
        next.delete(roleId)
        return next
      })
    }
  }

  const isLoading = isLoadingUserRoles || isLoadingAllRoles

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Shield className="h-5 w-5" />
          {t('users.detail.sections.roles')}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {!canModifyRoles && isSelfAssignment && (
          <p className="text-sm text-muted-foreground mb-4">
            {tBackend('user_role.self_assignment_forbidden')}
          </p>
        )}

        <div className="border rounded-md">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 text-sm font-medium">
                  {t('users.roleDialog.roleName')}
                </th>
                <th className="w-16 p-3 text-center text-sm font-medium">
                  {t('users.roleDialog.assigned')}
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={2} className="p-4 text-center text-muted-foreground">
                    {t('users.roleDialog.loading')}
                  </td>
                </tr>
              ) : allRoles?.items?.length ? (
                allRoles.items.map((role) => {
                  const isAssigned = assignedRoleIds.has(role.id)
                  const isUpdating = updatingRoleIds.has(role.id)
                  return (
                    <tr key={role.id} className="border-b last:border-0">
                      <td className="p-3">
                        <div>
                          <span className="text-sm font-medium">{role.name}</span>
                          {role.description && (
                            <p className="text-xs text-muted-foreground">{role.description}</p>
                          )}
                        </div>
                      </td>
                      <td className="p-3 text-center">
                        <Checkbox
                          checked={isAssigned}
                          disabled={!canModifyRoles || isUpdating}
                          onCheckedChange={() => handleToggleRole(role.id, isAssigned)}
                          className={isUpdating ? 'opacity-50' : ''}
                        />
                      </td>
                    </tr>
                  )
                })
              ) : (
                <tr>
                  <td colSpan={2} className="p-4 text-center text-muted-foreground">
                    {t('users.roleDialog.noRolesAvailable')}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
