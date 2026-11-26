import { Spinner } from '@/components/ui/spinner'

/**
 * Full-page loading indicator for route code splitting.
 * Displayed as Suspense fallback while lazy-loaded page components are being fetched.
 */
export function PageLoader() {
  return (
    <div className="flex h-full min-h-[200px] items-center justify-center">
      <Spinner size="lg" className="text-muted-foreground" />
    </div>
  )
}
