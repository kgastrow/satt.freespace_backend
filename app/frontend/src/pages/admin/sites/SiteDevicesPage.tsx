import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { DeviceStatsView } from '@/features/sites/components/DeviceStatsView'
import { useGetSiteDeviceStatsQuery } from '@/features/sites/liveApi'
import { getServerError } from '@/features/sites/errors'
import type { Site } from '@/types/site'

function SiteDevices({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { data, isLoading, error } = useGetSiteDeviceStatsQuery(site.id)

  if (isLoading) return <Skeleton className="h-64 w-full" />
  if (error || !data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('sites:devices.loadError')}</AlertTitle>
        <AlertDescription>{getServerError(error, t).message}</AlertDescription>
      </Alert>
    )
  }
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t('sites:devices.intro')}</p>
      <DeviceStatsView stats={data} />
    </div>
  )
}

export function SiteDevicesPage() {
  return <SiteDetailShell>{(site) => <SiteDevices site={site} />}</SiteDetailShell>
}
