/**
 * The one way to lazy-load a route in this app.
 *
 * Every route fragment used to declare its own `lazyNamed`/`LazyPage` pair, and
 * only `router.tsx`'s copy retried a failed chunk fetch. That left every route
 * declared in `config/routes.ts` and `routes/settingsRoutes.tsx` — the whole
 * admin and settings surface — with no recovery at all when a deploy removed
 * the chunk it was about to load. Import from here so a route cannot opt out of
 * that by accident.
 */
import { lazy, Suspense, type ComponentType, type ReactNode } from 'react'
import { PageLoader } from '@/components/PageLoader'
import { retryImport } from '@/lib/retryImport'

/** Lazy-load a page exported under `name`, with post-deploy chunk recovery. */
export const lazyNamed = <T extends ComponentType<object>>(
  importFn: () => Promise<Record<string, T>>,
  name: string
) => lazy(() => retryImport(importFn).then((m) => ({ default: m[name] as T })))

export function LazyPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}
