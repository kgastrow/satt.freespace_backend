import { useMemo } from 'react'
import { usePermissions } from './usePermissions'
import {
  mainNavigation,
  adminNavigation,
  adminSidebarNavigation,
  platformAdminNavigation,
  platformAdminSidebarNavigation,
  type NavItem,
  type NavSection,
} from '@/config/navigation'

/**
 * Navigation type selector
 */
export type NavigationType = 'main' | 'admin' | 'admin-sidebar' | 'platform-admin' | 'platform-admin-sidebar'

/**
 * Navigation hook return type
 */
export interface UseNavigationReturn {
  /** Filtered navigation sections based on user permissions */
  sections: NavSection[]
  /** True if user is super admin */
  isSuperAdmin: boolean
}

/**
 * Hook for accessing and filtering navigation based on user permissions.
 *
 * This hook provides data-driven navigation that automatically filters
 * items based on the current user's permissions. It uses the centralized
 * navigation configuration from @/config/navigation.ts.
 *
 * Features:
 * - Permission-based filtering
 * - Super admin bypass
 * - Impersonation support (super admin access disabled during impersonation)
 * - Reactive updates when permissions change
 *
 * @param type - Navigation type ('main' | 'admin' | 'platform-admin')
 * @returns Filtered navigation sections and super admin status
 *
 * @example
 * ```tsx
 * function AppSidebar() {
 *   const { sections, isSuperAdmin } = useNavigation('main')
 *
 *   return (
 *     <nav>
 *       {sections.map(section => (
 *         <div key={section.id}>
 *           {section.title && <h3>{t(section.title)}</h3>}
 *           {section.items.map(item => (
 *             <NavLink key={item.id} to={item.url}>
 *               <item.icon />
 *               {t(item.title)}
 *             </NavLink>
 *           ))}
 *         </div>
 *       ))}
 *     </nav>
 *   )
 * }
 * ```
 */
export function useNavigation(type: NavigationType): UseNavigationReturn {
  const { hasAnyPermission, hasAllPermissions, isSuperAdmin } = usePermissions()

  // Select navigation config based on type
  const config = useMemo(() => {
    switch (type) {
      case 'main':
        return mainNavigation
      case 'admin':
        return adminNavigation
      case 'admin-sidebar':
        return adminSidebarNavigation
      case 'platform-admin':
        return platformAdminNavigation
      case 'platform-admin-sidebar':
        return platformAdminSidebarNavigation
    }
  }, [type])

  // Filter navigation items based on permissions
  const filteredNavigation = useMemo(() => {
    /**
     * Filter a single navigation item and its children
     */
    const filterItem = (item: NavItem): NavItem | null => {
      // Check permissions if specified
      if (item.permissions && item.permissions.length > 0) {
        const hasAccess = item.requireAll
          ? hasAllPermissions(item.permissions)
          : hasAnyPermission(item.permissions)

        if (!hasAccess) return null
      }

      // Filter children recursively
      if (item.children) {
        const filteredChildren = item.children
          .map(filterItem)
          .filter((child): child is NavItem => child !== null)

        // If no children passed the filter, hide the parent
        if (filteredChildren.length === 0) return null

        return { ...item, children: filteredChildren }
      }

      return item
    }

    /**
     * Filter a navigation section
     */
    const filterSection = (section: NavSection): NavSection | null => {
      const filteredItems = section.items
        .map(filterItem)
        .filter((item): item is NavItem => item !== null)

      // If no items passed the filter, hide the section
      if (filteredItems.length === 0) return null

      return { ...section, items: filteredItems }
    }

    // Filter all sections
    return config
      .map(filterSection)
      .filter((section): section is NavSection => section !== null)
  }, [config, hasAnyPermission, hasAllPermissions])

  return {
    sections: filteredNavigation,
    isSuperAdmin,
  }
}
