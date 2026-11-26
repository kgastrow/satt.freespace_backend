import { Fragment, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight, Download } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { DatePicker } from '@/components/ui/date-picker'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { getErrorMessage } from '@/types/api'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { EventDetail } from '@/features/sites/components/EventDetail'
import { useExportSiteEventsMutation, useGetSiteEventsQuery } from '@/features/sites/eventsApi'
import {
  EMPTY_EVENT_FILTERS,
  EVENT_REASONS,
  EVENT_TYPES,
  filtersToQuery,
  isPeriodInvalid,
  type EventFilters,
  type PeriodPreset,
} from '@/features/sites/eventFilters'
import { formatDayClock } from '@/features/sites/engineTimers'
import { downloadTextFile } from '@/features/sites/downloadCsv'
import { getServerError } from '@/features/sites/errors'
import { useSitePermissions } from '@/features/sites/permissions'
import type { Site } from '@/types/site'

const PAGE_SIZE = 25
const ANY = '__any__'
const PERIODS: PeriodPreset[] = ['all', '24h', '7d', '30d', 'custom']

function SiteEvents({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { canReadEvents } = useSitePermissions()
  const [filters, setFilters] = useState<EventFilters>(EMPTY_EVENT_FILTERS)
  // "Now" for relative periods only moves when the filter changes, so the
  // query key is stable between renders.
  const [anchor, setAnchor] = useState(() => new Date())
  const [page, setPage] = useState(1)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [exportEvents, { isLoading: isExporting }] = useExportSiteEventsMutation()

  const periodInvalid = isPeriodInvalid(filters)
  const query = useMemo(
    () => filtersToQuery(filters, { timeZone: site.time_zone, now: anchor, page, pageSize: PAGE_SIZE }),
    [filters, site.time_zone, anchor, page]
  )
  const { data, isLoading, isFetching, error } = useGetSiteEventsQuery(
    { siteId: site.id, query },
    { skip: periodInvalid || !canReadEvents }
  )

  const update = (patch: Partial<EventFilters>) => {
    setFilters((current) => ({ ...current, ...patch }))
    setAnchor(new Date())
    setPage(1)
  }

  const toggle = (id: string) =>
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const onExport = async () => {
    try {
      const csv = await exportEvents({ siteId: site.id, query }).unwrap()
      downloadTextFile(csv, `events-${site.slug}.csv`)
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  if (!canReadEvents) {
    return (
      <Alert>
        <AlertDescription>{t('sites:events.noAccess')}</AlertDescription>
      </Alert>
    )
  }

  const total = data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const items = data?.items ?? []
  const first = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const last = Math.min(total, page * PAGE_SIZE)

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t('sites:events.intro')}</p>

      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-wrap items-end gap-4">
            <div className="space-y-2">
              <Label htmlFor="event-type">{t('sites:events.filters.type')}</Label>
              <Select
                value={filters.type || ANY}
                onValueChange={(v) => update({ type: v === ANY ? '' : v })}
              >
                <SelectTrigger id="event-type" className="w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>{t('sites:events.filters.anyType')}</SelectItem>
                  {EVENT_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {t(`sites:events.types.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="event-reason">{t('sites:events.filters.reason')}</Label>
              <Select
                value={filters.reason || ANY}
                onValueChange={(v) => update({ reason: v === ANY ? '' : v })}
              >
                <SelectTrigger id="event-reason" className="w-60">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY}>{t('sites:events.filters.anyReason')}</SelectItem>
                  {EVENT_REASONS.map((reason) => (
                    <SelectItem key={reason} value={reason}>
                      {t(`sites:events.reasons.${reason}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="event-period">{t('sites:events.filters.period')}</Label>
              <Select
                value={filters.period}
                onValueChange={(v) => update({ period: v as PeriodPreset })}
              >
                <SelectTrigger id="event-period" className="w-48">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PERIODS.map((period) => (
                    <SelectItem key={period} value={period}>
                      {t(`sites:events.filters.periods.${period}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {filters.period === 'custom' && (
              <>
                <div className="space-y-2">
                  <Label>{t('sites:events.filters.from')}</Label>
                  <DatePicker
                    value={filters.from || undefined}
                    onChange={(v) => update({ from: v ?? '' })}
                    placeholder={t('sites:events.filters.pickDay')}
                  />
                </div>
                <div className="space-y-2">
                  <Label>{t('sites:events.filters.to')}</Label>
                  <DatePicker
                    value={filters.to || undefined}
                    onChange={(v) => update({ to: v ?? '' })}
                    placeholder={t('sites:events.filters.pickDay')}
                  />
                </div>
              </>
            )}
            <div className="ml-auto flex gap-2">
              <Button
                variant="ghost"
                onClick={() => {
                  setFilters(EMPTY_EVENT_FILTERS)
                  setAnchor(new Date())
                  setPage(1)
                }}
              >
                {t('sites:events.filters.clear')}
              </Button>
              <Button
                variant="outline"
                onClick={onExport}
                disabled={isExporting || periodInvalid}
              >
                <Download className="mr-2 h-4 w-4" />
                {isExporting ? t('sites:events.exporting') : t('sites:events.export')}
              </Button>
            </div>
          </div>
          {periodInvalid && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {t('sites:events.filters.periodInvalid')}
            </p>
          )}
        </CardContent>
      </Card>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t('sites:events.loadError')}</AlertTitle>
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      ) : isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>{t('sites:events.columns.time')}</TableHead>
                <TableHead>{t('sites:events.columns.type')}</TableHead>
                <TableHead>{t('sites:events.columns.reason')}</TableHead>
                <TableHead>{t('sites:events.columns.zone')}</TableHead>
                <TableHead className="text-right">{t('sites:events.columns.repeats')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground">
                    {t('sites:events.empty')}
                  </TableCell>
                </TableRow>
              )}
              {items.map((event) => {
                const open = expanded.has(event.id)
                return (
                  <Fragment key={event.id}>
                    <TableRow data-testid={`event-row-${event.id}`}>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-expanded={open}
                          aria-label={t(open ? 'sites:events.collapse' : 'sites:events.expand')}
                          onClick={() => toggle(event.id)}
                        >
                          {open ? (
                            <ChevronDown className="h-4 w-4" />
                          ) : (
                            <ChevronRight className="h-4 w-4" />
                          )}
                        </Button>
                      </TableCell>
                      <TableCell className="whitespace-nowrap">
                        {formatDayClock(event.occurred_at, site.time_zone) ?? event.occurred_at}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {t(`sites:events.types.${event.type}`, { defaultValue: event.type })}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {event.reason
                          ? t(`sites:events.reasons.${event.reason}`, { defaultValue: event.reason })
                          : <span className="text-muted-foreground">-</span>}
                      </TableCell>
                      <TableCell>
                        {event.zone_slug ?? <span className="text-muted-foreground">-</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {event.repeat_count > 1 ? `×${event.repeat_count}` : ''}
                      </TableCell>
                    </TableRow>
                    {open && (
                      <TableRow className="bg-muted/30 hover:bg-muted/30">
                        <TableCell colSpan={6} className="p-0">
                          <EventDetail event={event} timeZone={site.time_zone} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {t('sites:events.range', { first, last, total })}
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1 || isFetching}
                onClick={() => setPage((p) => p - 1)}
              >
                {t('sites:events.previous')}
              </Button>
              <span className="text-sm tabular-nums">
                {t('sites:events.pageOf', { page, pages: pageCount })}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= pageCount || isFetching}
                onClick={() => setPage((p) => p + 1)}
              >
                {t('sites:events.next')}
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export function SiteEventsPage() {
  return <SiteDetailShell>{(site) => <SiteEvents site={site} />}</SiteDetailShell>
}
