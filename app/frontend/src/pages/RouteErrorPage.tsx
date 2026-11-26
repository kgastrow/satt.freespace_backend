import { useRouteError, isRouteErrorResponse, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { AlertTriangle, Home, RefreshCw } from 'lucide-react'
import { StaleBuildNotice } from '@/components/StaleBuildNotice'
import { isChunkLoadError } from '@/lib/retryImport'

export function RouteErrorPage() {
  const error = useRouteError()
  const { t } = useTranslation('errors')

  // A chunk this build can no longer fetch is a stale tab, not a crash, and has
  // a fix the user can act on. Checked before the response branch because a
  // failed dynamic import is a plain Error, never a route response.
  if (!isRouteErrorResponse(error) && isChunkLoadError(error)) {
    return <StaleBuildNotice />
  }

  const isResponse = isRouteErrorResponse(error)
  const statusCode = isResponse ? error.status : 500
  const statusText = isResponse
    ? error.statusText
    : t('routeError.unexpectedError')

  const description = isResponse
    ? t(`routeError.status.${statusCode}`, { defaultValue: error.statusText })
    : t('routeError.description')

  const errorMessage =
    error instanceof Error ? error.message : isResponse ? error.data : null

  const errorStack = error instanceof Error ? error.stack : null

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-8 w-8 text-destructive" />
          </div>
          <p className="text-6xl font-bold text-destructive">{statusCode}</p>
          <CardTitle className="text-2xl">{statusText}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <p className="text-muted-foreground">{description}</p>

          {import.meta.env.DEV && errorMessage && (
            <div className="rounded-md bg-destructive/10 p-4 text-left">
              <p className="text-sm font-medium text-destructive">
                {errorMessage}
              </p>
              {errorStack && (
                <ScrollArea className="mt-2 max-h-40">
                  <pre className="text-xs text-muted-foreground">
                    {errorStack}
                  </pre>
                </ScrollArea>
              )}
            </div>
          )}

          <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
            <Button variant="default" asChild>
              <Link to="/">
                <Home className="mr-2 h-4 w-4" />
                {t('routeError.goHome')}
              </Link>
            </Button>
            <Button
              variant="outline"
              onClick={() => window.location.reload()}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('routeError.tryAgain')}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
