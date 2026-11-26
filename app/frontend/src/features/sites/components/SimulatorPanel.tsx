import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCircle2, CircleAlert, Clock, Play, RotateCcw, Send } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { getErrorMessage } from '@/types/api'
import { useGetSiteEventsQuery } from '../eventsApi'
import { useGetSiteLiveQuery } from '../liveApi'
import {
  useGetMockStatusQuery,
  usePostMockClockMutation,
  usePostMockOccupancyMutation,
} from '../mockApi'
import {
  buildOccupancyRequest,
  buildPreset,
  matchExpectation,
  observedFromLive,
  PRESET_IDS,
  simZonesFromLive,
  snapshotFromSpec,
  type MatchResult,
  type Observed,
  type Preset,
} from '../simulatorPresets'
import { formatDayClock } from '../engineTimers'
import { EngineStateBadge, StaleBadge } from './LiveBadges'
import type { Site } from '@/types/site'
import type { Health, SiteLiveResponse } from '@/types/siteLive'

interface Row {
  capacity: number
  occupied: number
  health: Health
}

const HEALTH: Health[] = ['OK', 'PARTIAL', 'OFFLINE']
const intOr = (value: string, fallback = 0) => {
  const n = Number.parseInt(value, 10)
  return Number.isNaN(n) || n < 0 ? fallback : n
}

interface PresetRun {
  preset: Preset
  next: number
  observed: Array<{ observed: Observed; match: MatchResult }>
}

/** Everything the simulator does for one site; mounted per site (and live view) so form state starts from the live figures. */
export function SimulatorPanel({ site, initial }: { site: Site; initial: SiteLiveResponse }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { data: status } = useGetMockStatusQuery()
  const { data: live = initial, refetch: refetchLive } = useGetSiteLiveQuery(site.id, {
    pollingInterval: 5000,
  })
  const { data: events } = useGetSiteEventsQuery({ siteId: site.id, query: { limit: 8 } })
  const [postOccupancy, { isLoading: posting }] = usePostMockOccupancyMutation()
  const [postClock, { isLoading: moving }] = usePostMockClockMutation()

  const simZones = simZonesFromLive(initial.availability.zones)
  const [siteRow, setSiteRow] = useState<Row>(() => ({
    capacity: initial.availability.capacity ?? 200,
    occupied: initial.availability.occupied ?? 0,
    health: 'OK',
  }))
  const [zoneRows, setZoneRows] = useState<Record<string, Row>>(() =>
    Object.fromEntries(
      initial.availability.zones.map((z) => [
        z.id,
        { capacity: z.capacity ?? 50, occupied: z.occupied ?? 0, health: 'OK' as Health },
      ])
    )
  )
  const [message, setMessage] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [run, setRun] = useState<PresetRun | null>(null)
  const [running, setRunning] = useState(false)

  const observed = observedFromLive(live)

  const fail = (err: unknown) => setMessage({ kind: 'error', text: getErrorMessage(err, t) })

  const postManual = async () => {
    setMessage(null)
    try {
      const body = buildOccupancyRequest(
        site.slug,
        siteRow,
        simZones.map((z) => ({
          zoneId: z.slug,
          name: z.name,
          ...(zoneRows[z.slug] ?? { capacity: z.capacity, occupied: 0, health: 'OK' as Health }),
        }))
      )
      const result = await postOccupancy({ slug: site.slug, body }).unwrap()
      setMessage({
        kind: 'ok',
        text: result.ignored
          ? t('sites:simulator.ignored', { reason: result.ignored })
          : t('sites:simulator.posted'),
      })
    } catch (err) {
      fail(err)
    }
  }

  const moveClock = async (arg: { seconds: number } | { reset: true }) => {
    setMessage(null)
    try {
      await postClock(arg).unwrap()
    } catch (err) {
      fail(err)
    }
  }

  const startPreset = (id: string) => {
    const preset = buildPreset(id, {
      triggerPct: live.site.trigger_pct,
      resetPct: live.site.reset_pct,
      stabilisationS: live.site.stabilisation_s,
      staleLimitS: live.site.stale_limit_s,
    })
    setMessage(null)
    setRun(preset ? { preset, next: 0, observed: [] } : null)
  }

  const runNextStep = async () => {
    if (!run || run.next >= run.preset.steps.length) return
    const step = run.preset.steps[run.next]
    setRunning(true)
    setMessage(null)
    try {
      if (step.advanceSeconds) await postClock({ seconds: step.advanceSeconds }).unwrap()
      if (step.snapshot) {
        const capacity = live.availability.capacity ?? siteRow.capacity
        await postOccupancy({
          slug: site.slug,
          body: snapshotFromSpec(site.slug, capacity, simZones, step.snapshot),
        }).unwrap()
      }
      const fresh = await refetchLive().unwrap()
      const seen = observedFromLive(fresh)
      setRun({
        ...run,
        next: run.next + 1,
        observed: [...run.observed, { observed: seen, match: matchExpectation(step.expected, seen) }],
      })
    } catch (err) {
      fail(err)
    } finally {
      setRunning(false)
    }
  }

  const recommended = live.availability.zones.find((z) => z.id === live.availability.recommended_zone_id)
  const busy = posting || moving || running

  return (
    <div className="space-y-6">
      {message && (
        <Alert variant={message.kind === 'error' ? 'destructive' : 'default'} role={message.kind === 'error' ? 'alert' : 'status'}>
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>{t('sites:simulator.result.title')}</CardTitle>
          <CardDescription>{t('sites:simulator.result.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="simulator-observed">
            <div>
              <dt className="text-sm text-muted-foreground">{t('sites:simulator.result.state')}</dt>
              <dd><EngineStateBadge state={observed.state} /></dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">{t('sites:simulator.result.data')}</dt>
              <dd><StaleBadge stale={observed.stale} /></dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">{t('sites:simulator.result.recommendation')}</dt>
              <dd>{recommended?.name ?? <span className="text-muted-foreground">{t('sites:live.none')}</span>}</dd>
            </div>
            <div>
              <dt className="text-sm text-muted-foreground">{t('sites:simulator.result.mockTime')}</dt>
              <dd className="tabular-nums">
                {formatDayClock(status?.mockTime, live.site.time_zone) ?? '-'}
              </dd>
            </div>
          </dl>
          <div>
            <h4 className="mb-1 text-sm font-medium">{t('sites:simulator.result.recentEvents')}</h4>
            {(events?.items ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">{t('sites:simulator.result.noEvents')}</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {events?.items.map((e) => (
                  <li key={e.id} className="flex flex-wrap items-center gap-2">
                    <span className="tabular-nums text-muted-foreground">
                      {formatDayClock(e.occurred_at, live.site.time_zone)}
                    </span>
                    <Badge variant="outline">{t(`sites:events.types.${e.type}`, { defaultValue: e.type })}</Badge>
                    {e.reason && <span>{t(`sites:events.reasons.${e.reason}`, { defaultValue: e.reason })}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('sites:simulator.presets.title')}</CardTitle>
          <CardDescription>{t('sites:simulator.presets.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {PRESET_IDS.map((id) => (
              <Button
                key={id}
                variant={run?.preset.id === id ? 'default' : 'outline'}
                size="sm"
                disabled={busy}
                onClick={() => startPreset(id)}
              >
                {id}
              </Button>
            ))}
          </div>
          {run && (
            <div className="space-y-3" data-testid="preset-run">
              <div>
                <h4 className="font-medium">
                  {run.preset.id}: {t(run.preset.titleKey)}
                </h4>
                <p className="text-sm text-muted-foreground">{t(run.preset.descriptionKey)}</p>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">{t('sites:simulator.presets.step')}</TableHead>
                    <TableHead>{t('sites:simulator.presets.action')}</TableHead>
                    <TableHead>{t('sites:simulator.presets.expected')}</TableHead>
                    <TableHead>{t('sites:simulator.presets.observed')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {run.preset.steps.map((step, index) => {
                    const result = run.observed[index]
                    return (
                      <TableRow key={step.id} data-testid={`preset-step-${index}`} className={index === run.next ? 'bg-muted/50' : undefined}>
                        <TableCell className="tabular-nums">{index + 1}</TableCell>
                        <TableCell className="text-sm">
                          {step.advanceSeconds
                            ? t('sites:simulator.presets.advance', { seconds: step.advanceSeconds })
                            : null}{' '}
                          {step.snapshot
                            ? t('sites:simulator.presets.snapshot', { pct: step.snapshot.sitePct })
                            : null}
                        </TableCell>
                        <TableCell className="text-sm">{t(step.expectedKey, step.values)}</TableCell>
                        <TableCell className="text-sm">
                          {result ? (
                            <span className="flex flex-wrap items-center gap-2">
                              {result.match === 'match' && <CheckCircle2 className="h-4 w-4 text-green-600" aria-hidden />}
                              {result.match === 'differs' && <CircleAlert className="h-4 w-4 text-amber-600" aria-hidden />}
                              <span data-testid={`preset-match-${index}`}>
                                {t(`sites:simulator.presets.match.${result.match}`)}
                              </span>
                              <span className="text-muted-foreground">
                                {t('sites:simulator.presets.observedValue', {
                                  state: t(`sites:engineState.${result.observed.state}`),
                                  stale: result.observed.stale ? t('sites:live.stale') : t('sites:live.fresh'),
                                  recommendation: result.observed.recommendedZoneId ?? t('sites:live.none'),
                                })}
                              </span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground">-</span>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
              <div className="flex gap-2">
                <Button onClick={runNextStep} disabled={busy || run.next >= run.preset.steps.length}>
                  <Play className="mr-2 h-4 w-4" />
                  {run.next >= run.preset.steps.length
                    ? t('sites:simulator.presets.done')
                    : t('sites:simulator.presets.runNext', { n: run.next + 1 })}
                </Button>
                <Button variant="ghost" disabled={busy} onClick={() => startPreset(run.preset.id)}>
                  <RotateCcw className="mr-2 h-4 w-4" />
                  {t('sites:simulator.presets.restart')}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('sites:simulator.clock.title')}</CardTitle>
          <CardDescription>{t('sites:simulator.clock.description')}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          {[60, 300, 1800].map((seconds) => (
            <Button key={seconds} variant="outline" disabled={busy} onClick={() => moveClock({ seconds })}>
              <Clock className="mr-2 h-4 w-4" />
              {t('sites:simulator.clock.advance', { minutes: seconds / 60 })}
            </Button>
          ))}
          <Button variant="outline" disabled={busy} onClick={() => moveClock({ reset: true })}>
            <RotateCcw className="mr-2 h-4 w-4" />
            {t('sites:simulator.clock.reset')}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('sites:simulator.snapshot.title')}</CardTitle>
          <CardDescription>{t('sites:simulator.snapshot.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('sites:simulator.snapshot.area')}</TableHead>
                <TableHead>{t('sites:simulator.snapshot.capacity')}</TableHead>
                <TableHead>{t('sites:simulator.snapshot.occupied')}</TableHead>
                <TableHead>{t('sites:simulator.snapshot.health')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <FigureRow
                id="site"
                label={t('sites:simulator.snapshot.siteTotals')}
                row={siteRow}
                onChange={setSiteRow}
              />
              {simZones.map((zone) => (
                <FigureRow
                  key={zone.slug}
                  id={`zone-${zone.slug}`}
                  label={zone.name}
                  row={zoneRows[zone.slug] ?? { capacity: zone.capacity, occupied: 0, health: 'OK' }}
                  onChange={(row) => setZoneRows((current) => ({ ...current, [zone.slug]: row }))}
                />
              ))}
            </TableBody>
          </Table>
          <Button onClick={postManual} disabled={busy}>
            <Send className="mr-2 h-4 w-4" />
            {t('sites:simulator.snapshot.post')}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function FigureRow({
  id,
  label,
  row,
  onChange,
}: {
  id: string
  label: string
  row: Row
  onChange: (row: Row) => void
}) {
  const { t } = useTranslation('sites')
  return (
    <TableRow>
      <TableCell className="font-medium">{label}</TableCell>
      <TableCell>
        <Label htmlFor={`${id}-capacity`} className="sr-only">
          {t('simulator.snapshot.capacityOf', { name: label })}
        </Label>
        <Input
          id={`${id}-capacity`}
          type="number"
          min={0}
          className="w-24"
          value={row.capacity}
          onChange={(e) => onChange({ ...row, capacity: intOr(e.target.value) })}
        />
      </TableCell>
      <TableCell>
        <Label htmlFor={`${id}-occupied`} className="sr-only">
          {t('simulator.snapshot.occupiedOf', { name: label })}
        </Label>
        <Input
          id={`${id}-occupied`}
          type="number"
          min={0}
          className="w-24"
          value={row.occupied}
          onChange={(e) => onChange({ ...row, occupied: intOr(e.target.value) })}
        />
      </TableCell>
      <TableCell>
        <Select value={row.health} onValueChange={(v) => onChange({ ...row, health: v as Health })}>
          <SelectTrigger className="w-32" aria-label={t('simulator.snapshot.healthOf', { name: label })}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HEALTH.map((h) => (
              <SelectItem key={h} value={h}>
                {t(`simulator.health.${h}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
    </TableRow>
  )
}
