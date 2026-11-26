import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useAppSelector } from '@/store/hooks'
import { FeedbackForm } from '@/features/feedback/components'
import { buildErrorDiagnostics } from '@/lib/errorDiagnostics'
import { isChunkLoadError } from '@/lib/retryImport'
import { StaleBuildNotice } from '@/components/StaleBuildNotice'

interface ErrorFallbackProps {
  error: Error
  componentStack: string | null
  reset: () => void
}

/**
 * Rich, in-app error page rendered by the error boundary that sits below the
 * Redux/i18n providers. Surfaces the page + component that failed and lets the
 * user file a support item with full diagnostics attached automatically.
 */
export function ErrorFallback({ error, componentStack, reset }: ErrorFallbackProps) {
  const { t } = useTranslation(['common', 'feedback'])
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)
  const [reportOpen, setReportOpen] = useState(false)

  const diagnostics = useMemo(
    () => buildErrorDiagnostics(error, componentStack),
    [error, componentStack],
  )

  const componentName = diagnostics.component ?? t('common:errorBoundary.unknownComponent')

  // Concise, human-readable summary that fits the 2000-char message field.
  // The full structured payload is attached as JSON.
  const reportSubject = t('common:errorBoundary.prefillSubject', {
    message: error.message || error.name,
  }).slice(0, 100)

  const recentActions = diagnostics.breadcrumbs
    .slice(-5)
    .map((b) => `- ${b.label}`)
    .join('\n')

  const reportMessage = [
    t('common:errorBoundary.prefillIntro'),
    '',
    `${t('common:errorBoundary.pageLabel')}: ${diagnostics.page.pathname}`,
    `${t('common:errorBoundary.componentLabel')}: ${componentName}`,
    `${t('common:errorBoundary.errorLabel')}: ${error.name}: ${error.message}`.slice(0, 300),
    '',
    `${t('common:errorBoundary.recentActionsLabel')}:`,
    recentActions || `- ${t('common:errorBoundary.noRecentActions')}`,
    '',
    t('common:errorBoundary.diagnosticsAttachedNote'),
  ].join('\n')

  // A chunk this build can no longer fetch after a deploy is a stale tab, not a
  // crash: there is nothing to report and a fix the user can act on. Placed
  // after the hooks above so the early return does not change the hook order.
  if (isChunkLoadError(error)) {
    return <StaleBuildNotice />
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-paper p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-danger-nc-soft">
            <AlertTriangle className="h-8 w-8 text-danger-nc" strokeWidth={1.5} />
          </div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-danger-nc">
            {t('common:errorBoundary.eyebrow')}
          </p>
          <CardTitle className="font-display text-2xl font-normal tracking-[-0.01em] text-ink">
            {t('common:errorBoundary.title')}
          </CardTitle>
          <CardDescription className="text-ink-2">
            {t('common:errorBoundary.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {/* Auto-captured context, shown so the user sees what will be sent */}
          <div className="flex flex-col gap-1.5 rounded-nc-md bg-surface-2 p-3 text-sm">
            <div className="flex gap-2">
              <span className="shrink-0 text-ink-3">{t('common:errorBoundary.pageLabel')}:</span>
              <span className="truncate font-mono-nc text-ink-2">
                {diagnostics.page.pathname}
              </span>
            </div>
            <div className="flex gap-2">
              <span className="shrink-0 text-ink-3">
                {t('common:errorBoundary.componentLabel')}:
              </span>
              <span className="truncate font-mono-nc text-ink-2">{componentName}</span>
            </div>
          </div>

          {import.meta.env.DEV && (
            <div className="rounded-nc-md bg-danger-nc-soft p-3">
              <p className="text-sm font-medium text-danger-nc">{error.message}</p>
              <ScrollArea className="mt-2 max-h-40">
                <pre className="font-mono-nc text-xs text-ink-3">{error.stack}</pre>
              </ScrollArea>
            </div>
          )}

          <div className="flex flex-col gap-2 sm:flex-row sm:justify-center">
            <Button onClick={reset}>{t('common:errorBoundary.tryAgain')}</Button>
            <Button variant="outline" onClick={() => window.location.reload()}>
              {t('common:errorBoundary.reloadPage')}
            </Button>
            {isAuthenticated && (
              <Button variant="outline" onClick={() => setReportOpen(true)}>
                {t('common:errorBoundary.reportButton')}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {isAuthenticated && (
        <Dialog open={reportOpen} onOpenChange={setReportOpen}>
          <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-md">
            <DialogHeader>
              <DialogTitle>{t('common:errorBoundary.reportDialogTitle')}</DialogTitle>
              <DialogDescription>
                {t('common:errorBoundary.reportDialogDescription')}
              </DialogDescription>
            </DialogHeader>
            <div className="mt-2">
              <FeedbackForm
                onSuccess={() => setReportOpen(false)}
                defaultValues={{
                  type: 'bug',
                  subject: reportSubject,
                  message: reportMessage,
                }}
                diagnostics={diagnostics}
              />
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
