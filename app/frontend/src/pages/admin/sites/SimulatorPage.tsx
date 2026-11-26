import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { SimulatorPanel } from '@/features/sites/components/SimulatorPanel'
import { useGetSiteLiveQuery } from '@/features/sites/liveApi'
import { useGetMockStatusQuery } from '@/features/sites/mockApi'
import { useGetSitesQuery } from '@/features/sites/sitesApi'
import { getServerError } from '@/features/sites/errors'

function SimulatorBody() {
  const { t } = useTranslation(['sites', 'backend'])
  const { data: sites } = useGetSitesQuery({ limit: 100 })
  const [siteId, setSiteId] = useState('')
  const site = sites?.items.find((s) => s.id === siteId)
  const { data: live, error } = useGetSiteLiveQuery(siteId, { skip: !siteId })

  return (
    <div className="space-y-6">
      <Alert>
        <AlertDescription>{t('sites:simulator.notice')}</AlertDescription>
      </Alert>
      <div className="max-w-sm space-y-2">
        <Label htmlFor="simulator-site">{t('sites:simulator.site')}</Label>
        <Select value={siteId} onValueChange={setSiteId}>
          <SelectTrigger id="simulator-site">
            <SelectValue placeholder={t('sites:simulator.sitePlaceholder')} />
          </SelectTrigger>
          <SelectContent>
            {(sites?.items ?? []).map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertTitle>{t('sites:live.loadError')}</AlertTitle>
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      )}
      {site && live && <SimulatorPanel key={site.id} site={site} initial={live} />}
      {site && !live && !error && <Skeleton className="h-64 w-full" />}
    </div>
  )
}

/**
 * Demonstration simulator (BF-84, section 13.1). Exists only when the backend
 * runs in mock mode: GET /mock/status answers 404 otherwise and the page says
 * it is not available.
 */
export function SimulatorPage() {
  const { t } = useTranslation('sites')
  const { data: status, isLoading } = useGetMockStatusQuery()

  return (
    <div className="space-y-6">
      <PageHeader title={t('simulator.title')} description={t('simulator.description')} />
      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : status?.enabled ? (
        <SimulatorBody />
      ) : (
        <Alert data-testid="simulator-unavailable">
          <AlertTitle>{t('simulator.unavailable.title')}</AlertTitle>
          <AlertDescription>{t('simulator.unavailable.description')}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}
