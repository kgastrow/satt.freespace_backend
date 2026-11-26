import type { HistoryPoint, SiteHistoryResponse } from '@/types/siteLive'

/** A chart row: `t` is the epoch ms; series keys hold a percentage or null (no data). */
export type HistoryRow = { t: number } & Record<string, number | null>

export interface HistorySeriesInfo {
  /** key in the rows: 'site' or 'zone:<slug>' */
  key: string
  /** zone slug; null for the site series */
  zoneId: string | null
  name: string
}

export interface ShapedHistory {
  rows: HistoryRow[]
  series: HistorySeriesInfo[]
  domain: [number, number]
  /** true when no series has a single plottable point */
  empty: boolean
}

/** Default: a hole longer than this breaks the line. */
export const DEFAULT_MAX_GAP_MS = 10 * 60_000

interface Plot {
  t: number
  value: number
}

/** Plottable points: no data (null %) and OFFLINE buckets are gaps, never zero. */
function plottable(points: HistoryPoint[]): Plot[] {
  return points
    .filter((p) => p.occupancy_pct !== null && p.health !== 'OFFLINE')
    .map((p) => ({ t: new Date(p.at).getTime(), value: p.occupancy_pct as number }))
    .filter((p) => !Number.isNaN(p.t))
    .sort((a, b) => a.t - b.t)
}

/**
 * Turn the history response into chart rows: one row per instant, one column
 * per series, `null` where a series has no data. Where two consecutive points
 * of a series are further apart than `maxGapMs`, a null row is inserted
 * between them so the line is broken instead of drawn across the hole.
 * `maxZones` caps the zone series (the palette has a fixed number of hues).
 */
export function shapeHistory(
  history: SiteHistoryResponse,
  opts: { maxGapMs?: number; maxZones?: number } = {}
): ShapedHistory {
  const maxGap = opts.maxGapMs ?? DEFAULT_MAX_GAP_MS
  const zones = history.zones.slice(0, opts.maxZones ?? history.zones.length)
  const series: HistorySeriesInfo[] = [
    { key: 'site', zoneId: null, name: '' },
    ...zones.map((z) => ({ key: `zone:${z.id}`, zoneId: z.id, name: z.name })),
  ]
  const sources: Array<[string, Plot[]]> = [
    ['site', plottable(history.site)],
    ...zones.map((z): [string, Plot[]] => [`zone:${z.id}`, plottable(z.points)]),
  ]

  const byTime = new Map<number, HistoryRow>()
  const rowAt = (t: number): HistoryRow => {
    let row = byTime.get(t)
    if (!row) {
      row = { t } as HistoryRow
      for (const s of series) row[s.key] = null
      byTime.set(t, row)
    }
    return row
  }

  let any = false
  for (const [key, points] of sources) {
    let previous: Plot | null = null
    for (const point of points) {
      any = true
      if (previous && point.t - previous.t > maxGap) {
        // Break the line: a row where this series is explicitly null.
        rowAt(Math.round((previous.t + point.t) / 2))
      }
      rowAt(point.t)[key] = point.value
      previous = point
    }
  }

  const start = new Date(history.start).getTime()
  const end = new Date(history.end).getTime()
  const rows = [...byTime.values()].sort((a, b) => a.t - b.t)
  const fallback: [number, number] = rows.length ? [rows[0].t, rows[rows.length - 1].t] : [0, 1]
  return {
    rows,
    series,
    domain: Number.isNaN(start) || Number.isNaN(end) ? fallback : [start, end],
    empty: !any,
  }
}

/** Today in the given zone as yyyy-MM-dd. */
export function todayInZone(timeZone: string, now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat('en-CA', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(now)
  } catch {
    return now.toISOString().slice(0, 10)
  }
}

/** yyyy-MM-dd shifted by whole days (calendar arithmetic, no time zone involved). */
export function shiftDay(day: string, delta: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  if (!match) return day
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + delta))
  return date.toISOString().slice(0, 10)
}

/** Tick instants every `stepHours` from the start of the domain. */
export function hourTicks(domain: [number, number], stepHours = 3): number[] {
  const ticks: number[] = []
  for (let t = domain[0]; t <= domain[1]; t += stepHours * 3_600_000) ticks.push(t)
  return ticks
}
