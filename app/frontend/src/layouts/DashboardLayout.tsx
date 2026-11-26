import { Outlet } from 'react-router-dom'
import { Menu } from 'lucide-react'
import { SidebarProvider, SidebarInset, useSidebar } from '@/components/ui/sidebar'
import { AppSidebar } from '@/components/AppSidebar'
import { usePreferences } from '@/features/preferences'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { NotificationBell } from '@/components/NotificationBell'
import { AnnouncementBanner } from '@/components/AnnouncementBanner'
import { HeaderUserMenu } from '@/components/HeaderUserMenu'
import { ImpersonationIndicator } from '@/components/ImpersonationIndicator'
import { ScrollArea } from '@/components/ui/scroll-area'
import { DeletionPendingBanner } from '@/components/DeletionPendingBanner'
import { TwoFactorEnforcement } from '@/components/TwoFactorEnforcement'

function MobileHeader() {
  const { toggleSidebar } = useSidebar()

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4 md:hidden">
      <Button
        variant="ghost"
        size="icon"
        className="-ml-1 h-10 w-10 shrink-0"
        onClick={toggleSidebar}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </Button>
      <AnnouncementBanner />
      <div className="flex-1" />
      <ImpersonationIndicator />
      <ThemeToggle />
      <LanguageSwitcher />
      <NotificationBell />
      <HeaderUserMenu />
    </header>
  )
}

function DesktopHeader() {
  return (
    <header className="hidden md:flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <AnnouncementBanner />
      <div className="flex-1" />
      <ImpersonationIndicator />
      <ThemeToggle />
      <LanguageSwitcher />
      <NotificationBell />
      <HeaderUserMenu />
    </header>
  )
}

export function DashboardLayout() {
  const { sidebarCollapsed, setSidebarCollapsed } = usePreferences()

  return (
    <SidebarProvider
      open={!sidebarCollapsed}
      onOpenChange={(open) => setSidebarCollapsed(!open)}
    >
      <AppSidebar />
      <SidebarInset className="flex h-full flex-col">
        <TwoFactorEnforcement>
          <DeletionPendingBanner />
          <MobileHeader />
          <DesktopHeader />
          {/* Main content */}
          <ScrollArea className="flex-1 h-0">
            <main className="p-4 md:p-6">
              <Outlet />
            </main>
          </ScrollArea>
        </TwoFactorEnforcement>
      </SidebarInset>
    </SidebarProvider>
  )
}
