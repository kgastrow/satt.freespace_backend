import { memo } from 'react'
import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useNavigation } from '@/hooks/useNavigation'
import { PanelLeftClose, PanelLeft } from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from '@/components/ui/sidebar'

function AppSidebarComponent() {
  const { t } = useTranslation()
  const { toggleSidebar, state, isMobile, setOpenMobile } = useSidebar()

  // Get navigation data from centralized config
  const mainNav = useNavigation('main')
  const adminNav = useNavigation('admin')
  const { sections: platformAdminSections, isSuperAdmin } = useNavigation('platform-admin')

  const isCollapsed = state === 'collapsed'

  const handleNavClick = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        {/* Collapsed state: show A symbol and expand button */}
        {isCollapsed && !isMobile ? (
          <div className="flex flex-col items-center gap-1 p-2">
            <a href="https://ayzer.ai" target="_blank" rel="noopener noreferrer">
              <img src="/A_symbol.svg" alt="AYZER" className="h-8 w-auto dark:invert" />
            </a>
            <button
              onClick={toggleSidebar}
              className="flex h-8 w-8 items-center justify-center rounded-md text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
              aria-label={t('common:sidebar.expandSidebar')}
            >
              <PanelLeft className="size-4" />
            </button>
          </div>
        ) : (
          /* Expanded state: show wordmark logo and collapse button */
          <div className="flex items-center justify-between gap-2 overflow-hidden">
            <SidebarMenu className="flex-1 min-w-0">
              <SidebarMenuItem>
                <SidebarMenuButton size="lg" asChild>
                  <a href="https://ayzer.ai" target="_blank" rel="noopener noreferrer">
                    <img src="/AYZER_wordmark.svg" alt="AYZER" className="h-6 dark:invert" />
                  </a>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
            {!isMobile && (
              <button
                onClick={toggleSidebar}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
                aria-label={t('common:sidebar.collapseSidebar')}
              >
                <PanelLeftClose className="size-4" />
              </button>
            )}
          </div>
        )}
      </SidebarHeader>

      <SidebarContent>
        {/* Main Navigation */}
        {mainNav.sections.map((section) => (
          <SidebarGroup key={section.id}>
            {section.title && (
              <SidebarGroupLabel>{t(section.title)}</SidebarGroupLabel>
            )}
            <SidebarGroupContent>
              <nav>
                <SidebarMenu>
                  {section.items.map((item) => (
                    <SidebarMenuItem key={item.id}>
                      <SidebarMenuButton asChild tooltip={t(item.title)}>
                        <NavLink to={item.url} onClick={handleNavClick}>
                          {({ isActive }) => (
                            <>
                              <item.icon className={isActive ? 'text-sidebar-primary' : ''} />
                              <span>{t(item.title)}</span>
                            </>
                          )}
                        </NavLink>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </nav>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}

        {/* Admin Hub Navigation */}
        {adminNav.sections.length > 0 && (
          <>
            <SidebarSeparator />
            {adminNav.sections.map((section) => (
              <SidebarGroup key={section.id}>
                {section.title && (
                  <SidebarGroupLabel>{t(section.title)}</SidebarGroupLabel>
                )}
                <SidebarGroupContent>
                  <nav>
                    <SidebarMenu>
                      {section.items.map((item) => (
                        <SidebarMenuItem key={item.id}>
                          <SidebarMenuButton asChild tooltip={t(item.title)}>
                            <NavLink to={item.url} onClick={handleNavClick}>
                              {({ isActive }) => (
                                <>
                                  <item.icon className={isActive ? 'text-sidebar-primary' : ''} />
                                  <span>{t(item.title)}</span>
                                </>
                              )}
                            </NavLink>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenu>
                  </nav>
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </>
        )}

        {/* Platform Admin Hub Navigation - Super Admins only */}
        {isSuperAdmin && platformAdminSections.length > 0 && (
          <>
            <SidebarSeparator />
            {platformAdminSections.map((section) => (
              <SidebarGroup key={section.id}>
                {section.title && (
                  <SidebarGroupLabel>{t(section.title)}</SidebarGroupLabel>
                )}
                <SidebarGroupContent>
                  <nav>
                    <SidebarMenu>
                      {section.items.map((item) => (
                        <SidebarMenuItem key={item.id}>
                          <SidebarMenuButton asChild tooltip={t(item.title)}>
                            <NavLink to={item.url} onClick={handleNavClick}>
                              {({ isActive }) => (
                                <>
                                  <item.icon
                                    className={
                                      isActive ? 'text-destructive' : 'text-destructive/70'
                                    }
                                  />
                                  <span className="text-destructive">{t(item.title)}</span>
                                </>
                              )}
                            </NavLink>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenu>
                  </nav>
                </SidebarGroupContent>
              </SidebarGroup>
            ))}
          </>
        )}
      </SidebarContent>
    </Sidebar>
  )
}

// Memoize to prevent re-renders when parent state changes but sidebar props are stable
export const AppSidebar = memo(AppSidebarComponent)
