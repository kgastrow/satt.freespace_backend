import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { NavItem, NavSection } from '@/config/navigation'
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'

/**
 * Props for the NavRenderer component
 */
interface NavRendererProps {
  /** Navigation sections to render */
  sections: NavSection[]
  /** Whether the sidebar is collapsed (icon-only mode) */
  collapsed?: boolean
  /** Callback when a navigation item is clicked */
  onItemClick?: () => void
  /** Additional CSS classes */
  className?: string
  /** Variant for styling - 'default', 'admin', or 'platform-admin' */
  variant?: 'default' | 'admin' | 'platform-admin'
}

/**
 * Get variant-specific styles
 */
function getVariantStyles(variant: 'default' | 'admin' | 'platform-admin', isActive: boolean) {
  switch (variant) {
    case 'platform-admin':
      return {
        item: cn(
          'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
          isActive
            ? 'bg-destructive text-destructive-foreground'
            : 'text-muted-foreground hover:bg-destructive/10 hover:text-destructive'
        ),
        category: cn(
          'w-full justify-between font-medium',
          isActive && 'bg-destructive/10 text-destructive'
        ),
        border: 'border-l border-destructive/20',
      }
    case 'admin':
      return {
        item: cn(
          'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
          isActive
            ? 'bg-primary text-primary-foreground'
            : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
        ),
        category: cn(
          'w-full justify-between font-medium',
          isActive && 'bg-accent text-accent-foreground'
        ),
        border: 'border-l',
      }
    default:
      return {
        item: '',
        category: '',
        border: '',
      }
  }
}

/**
 * Renders a single navigation item
 */
function NavItemComponent({
  item,
  onItemClick,
  isActive,
  variant = 'default',
}: {
  item: NavItem
  onItemClick?: () => void
  isActive: boolean
  variant?: 'default' | 'admin' | 'platform-admin'
}) {
  const { t } = useTranslation()
  const Icon = item.icon
  const styles = getVariantStyles(variant, isActive)

  if (variant === 'default') {
    // Use SidebarMenuButton for default variant (AppSidebar style)
    return (
      <SidebarMenuItem>
        <SidebarMenuButton asChild tooltip={t(item.title)}>
          <NavLink to={item.url} onClick={onItemClick}>
            {({ isActive }) => (
              <>
                <Icon className={isActive ? 'text-sidebar-primary' : ''} />
                <span>{t(item.title)}</span>
              </>
            )}
          </NavLink>
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  // Use custom styling for admin variants
  return (
    <NavLink to={item.url} onClick={onItemClick} className={styles.item}>
      <Icon className="h-4 w-4" />
      {t(item.title)}
    </NavLink>
  )
}

/**
 * Renders a collapsible navigation category (for admin variants)
 */
function NavCategoryComponent({
  section,
  isExpanded,
  onToggle,
  onItemClick,
  isActive,
  location,
  variant = 'admin',
}: {
  section: NavSection
  isExpanded: boolean
  onToggle: () => void
  onItemClick?: () => void
  isActive: boolean
  location: ReturnType<typeof useLocation>
  variant?: 'admin' | 'platform-admin'
}) {
  const { t } = useTranslation()
  const styles = getVariantStyles(variant, isActive)

  // Get the first item's icon to use as category icon
  const CategoryIcon = section.items[0]?.icon

  const isItemActive = (url: string) => {
    return location.pathname === url || location.pathname.startsWith(url + '/')
  }

  return (
    <div>
      <Button variant="ghost" className={styles.category} onClick={onToggle}>
        <span className="flex items-center gap-2">
          {CategoryIcon && <CategoryIcon className="h-4 w-4" />}
          {section.title && t(section.title)}
        </span>
        {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </Button>

      {isExpanded && (
        <div className={cn('ml-4 mt-1 space-y-1 pl-2', styles.border)}>
          {section.items.map((item) => (
            <NavItemComponent
              key={item.id}
              item={item}
              onItemClick={onItemClick}
              isActive={isItemActive(item.url)}
              variant={variant}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * Navigation renderer component
 *
 * Renders navigation sections with permission filtering.
 * Supports multiple rendering styles via the variant prop.
 *
 * @example
 * ```tsx
 * // Default style (AppSidebar)
 * const { sections } = useNavigation('main')
 * <NavRenderer sections={sections} variant="default" />
 *
 * // Admin style
 * const { sections } = useNavigation('admin')
 * <NavRenderer sections={sections} variant="admin" />
 *
 * // Platform admin style
 * const { sections } = useNavigation('platform-admin')
 * <NavRenderer sections={sections} variant="platform-admin" />
 * ```
 */
export function NavRenderer({
  sections,
  collapsed = false,
  onItemClick,
  className,
  variant = 'default',
}: NavRendererProps) {
  const location = useLocation()
  const { t } = useTranslation()

  // Track expanded state for collapsible categories (admin variants only)
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {}
    sections.forEach((section) => {
      initial[section.id] = true // Default to expanded
    })
    return initial
  })

  const toggleSection = (sectionId: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }))
  }

  const isItemActive = (url: string) => {
    return location.pathname === url || location.pathname.startsWith(url + '/')
  }

  const isSectionActive = (section: NavSection) => {
    return section.items.some((item) => isItemActive(item.url))
  }

  // Default variant - flat navigation with SidebarMenu components
  if (variant === 'default') {
    return (
      <div className={cn('flex flex-col gap-1', className)}>
        {sections.map((section) => (
          <SidebarGroup key={section.id}>
            {section.title && !collapsed && (
              <SidebarGroupLabel>{t(section.title)}</SidebarGroupLabel>
            )}
            <SidebarGroupContent>
              <nav>
                <SidebarMenu>
                  {section.items.map((item) => (
                    <NavItemComponent
                      key={item.id}
                      item={item}
                      onItemClick={onItemClick}
                      isActive={isItemActive(item.url)}
                      variant="default"
                    />
                  ))}
                </SidebarMenu>
              </nav>
            </SidebarGroupContent>
            {sections.indexOf(section) < sections.length - 1 && <SidebarSeparator />}
          </SidebarGroup>
        ))}
      </div>
    )
  }

  // Admin variants - collapsible categories
  return (
    <nav className={cn('space-y-1', className)}>
      {sections.map((section) => (
        <NavCategoryComponent
          key={section.id}
          section={section}
          isExpanded={expandedSections[section.id]}
          onToggle={() => toggleSection(section.id)}
          onItemClick={onItemClick}
          isActive={isSectionActive(section)}
          location={location}
          variant={variant}
        />
      ))}
    </nav>
  )
}
