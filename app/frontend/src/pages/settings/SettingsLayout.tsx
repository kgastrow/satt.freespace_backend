import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Menu, Settings } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { SettingsSidebar } from '@/components/settings/SettingsSidebar'
import { PageHeader } from '@/components/PageHeader'

export function SettingsLayout() {
  const { t } = useTranslation('settings')
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('title', 'Settings')}
        description={t('description', 'Manage your account settings and preferences')}
      >
        {isMobile && (
          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon">
                <Menu className="h-4 w-4" />
                <span className="sr-only">{t('openMenu', 'Open menu')}</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72">
              <SheetHeader>
                <SheetTitle className="flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  {t('title', 'Settings')}
                </SheetTitle>
              </SheetHeader>
              <div className="mt-6">
                <SettingsSidebar onNavigate={() => setSheetOpen(false)} />
              </div>
            </SheetContent>
          </Sheet>
        )}
      </PageHeader>

      <div className="flex gap-6">
        {/* Desktop sidebar */}
        {!isMobile && (
          <aside className="w-64 shrink-0">
            <div className="sticky top-6">
              <SettingsSidebar />
            </div>
          </aside>
        )}

        {/* Main content */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
