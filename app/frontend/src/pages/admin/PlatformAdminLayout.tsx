import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Menu, ShieldAlert } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { PlatformAdminSidebar } from '@/components/admin/PlatformAdminSidebar'
import { SuperAdminGuard } from '@/components/SuperAdminGuard'

export function PlatformAdminLayout() {
  const { t } = useTranslation('platformAdmin')
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <SuperAdminGuard>
      <div className="space-y-6">
        <div className="border-l-4 border-destructive pl-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-destructive">
                {t('title', 'Platform Administration')}
              </h1>
              <p className="text-muted-foreground">
                {t('description', 'Manage platform-wide settings and configurations')}
              </p>
            </div>
            {isMobile && (
              <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
                <SheetTrigger asChild>
                  <Button variant="outline" size="icon" className="border-destructive/50">
                    <Menu className="h-4 w-4" />
                    <span className="sr-only">{t('openMenu', 'Open menu')}</span>
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" className="w-72">
                  <SheetHeader>
                    <SheetTitle className="flex items-center gap-2 text-destructive">
                      <ShieldAlert className="h-5 w-5" />
                      {t('title', 'Platform Administration')}
                    </SheetTitle>
                  </SheetHeader>
                  <div className="mt-6">
                    <PlatformAdminSidebar onNavigate={() => setSheetOpen(false)} />
                  </div>
                </SheetContent>
              </Sheet>
            )}
          </div>
        </div>

        <div className="flex gap-6">
          {/* Desktop sidebar */}
          {!isMobile && (
            <aside className="w-64 shrink-0">
              <div className="sticky top-6">
                <PlatformAdminSidebar />
              </div>
            </aside>
          )}

          {/* Main content */}
          <main className="flex-1 min-w-0">
            <Outlet />
          </main>
        </div>
      </div>
    </SuperAdminGuard>
  )
}
