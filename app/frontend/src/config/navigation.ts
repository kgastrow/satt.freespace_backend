import type { LucideIcon } from 'lucide-react'
import { LayoutDashboard, Settings, ShieldAlert } from 'lucide-react'
import { adminNavConfig } from './adminNav'
import { platformAdminNavConfig } from './platformAdminNav'

/**
 * Navigation item configuration
 */
export interface NavItem {
  /** Unique identifier for the navigation item */
  id: string
  /** i18n key for the item title */
  title: string
  /** Route URL path */
  url: string
  /** Lucide icon component */
  icon: LucideIcon
  /** Required permissions (empty = no permission required) */
  permissions?: string[]
  /** Require all permissions (true) or any permission (false, default) */
  requireAll?: boolean
  /** Badge type for dynamic badges */
  badge?: 'notification-count' | 'pending-count'
  /** Only shown when the backend runs in mock mode */
  requiresMockMode?: boolean
  /** Child navigation items */
  children?: NavItem[]
  /** Show divider before this item */
  dividerBefore?: boolean
  /** Show divider after this item */
  dividerAfter?: boolean
  /** External link (opens in new tab) */
  external?: boolean
}

/**
 * Navigation section configuration
 */
export interface NavSection {
  /** Unique identifier for the section */
  id: string
  /** i18n key for section title (optional for untitled sections) */
  title?: string
  /** Navigation items in this section */
  items: NavItem[]
}

/**
 * Main application navigation
 * Used in AppSidebar for regular users
 */
export const mainNavigation: NavSection[] = [
  {
    id: 'main',
    title: 'common:sidebar.navigation',
    items: [
      {
        id: 'dashboard',
        title: 'common:navigation.dashboard',
        url: '/dashboard',
        icon: LayoutDashboard,
      },
    ],
  },
]

/**
 * Admin hub navigation
 * Used in AppSidebar to show a single link to Admin Hub
 */
export const adminNavigation: NavSection[] = [
  {
    id: 'admin-hub',
    items: [
      {
        id: 'admin-hub',
        title: 'common:navigation.adminHub',
        url: '/admin',
        icon: Settings,
        permissions: [
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
          'reports:read',
          'changelog:write',
          'sites:read',
        ],
      },
    ],
  },
]

/**
 * Admin sidebar navigation
 * Used in AdminSidebar - full navigation with collapsible categories
 * Converts adminNavConfig categories into NavSection format
 */
export const adminSidebarNavigation: NavSection[] = adminNavConfig.map((category) => ({
  id: category.id,
  title: category.labelKey,
  items: category.items.map((item) => ({
    id: item.id,
    title: item.labelKey,
    url: item.path,
    icon: item.icon,
    permissions: item.permissions,
    requiresMockMode: item.requiresMockMode,
  })),
}))

/**
 * Platform admin hub navigation
 * Used in AppSidebar to show a single link to Platform Admin Hub
 */
export const platformAdminNavigation: NavSection[] = [
  {
    id: 'platform-admin',
    items: [
      {
        id: 'platform-admin-hub',
        title: 'common:navigation.platformAdminHub',
        url: '/platform-admin',
        icon: ShieldAlert,
      },
    ],
  },
]

/**
 * Platform admin sidebar navigation
 * Used in PlatformAdminSidebar - full navigation with collapsible categories
 * Converts platformAdminNavConfig categories into NavSection format
 */
export const platformAdminSidebarNavigation: NavSection[] = platformAdminNavConfig.map((category) => ({
  id: category.id,
  title: category.labelKey,
  items: category.items.map((item) => ({
    id: item.id,
    title: item.labelKey,
    url: item.path,
    icon: item.icon,
  })),
}))
