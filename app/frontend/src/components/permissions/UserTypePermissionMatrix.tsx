import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type { Permission, UserTypeWithPermissions } from '@/features/permissions/types'
import { groupPermissionsByResource } from '@/features/permissions/types'

interface UserTypePermissionMatrixProps {
  permissions: Permission[]
  userTypes: UserTypeWithPermissions[]
  onToggle: (userTypeId: string, permissionId: string, checked: boolean) => void
  isLoading?: boolean
  isToggling?: boolean
}

/**
 * User Type Permission Matrix component that displays a grid of permissions vs user types
 * with checkboxes to assign/revoke permissions
 */
export function UserTypePermissionMatrix({
  permissions,
  userTypes,
  onToggle,
  isLoading = false,
  isToggling = false,
}: UserTypePermissionMatrixProps) {
  const { t } = useTranslation('admin')

  // Group permissions by resource for better organization
  const permissionGroups = useMemo(
    () => groupPermissionsByResource(permissions),
    [permissions]
  )

  if (isLoading) {
    return <UserTypePermissionMatrixSkeleton userTypeCount={3} permissionCount={8} />
  }

  if (permissions.length === 0) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        {t('permissions.userTypePermissions.noPermissions', 'No permissions found. Create some permissions first.')}
      </div>
    )
  }

  if (userTypes.length === 0) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        {t('permissions.userTypePermissions.noUserTypes', 'No user types found. Create some user types first.')}
      </div>
    )
  }

  return (
    <div className="rounded-md border overflow-hidden">
      <ScrollArea className="w-full">
        <Table>
          <TableHeader className="sticky top-0 bg-background z-10 border-b">
            <TableRow>
              <TableHead className="w-[250px] sticky left-0 bg-background z-20">
                {t('permissions.userTypePermissions.permissionColumn', 'Permission')}
              </TableHead>
              {userTypes.map((userType) => (
                <TableHead
                  key={userType.id}
                  className="text-center min-w-[120px]"
                >
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div className="cursor-help">
                        <div className="font-medium">{userType.name}</div>
                        <div className="text-xs text-muted-foreground font-normal">
                          {userType.code}
                        </div>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-[300px]">
                      <div className="space-y-1">
                        <p className="font-medium">{userType.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {userType.description || t('permissions.userTypePermissions.noDescription', 'No description')}
                        </p>
                        <p className="text-xs font-mono bg-muted px-1 rounded">
                          {userType.code}
                        </p>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
        </Table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
      <ScrollArea className="h-[550px]">
        <Table>
          <TableBody>
            {permissionGroups.map((group) => (
              <>
                {/* Resource group header */}
                <TableRow
                  key={`group-${group.resource}`}
                  className="bg-muted/50"
                >
                  <TableCell
                    colSpan={userTypes.length + 1}
                    className="font-semibold text-sm sticky left-0 bg-muted/50 w-[250px]"
                  >
                    {formatResourceName(group.resource)}
                  </TableCell>
                </TableRow>

                {/* Permissions in this group */}
                {group.permissions.map((permission) => (
                  <TableRow key={permission.id}>
                    <TableCell className="sticky left-0 bg-background w-[250px]">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <div className="cursor-help">
                            <div className="font-medium text-sm">
                              {permission.name}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {permission.code}
                            </div>
                          </div>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-[300px]">
                          <div className="space-y-1">
                            <p className="font-medium">{permission.name}</p>
                            <p className="text-xs text-muted-foreground">
                              {permission.description || t('permissions.userTypePermissions.noDescription', 'No description')}
                            </p>
                            <p className="text-xs font-mono bg-muted px-1 rounded">
                              {permission.code}
                            </p>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>

                    {userTypes.map((userType) => {
                      const hasPermission = userType.permission_ids.includes(
                        permission.id
                      )
                      return (
                        <TableCell
                          key={userType.id}
                          className="text-center min-w-[120px]"
                        >
                          <div className="flex items-center justify-center">
                            <Checkbox
                              checked={hasPermission}
                              onCheckedChange={(checked) =>
                                onToggle(
                                  userType.id,
                                  permission.id,
                                  checked === true
                                )
                              }
                              disabled={isToggling}
                              className={cn(
                                isToggling && 'opacity-50 cursor-not-allowed'
                              )}
                              aria-label={`${hasPermission ? t('permissions.userTypePermissions.revoke', 'Revoke') : t('permissions.userTypePermissions.assign', 'Assign')} ${permission.name} ${hasPermission ? t('permissions.userTypePermissions.from', 'from') : t('permissions.userTypePermissions.to', 'to')} ${userType.name}`}
                            />
                          </div>
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </>
            ))}
          </TableBody>
        </Table>
        <ScrollBar orientation="horizontal" />
      </ScrollArea>
    </div>
  )
}

/**
 * Format resource name for display (e.g., 'user_management' -> 'User Management')
 */
function formatResourceName(resource: string): string {
  return resource
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

/**
 * Skeleton loading state for the user type permission matrix
 */
function UserTypePermissionMatrixSkeleton({
  userTypeCount,
  permissionCount,
}: {
  userTypeCount: number
  permissionCount: number
}) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[250px]">
              <Skeleton className="h-5 w-24" />
            </TableHead>
            {Array.from({ length: userTypeCount }).map((_, i) => (
              <TableHead key={i} className="text-center min-w-[120px]">
                <div className="space-y-1">
                  <Skeleton className="h-4 w-16 mx-auto" />
                  <Skeleton className="h-3 w-12 mx-auto" />
                </div>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: permissionCount }).map((_, rowIndex) => (
            <TableRow key={rowIndex}>
              <TableCell>
                <div className="space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </TableCell>
              {Array.from({ length: userTypeCount }).map((_, colIndex) => (
                <TableCell key={colIndex} className="text-center">
                  <Skeleton className="h-4 w-4 mx-auto rounded" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
