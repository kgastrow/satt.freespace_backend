import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { type SettingsNavCategory } from '@/config/settingsNav'
import { useSettingsNav } from '@/hooks/useSettingsNav'
import { Button } from '@/components/ui/button'

interface SettingsSidebarProps {
  onNavigate?: () => void
}

export function SettingsSidebar({ onNavigate }: SettingsSidebarProps) {
  const { t } = useTranslation(['settings'])
  const location = useLocation()
  const { navConfig } = useSettingsNav()

  // Determine which categories should be expanded based on current path
  // Default to all expanded for better discoverability
  const getInitialExpandedState = () => {
    const expanded: Record<string, boolean> = {}
    navConfig.forEach((category) => {
      expanded[category.id] = true
    })
    return expanded
  }

  const [expandedCategories, setExpandedCategories] = useState<Record<string, boolean>>(
    getInitialExpandedState
  )

  const toggleCategory = (categoryId: string) => {
    setExpandedCategories((prev) => ({
      ...prev,
      [categoryId]: !prev[categoryId],
    }))
  }

  const handleItemClick = () => {
    onNavigate?.()
  }

  const isItemActive = (path: string) => {
    return location.pathname === path || location.pathname.startsWith(path + '/')
  }

  const isCategoryActive = (category: SettingsNavCategory) => {
    return category.items.some((item) => isItemActive(item.path))
  }

  return (
    <nav className="space-y-1">
      {navConfig.map((category) => {
        const CategoryIcon = category.icon
        const isExpanded = expandedCategories[category.id]
        const isActive = isCategoryActive(category)

        return (
          <div key={category.id}>
            <Button
              variant="ghost"
              className={cn(
                'w-full justify-between font-medium',
                isActive && 'bg-accent text-accent-foreground'
              )}
              onClick={() => toggleCategory(category.id)}
            >
              <span className="flex items-center gap-2">
                <CategoryIcon className="h-4 w-4" />
                {t(category.labelKey)}
              </span>
              {isExpanded ? (
                <ChevronDown className="h-4 w-4" />
              ) : (
                <ChevronRight className="h-4 w-4" />
              )}
            </Button>

            {isExpanded && (
              <div className="ml-4 mt-1 space-y-1 border-l pl-2">
                {category.items.map((item) => {
                  const ItemIcon = item.icon
                  const active = isItemActive(item.path)

                  return (
                    <NavLink
                      key={item.id}
                      to={item.path}
                      onClick={handleItemClick}
                      className={cn(
                        'flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                        active
                          ? 'bg-primary text-primary-foreground'
                          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                      )}
                    >
                      <ItemIcon className="h-4 w-4" />
                      {t(item.labelKey)}
                    </NavLink>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </nav>
  )
}
