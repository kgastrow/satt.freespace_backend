import { useTranslation } from 'react-i18next'
import { useHasAnyPermission } from '@/hooks/usePermission'

export function AdminHubPage() {
  const { t } = useTranslation('admin')

  // Check if user has any admin permissions
  const hasAnyAdminAccess = useHasAnyPermission([
    'organization:read',
    'organization:write',
    'users:read',
    'users:write',
    'users:delete',
    'api_keys:read',
    'api_keys:write',
    'api_keys:delete',
    'notifications:read',
    'notifications:write',
    'notifications:send',
    'announcements:read',
    'announcements:write',
    'announcements:delete',
    'files:read',
    'files:write',
    'files:delete',
    'files:admin',
    'two_factor:read',
    'two_factor:write',
    'audit_logs:read',
    'metrics:read',
    'feedback:view',
  ])

  if (!hasAnyAdminAccess) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <p className="text-muted-foreground text-lg">
            {t('common:adminHub.emptyState', "You don't have access to any admin functions.")}
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="text-center py-12">
      <p className="text-muted-foreground">
        {t('selectFromSidebar', 'Select an option from the sidebar to get started.')}
      </p>
    </div>
  )
}
