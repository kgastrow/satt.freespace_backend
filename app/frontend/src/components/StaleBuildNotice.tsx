import { useTranslation } from 'react-i18next'
import { RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { applyUpdate } from '@/lib/swUpdate'

/**
 * Shown instead of a generic crash screen when the thing that actually failed
 * was a chunk this build can no longer fetch.
 *
 * After a deploy, a long-lived tab still references chunk hashes the origin has
 * removed. `retryImport` recovers most of these silently; what reaches here is
 * the case where a reload has already been tried once. "Something went wrong"
 * is true but useless — the user can't act on it, and it reads as a broken app
 * rather than a stale tab. This says what happened and offers the one fix.
 *
 * `applyUpdate` rather than a bare reload: if a newer worker is staged this
 * promotes it, so the reload lands on the build that has the missing chunk.
 */
export function StaleBuildNotice() {
  const { t } = useTranslation('errors')

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-lg">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
            <RefreshCw className="h-8 w-8 text-primary" />
          </div>
          <CardTitle className="text-2xl">{t('staleBuild.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-center">
          <p className="text-muted-foreground">{t('staleBuild.description')}</p>
          <Button variant="default" onClick={() => void applyUpdate()}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('staleBuild.action')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
