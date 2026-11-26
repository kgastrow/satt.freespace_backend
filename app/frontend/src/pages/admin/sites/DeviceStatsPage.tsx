import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { DeviceStatsView } from '@/features/sites/components/DeviceStatsView'
import { useGetAllDeviceStatsQuery } from '@/features/sites/liveApi'
import { getServerError } from '@/features/sites/errors'

/** Section-level device statistics across every site the user may see. */
export function DeviceStatsPage() {
  const { t } = useTranslation(['sites', 'backend'])
  const { data, isLoading, error } = useGetAllDeviceStatsQuery()

  return (
    <div className="space-y-6">
      <PageHeader title={t('sites:devices.title')} description={t('sites:devices.description')} />
      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : error || !data ? (
        <Alert variant="destructive">
          <AlertTitle>{t('sites:devices.loadError')}</AlertTitle>
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      ) : (
        <DeviceStatsView stats={data} showSites />
      )}
    </div>
  )
}
