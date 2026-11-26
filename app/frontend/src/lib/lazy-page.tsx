import { lazy, Suspense, type ComponentType, type JSX, type LazyExoticComponent } from 'react'
import { PageLoader } from '@/components/PageLoader'
import { retryImport } from '@/lib/retryImport'

/**
 * Helper to create a lazy-loaded page component with Suspense wrapper.
 *
 * Handles the common pattern of importing a named export from a page module
 * and wrapping it with Suspense for code splitting.
 *
 * @param importFn - Dynamic import function that returns a module with a named export
 * @param componentName - The name of the exported component in the module
 * @returns A wrapped lazy component with Suspense fallback
 *
 * @example
 * ```tsx
 * // For a named export: export function LoginPage() { ... }
 * const LoginPage = lazyPage(() => import('@/pages/LoginPage'), 'LoginPage')
 *
 * // Use in router
 * { path: 'login', element: <LoginPage /> }
 * ```
 */
export function lazyPage(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  importFn: () => Promise<Record<string, ComponentType<any>>>,
  componentName: string
): () => JSX.Element {
  const LazyComponent = lazy(() =>
    retryImport(importFn).then((module) => ({ default: module[componentName] }))
  )

  // Return a component that wraps the lazy component with Suspense
  return function LazyPageWrapper() {
    return (
      <Suspense fallback={<PageLoader />}>
        <LazyComponent />
      </Suspense>
    )
  }
}

/**
 * Alternative helper for default exports.
 *
 * @param importFn - Dynamic import function that returns a module with default export
 * @returns A wrapped lazy component with Suspense fallback
 *
 * @example
 * ```tsx
 * const HomePage = lazyPageDefault(() => import('@/pages/HomePage'))
 * ```
 */
export function lazyPageDefault(
  importFn: () => Promise<{ default: ComponentType }>
): () => JSX.Element {
  const LazyComponent = lazy(() => retryImport(importFn))

  return function LazyPageWrapper() {
    return (
      <Suspense fallback={<PageLoader />}>
        <LazyComponent />
      </Suspense>
    )
  }
}

/**
 * Create a lazy component without the wrapper function (for use with React Router's lazy).
 * Returns the LazyExoticComponent directly for advanced use cases.
 *
 * @param importFn - Dynamic import function
 * @param componentName - The named export to use
 * @returns LazyExoticComponent
 */
export function createLazyComponent<T extends ComponentType<object>>(
  importFn: () => Promise<Record<string, T>>,
  componentName: string
): LazyExoticComponent<T> {
  return lazy(() =>
    retryImport(importFn).then((module) => ({ default: module[componentName] as T }))
  )
}
