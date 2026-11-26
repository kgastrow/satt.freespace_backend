import { useState, memo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAppSelector } from '@/store/hooks'
import { selectUser } from '@/features/auth/authSelectors'
import { useAuth } from '@/hooks/useAuth'
import { useIsMobile } from '@/hooks/use-mobile'
import { useSettingsNav } from '@/hooks/useSettingsNav'
import { LogOut, ChevronUp, ChevronRight, LifeBuoy } from 'lucide-react'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { UserAvatar } from '@/components/ui/UserAvatar'
import { cn } from '@/lib/utils'

function HeaderUserMenuComponent() {
  const { t } = useTranslation(['common', 'settings'])
  const navigate = useNavigate()
  const user = useAppSelector(selectUser)
  const { logout, isLoggingOut } = useAuth()
  const isMobile = useIsMobile()
  const { navConfig } = useSettingsNav()

  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)

  const handleOpenChange = (open: boolean) => {
    if (!open) {
      setExpandedCategory(null)
    }
  }

  const navigateTo = (path: string) => {
    navigate(path)
    setExpandedCategory(null)
  }

  const toggleCategory = (categoryId: string, e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setExpandedCategory(expandedCategory === categoryId ? null : categoryId)
  }

  return (
    <DropdownMenu onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <UserAvatar
            firstName={user?.first_name}
            lastName={user?.last_name}
            avatarUrl={user?.avatar_url}
            size="sm"
          />
          <span className="sr-only">{t('common:navigation.userMenu')}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {/* User info header */}
        <div className="flex items-center gap-2 p-2">
          <UserAvatar
            firstName={user?.first_name}
            lastName={user?.last_name}
            avatarUrl={user?.avatar_url}
            size="md"
          />
          <div className="flex flex-col gap-0.5 leading-none">
            <span className="font-semibold text-sm">
              {user?.first_name} {user?.last_name}
            </span>
            <span className="text-xs text-muted-foreground">{user?.email}</span>
          </div>
        </div>
        <DropdownMenuSeparator />

        {/* Help Center Link */}
        <DropdownMenuItem asChild>
          <a
            href="/help-center"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 cursor-pointer"
          >
            <LifeBuoy className="h-4 w-4" />
            {t('common:navigation.helpCenter')}
          </a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />

        {isMobile ? (
          // Mobile: Expandable/accordion navigation
          <>
            {navConfig.map((category, categoryIndex) => {
              const CategoryIcon = category.icon
              const isExpanded = expandedCategory === category.id
              const isDanger = category.id === 'danger'

              return (
                <div key={category.id}>
                  {categoryIndex > 0 && isDanger && <DropdownMenuSeparator />}
                  <DropdownMenuItem
                    onClick={(e) => toggleCategory(category.id, e)}
                    className={cn(
                      'flex items-center gap-2 cursor-pointer',
                      isDanger && 'text-destructive focus:text-destructive'
                    )}
                  >
                    <CategoryIcon className="h-4 w-4" />
                    <span className="flex-1">{t(category.labelKey)}</span>
                    {isExpanded ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </DropdownMenuItem>
                  {isExpanded && (
                    <div className="pl-4 border-l ml-4 mt-1 mb-1 space-y-0.5">
                      {category.items.map((item) => {
                        const ItemIcon = item.icon
                        return (
                          <DropdownMenuItem
                            key={item.id}
                            onClick={() => navigateTo(item.path)}
                            className={cn(
                              'flex items-center gap-2 cursor-pointer text-sm',
                              isDanger && 'text-destructive focus:text-destructive'
                            )}
                          >
                            <ItemIcon className="h-3.5 w-3.5" />
                            {t(item.labelKey)}
                          </DropdownMenuItem>
                        )
                      })}
                    </div>
                  )}
                </div>
              )
            })}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => logout()}
              disabled={isLoggingOut}
              className="flex items-center gap-2 cursor-pointer"
            >
              <LogOut className="h-4 w-4" />
              {isLoggingOut ? t('common:navigation.signingOut') : t('common:navigation.signOut')}
            </DropdownMenuItem>
          </>
        ) : (
          // Desktop: Flyout submenus at root level
          <>
            {navConfig.map((category) => {
              const CategoryIcon = category.icon
              const isDanger = category.id === 'danger'

              return (
                <div key={category.id}>
                  {isDanger && <DropdownMenuSeparator />}
                  <DropdownMenuSub>
                    <DropdownMenuSubTrigger
                      className={cn(
                        'flex items-center gap-2',
                        isDanger && 'text-destructive focus:text-destructive'
                      )}
                    >
                      <CategoryIcon className="h-4 w-4" />
                      {t(category.labelKey)}
                    </DropdownMenuSubTrigger>
                    <DropdownMenuSubContent className="w-48">
                      {category.items.map((item) => {
                        const ItemIcon = item.icon
                        return (
                          <DropdownMenuItem
                            key={item.id}
                            onClick={() => navigateTo(item.path)}
                            className={cn(
                              'flex items-center gap-2 cursor-pointer',
                              isDanger && 'text-destructive focus:text-destructive'
                            )}
                          >
                            <ItemIcon className="h-4 w-4" />
                            {t(item.labelKey)}
                          </DropdownMenuItem>
                        )
                      })}
                    </DropdownMenuSubContent>
                  </DropdownMenuSub>
                </div>
              )
            })}
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => logout()}
              disabled={isLoggingOut}
              className="flex items-center gap-2 cursor-pointer"
            >
              <LogOut className="h-4 w-4" />
              {isLoggingOut ? t('common:navigation.signingOut') : t('common:navigation.signOut')}
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Memoize to prevent re-renders when parent state changes
export const HeaderUserMenu = memo(HeaderUserMenuComponent)
