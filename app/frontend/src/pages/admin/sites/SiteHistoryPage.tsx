import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { MAX_CHART_ZONES, OccupancyChart } from '@/features/sites/components/OccupancyChart'
import { useGetSiteHistoryQuery } from '@/features/sites/liveApi'
import { shapeHistory, shiftDay, todayInZone } from '@/features/sites/historySeries'
import { getServerError } from '@/features/sites/errors'
import type { Site } from '@/types/site'

function SiteHistory({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const today = todayInZone(site.time_zone)
  const [day, setDay] = useState(today)
  const { data, isLoading, isFetching, error } = useGetSiteHistoryQuery({
    siteId: site.id,
    date: day,
  })

  const shaped = useMemo(
    () => (data ? shapeHistory(data, { maxZones: MAX_CHART_ZONES }) : null),
    [data]
  )
  const hiddenZones = data ? Math.max(0, data.zones.length - MAX_CHART_ZONES) : 0
  const maxDate = useMemo(() => {
    const [y, m, d] = today.split('-').map(Number)
    return new Date(y, m - 1, d)
  }, [today])

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('sites:history.title')}</CardTitle>
        <CardDescription>
          {t('sites:history.description', { timeZone: site.time_zone })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label={t('sites:history.previousDay')}
            onClick={() => setDay((d) => shiftDay(d, -1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <div className="space-y-2">
            <Label>{t('sites:history.day')}</Label>
            <DatePicker
              value={day}
              onChange={(v) => v && setDay(v)}
              maxDate={maxDate}
              dateFormat="PP"
              placeholder={t('sites:history.pickDay')}
            />
          </div>
          <Button
            variant="outline"
            size="icon"
            aria-label={t('sites:history.nextDay')}
            disabled={day >= today}
            onClick={() => setDay((d) => shiftDay(d, 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          {day !== today && (
            <Button variant="ghost" onClick={() => setDay(today)}>
              {t('sites:history.today')}
            </Button>
          )}
        </div>

        {error ? (
          <Alert variant="destructive">
            <AlertTitle>{t('sites:history.loadError')}</AlertTitle>
            <AlertDescription>{getServerError(error, t).message}</AlertDescription>
          </Alert>
        ) : isLoading || !data || !shaped ? (
          <Skeleton className="h-80 w-full" />
        ) : shaped.empty ? (
          <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground" data-testid="history-empty">
            {t('sites:history.empty')}
          </p>
        ) : (
          <div className={isFetching ? 'opacity-60 transition-opacity' : undefined}>
            <OccupancyChart
              shaped={shaped}
              siteName={site.name}
              timeZone={data.time_zone}
              triggerPct={data.trigger_pct}
              resetPct={data.reset_pct}
            />
            <p className="mt-2 text-sm text-muted-foreground">{t('sites:history.gapNote')}</p>
            {hiddenZones > 0 && (
              <p className="text-sm text-muted-foreground">
                {t('sites:history.zonesNotPlotted', { count: hiddenZones })}
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function SiteHistoryPage() {
  return <SiteDetailShell>{(site) => <SiteHistory site={site} />}</SiteDetailShell>
}
