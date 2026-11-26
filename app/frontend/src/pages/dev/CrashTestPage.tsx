import { useState } from 'react'
import { Button } from '@/components/ui/button'

/**
 * DEV-ONLY page for exercising the app ErrorBoundary / ErrorFallback. It is
 * only registered as a route when `import.meta.env.DEV` is true (see router),
 * so it never ships to production and is intentionally not internationalised.
 *
 * Clicking the button records a click breadcrumb and then throws during the
 * next render, so the resulting error report shows a realistic breadcrumb trail.
 */
function Boom(): never {
  throw new Error('Intentional render error from the dev crash-test page')
}

export function CrashTestPage() {
  const [crash, setCrash] = useState(false)

  if (crash) {
    return <Boom />
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-paper p-4">
      <div className="max-w-md space-y-4 text-center">
        <h1 className="font-display text-2xl text-ink">Error boundary test</h1>
        <p className="text-sm text-ink-2">
          Dev-only tool. Click below to throw a render error and see the error
          page. Navigate around and click a few things first to populate the
          breadcrumb trail.
        </p>
        <Button variant="destructive" onClick={() => setCrash(true)}>
          Trigger render error
        </Button>
      </div>
    </div>
  )
}
