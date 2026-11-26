import { useEffect } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import { AuthProvider } from '@/components/AuthProvider'
import { MaintenanceProvider } from '@/components/MaintenanceProvider'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorFallback } from '@/components/ErrorFallback'
import { useAppSelector } from '@/store/hooks'
import { FeedbackWidget } from '@/features/feedback/components'
import {
  installBreadcrumbCollectors,
  recordBreadcrumb,
} from '@/lib/errorBreadcrumbs'

function RootLayoutContent() {
  const isImpersonating = useAppSelector((state) => state.impersonation.isImpersonating)
  const location = useLocation()

  // Collect lightweight activity breadcrumbs to enrich error reports.
  useEffect(() => {
    installBreadcrumbCollectors()
  }, [])

  useEffect(() => {
    recordBreadcrumb('navigation', `Navigated to ${location.pathname}`)
  }, [location.pathname])

  return (
    <div
      className={`flex h-screen flex-col bg-background ${
        isImpersonating ? 'ring-4 ring-inset ring-yellow-500' : ''
      }`}
    >
      <div className="flex-1 overflow-hidden">
        <ErrorBoundary
          renderFallback={({ error, componentStack, reset }) => (
            <ErrorFallback error={error} componentStack={componentStack} reset={reset} />
          )}
        >
          <Outlet />
        </ErrorBoundary>
      </div>
      <Toaster />
      <FeedbackWidget />
    </div>
  )
}

export function RootLayout() {
  return (
    <AuthProvider>
      <MaintenanceProvider>
        <RootLayoutContent />
      </MaintenanceProvider>
    </AuthProvider>
  )
}
