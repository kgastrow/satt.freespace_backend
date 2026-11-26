import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Menu, Shield } from 'lucide-react'
import { useIsMobile } from '@/hooks/use-mobile'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { AdminSidebar } from '@/components/admin/AdminSidebar'
import { PageHeader } from '@/components/PageHeader'

export function AdminLayout() {
  const { t } = useTranslation('admin')
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('title', 'Administration')}
        description={t('description', 'Manage organization settings and users')}
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
                  <Shield className="h-5 w-5" />
                  {t('title', 'Administration')}
                </SheetTitle>
              </SheetHeader>
              <div className="mt-6">
                <AdminSidebar onNavigate={() => setSheetOpen(false)} />
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
              <AdminSidebar />
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
