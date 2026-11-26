import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Star } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { AgeText } from '@/features/sites/components/AgeText'
import {
  EngineStateBadge,
  StaleBadge,
  ZoneStatusBadge,
} from '@/features/sites/components/LiveBadges'
import { useGetSiteLiveQuery } from '@/features/sites/liveApi'
import { usePollingInterval } from '@/features/sites/usePolling'
import { describeEngineTimers, formatDayClock } from '@/features/sites/engineTimers'
import { getServerError } from '@/features/sites/errors'
import type { Site } from '@/types/site'
import type { SiteLiveResponse } from '@/types/siteLive'

function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(id)
  }, [intervalMs])
  return now
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-lg font-semibold">{children}</dd>
    </div>
  )
}

function ZoneTable({ live }: { live: SiteLiveResponse }) {
  const { t } = useTranslation('sites')
  const { availability } = live
  const dash = <span className="text-muted-foreground">-</span>
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('live.zones.title')}</CardTitle>
        <CardDescription>{t('live.zones.description')}</CardDescription>
      </CardHeader>
      <CardContent>
        {availability.zones.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('live.zones.empty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('live.zones.zone')}</TableHead>
                <TableHead>{t('live.zones.status')}</TableHead>
                <TableHead className="text-right">{t('live.zones.free')}</TableHead>
                <TableHead className="text-right">{t('live.zones.occupancy')}</TableHead>
                <TableHead>{t('live.zones.updated')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {availability.zones.map((zone) => {
                const recommended = zone.id === availability.recommended_zone_id
                return (
                  <TableRow
                    key={zone.id}
                    data-testid={`zone-row-${zone.id}`}
                    data-enabled={zone.enabled}
                    className={cn(!zone.enabled && 'bg-muted/40 text-muted-foreground italic')}
                  >
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{zone.name}</span>
                        {recommended && (
                          <Badge className="gap-1">
                            <Star className="h-3 w-3" aria-hidden />
                            {t('live.zones.recommended')}
                          </Badge>
                        )}
                        {!zone.enabled && (
                          <Badge variant="outline">{t('live.zones.notEnabled')}</Badge>
                        )}
                        {zone.enabled && !zone.recommendable && (
                          <Badge variant="outline">{t('live.zones.notRecommendable')}</Badge>
                        )}
                      </div>
                      <code className="text-xs text-muted-foreground not-italic">{zone.id}</code>
                    </TableCell>
                    <TableCell>
                      <ZoneStatusBadge status={zone.status} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {zone.free === null ? dash : zone.free}
                      {zone.capacity !== null && (
                        <span className="text-muted-foreground"> / {zone.capacity}</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {zone.occupancy_pct === null ? dash : `${zone.occupancy_pct}%`}
                    </TableCell>
                    <TableCell>
                      {zone.stale ? (
                        <StaleBadge stale />
                      ) : (
                        formatDayClock(zone.as_of, live.site.time_zone) ?? dash
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

function EnginePanel({ live, now }: { live: SiteLiveResponse; now: number }) {
  const { t } = useTranslation('sites')
  const { engine, site, availability } = live
  const zoneName = (slug: string | null) =>
    slug ? availability.zones.find((z) => z.id === slug)?.name ?? slug : null
  const timers = describeEngineTimers(engine, now, site.time_zone)
  const lastZone = zoneName(engine?.last_notified_zone_slug ?? null)
  const advisories = engine?.zone_advisories ?? []

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('live.engine.title')}</CardTitle>
        <CardDescription>
          {t('live.engine.description', { trigger: site.trigger_pct, reset: site.reset_pct })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <EngineStateBadge state={engine?.state ?? null} />
          <div className="text-sm" data-testid="engine-timers">
            {timers.map((line) => (
              <p key={line.key}>{t(line.key, line.values)}</p>
            ))}
          </div>
        </div>

        {engine?.inflight && (
          <Alert>
            <AlertTitle>{t('live.engine.inflight.title')}</AlertTitle>
            <AlertDescription>{t('live.engine.inflight.description')}</AlertDescription>
          </Alert>
        )}

        <dl className="grid gap-4 sm:grid-cols-2">
          <Metric label={t('live.engine.lastNotified')}>
            {engine?.last_notified_pct == null ? (
              <span className="text-base font-normal text-muted-foreground">
                {t('live.engine.neverNotified')}
              </span>
            ) : (
              <span className="text-base font-normal">
                {t('live.engine.lastNotifiedValue', {
                  pct: engine.last_notified_pct,
                  at: formatDayClock(engine.last_sent_at, site.time_zone) ?? '-',
                })}
              </span>
            )}
          </Metric>
          <Metric label={t('live.engine.lastRecommendation')}>
            <span className="text-base font-normal">
              {lastZone ?? <span className="text-muted-foreground">{t('live.none')}</span>}
              {engine && engine.last_notified_top_zones.length > 0 && (
                <span className="block text-sm text-muted-foreground">
                  {t('live.engine.topZones', {
                    zones: engine.last_notified_top_zones.map((s) => zoneName(s) ?? s).join(', '),
                  })}
                </span>
              )}
            </span>
          </Metric>
        </dl>

        {advisories.length > 0 && (
          <div className="space-y-1">
            <h4 className="text-sm font-medium">{t('live.engine.zoneAdvisories')}</h4>
            <ul className="space-y-1 text-sm">
              {advisories.map((a) => (
                <li key={a.zone}>
                  {t(a.advised ? 'live.engine.advisoryAdvised' : 'live.engine.advisoryWatching', {
                    zone: zoneName(a.zone) ?? a.zone,
                    since: formatDayClock(a.above_since, site.time_zone) ?? '-',
                  })}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function SiteLive({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { data: live, isLoading, error } = useGetSiteLiveQuery(site.id, {
    pollingInterval: usePollingInterval(),
  })
  const now = useNow()

  if (isLoading) return <Skeleton className="h-96 w-full" />
  if (error || !live) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('sites:live.loadError')}</AlertTitle>
        <AlertDescription>{getServerError(error, t).message}</AlertDescription>
      </Alert>
    )
  }

  const { availability } = live
  const recommended = availability.zones.find((z) => z.id === availability.recommended_zone_id)

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t('sites:live.intro')}</p>

      <Card>
        <CardContent className="pt-6">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label={t('sites:live.totals.occupancy')}>
              {availability.occupancy_pct === null ? '-' : `${availability.occupancy_pct}%`}
              <span className="block text-sm font-normal text-muted-foreground">
                {t('sites:live.totals.bays', {
                  occupied: availability.occupied ?? 0,
                  capacity: availability.capacity ?? 0,
                })}
              </span>
            </Metric>
            <Metric label={t('sites:live.totals.free')}>
              {availability.free_usable ?? '-'}
            </Metric>
            <Metric label={t('sites:live.totals.dataAge')}>
              <span className="flex flex-wrap items-center gap-2">
                <AgeText seconds={availability.age_seconds} />
                <StaleBadge stale={availability.stale} />
              </span>
            </Metric>
            <Metric label={t('sites:live.totals.recommendation')}>
              {recommended ? (
                recommended.name
              ) : (
                <span className="text-base font-normal text-muted-foreground">{t('sites:live.none')}</span>
              )}
            </Metric>
          </dl>
        </CardContent>
      </Card>

      <ZoneTable live={live} />
      <EnginePanel live={live} now={now} />
    </div>
  )
}

export function SiteLivePage() {
  return <SiteDetailShell>{(site) => <SiteLive site={site} />}</SiteDetailShell>
}
