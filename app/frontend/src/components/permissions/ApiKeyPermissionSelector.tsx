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
import type { Permission } from '@/features/permissions/types'
import { groupPermissionsByResource } from '@/features/permissions/types'

interface ApiKeyPermissionSelectorProps {
  permissions: Permission[]
  selectedPermissionIds: string[]
  onToggle: (permissionCode: string, checked: boolean) => void
  isLoading?: boolean
  readOnly?: boolean
}

/**
 * Permission selector component for API key creation/viewing.
 * Only shows permissions the user has access to (fetched from backend).
 * Read-only when viewing existing API keys (permissions can only be set at creation).
 *
 * Note: selectedPermissionIds should contain permission codes (e.g., "users:read"),
 * not UUIDs. The parameter name is kept for backwards compatibility.
 */
export function ApiKeyPermissionSelector({
  permissions,
  selectedPermissionIds,
  onToggle,
  isLoading = false,
  readOnly = false,
}: ApiKeyPermissionSelectorProps) {
  const { t } = useTranslation('settings')

  // Group permissions by resource for better organization
  const permissionGroups = useMemo(
    () => groupPermissionsByResource(permissions),
    [permissions]
  )

  if (isLoading) {
    return <ApiKeyPermissionSelectorSkeleton permissionCount={8} />
  }

  if (permissions.length === 0) {
    return (
      <div className="rounded-md border p-8 text-center text-muted-foreground">
        {t('apiKeys.messages.noPermissions')}
      </div>
    )
  }

  return (
    <div className="rounded-md border overflow-hidden">
      <ScrollArea className="h-[400px]">
        <Table>
          <TableHeader className="sticky top-0 bg-background z-10 border-b">
            <TableRow>
              {!readOnly && (
                <TableHead className="w-[60px]">
                  {t('apiKeys.table.permissions')}
                </TableHead>
              )}
              <TableHead>{t('apiKeys.fields.permissions')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {permissionGroups.map((group) => (
              <>
                {/* Resource group header */}
                <TableRow
                  key={`group-${group.resource}`}
                  className="bg-muted/50"
                >
                  <TableCell
                    colSpan={readOnly ? 1 : 2}
                    className="font-semibold text-sm"
                  >
                    {formatResourceName(group.resource)}
                  </TableCell>
                </TableRow>

                {/* Permissions in this group */}
                {group.permissions.map((permission) => {
                  const isSelected = selectedPermissionIds.includes(permission.code)
                  return (
                    <TableRow key={permission.id}>
                      {!readOnly && (
                        <TableCell className="w-[60px]">
                          <div className="flex items-center justify-center">
                            <Checkbox
                              checked={isSelected}
                              onCheckedChange={(checked) =>
                                onToggle(permission.code, checked === true)
                              }
                              aria-label={`${isSelected ? 'Deselect' : 'Select'} ${permission.name}`}
                            />
                          </div>
                        </TableCell>
                      )}
                      <TableCell>
                        <div>
                          <div className="font-medium text-sm">
                            {permission.name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {permission.code}
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
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
 * Skeleton loading state for the permission selector
 */
function ApiKeyPermissionSelectorSkeleton({
  permissionCount,
}: {
  permissionCount: number
}) {
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[60px]">
              <Skeleton className="h-5 w-8 mx-auto" />
            </TableHead>
            <TableHead>
              <Skeleton className="h-5 w-24" />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: permissionCount }).map((_, rowIndex) => (
            <TableRow key={rowIndex}>
              <TableCell className="w-[60px]">
                <Skeleton className="h-4 w-4 mx-auto rounded" />
              </TableCell>
              <TableCell>
                <div className="space-y-1">
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-3 w-24" />
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
