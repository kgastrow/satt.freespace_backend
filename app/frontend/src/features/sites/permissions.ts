import { usePermissions } from '@/hooks/usePermissions'

/** Permission codes (specs/freespace_contracts.md section 7). */
export const SITE_PERMISSIONS = {
  read: 'sites:read',
  write: 'sites:write',
  keysWrite: 'site_keys:write',
  pushTest: 'site_push:test',
  pushAnnounce: 'site_push:announce',
  eventsRead: 'site_events:read',
} as const

/**
 * What the current user may do in the Sites section. Viewer and Operator are
 * read-only on these pages; Administrator edits. App keys are super admin only
 * (and live in the platform admin hub, which guards them).
 */
export function useSitePermissions() {
  const { hasPermission, isSuperAdmin } = usePermissions()
  return {
    canRead: hasPermission(SITE_PERMISSIONS.read),
    canWrite: hasPermission(SITE_PERMISSIONS.write),
    canWriteKeys: hasPermission(SITE_PERMISSIONS.keysWrite),
    canTestPush: hasPermission(SITE_PERMISSIONS.pushTest),
    canAnnounce: hasPermission(SITE_PERMISSIONS.pushAnnounce),
    canReadEvents: hasPermission(SITE_PERMISSIONS.eventsRead),
    isSuperAdmin,
    hasPermission,
  }
}
