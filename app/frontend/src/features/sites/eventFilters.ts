import type { SiteEventQuery } from '@/types/siteLive'

/** Event types of the log (BF-62), in display order. */
export const EVENT_TYPES = [
  'STATE_CHANGE',
  'CANDIDATE',
  'ADVISORY',
  'DATA_STALE',
  'DATA_RECOVERED',
  'INGEST_REJECTED',
  'INGEST_INCONSISTENT',
  'ZONE_DISCOVERED',
  'FCM_ERROR',
  'CONFIG_CHANGED',
  'TEST_PUSH',
  'ANNOUNCEMENT',
] as const

/**
 * Reason codes that appear on events (BF-52, BF-57, BF-58, BF-61, BF-66,
 * BF-72, BF-77, §8.5, §8.6) - the options of the reason filter and the labels
 * (`sites:events.reasons.<CODE>`).
 */
export const EVENT_REASONS = [
  // state changes
  'TRIGGER_CROSSED',
  'NOT_STABLE',
  'STABILISED',
  'RESET',
  'CYCLE_RESTARTED',
  // candidate suppression
  'STALE_DATA',
  'NO_MATERIAL_CHANGE',
  'NO_RECOMMENDATION',
  'UNMANAGED',
  'IN_FLIGHT',
  // ingest
  'SITE_MISMATCH',
  'CLOCK_SKEW',
  'RATE_LIMITED',
  'OUT_OF_ORDER',
  'SUM_MISMATCH',
  // FCM
  'AUTH_FAILURE',
  'CREDENTIALS_MISSING',
  'QUOTA_EXHAUSTED',
  // configuration
  'SITE_SETTINGS',
  'ZONE_SETTINGS',
  'TEMPLATES',
  'MANAGED_ON',
  'MANAGED_OFF',
  'KEYS',
] as const

/** Per-device outcome keys of `counts` (BF-58, BF-66). */
export const DEVICE_OUTCOMES = [
  'SENT',
  'OPTED_OUT',
  'OUTSIDE_WINDOW',
  'DUPLICATE',
  'COOLDOWN',
  'DAILY_CAP',
  'SEND_FAILED',
  'TOKEN_INVALID',
  'PENDING',
] as const

export type PeriodPreset = 'all' | '24h' | '7d' | '30d' | 'custom'

export interface EventFilters {
  /** '' = any */
  type: string
  /** '' = any */
  reason: string
  period: PeriodPreset
  /** yyyy-MM-dd, used when period = custom */
  from: string
  /** yyyy-MM-dd (inclusive day), used when period = custom */
  to: string
}

export const EMPTY_EVENT_FILTERS: EventFilters = {
  type: '',
  reason: '',
  period: 'all',
  from: '',
  to: '',
}

const PRESET_HOURS: Record<string, number> = { '24h': 24, '7d': 24 * 7, '30d': 24 * 30 }

/** Offset (ms) of `timeZone` from UTC at the instant `ms`. */
function zoneOffsetMs(ms: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(new Date(ms))
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value)
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'))
  return asUtc - Math.floor(ms / 1000) * 1000
}

/** ISO instant of 00:00 on `day` (yyyy-MM-dd) in `timeZone`; null for bad input. */
export function zonedMidnightIso(day: string, timeZone: string, addDays = 0): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day)
  if (!match) return null
  const guess = Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + addDays)
  try {
    let result = guess - zoneOffsetMs(guess, timeZone)
    result = guess - zoneOffsetMs(result, timeZone)
    return new Date(result).toISOString()
  } catch {
    return null
  }
}

/**
 * Filter form -> API query. Presets are relative to `now` (pass a value that
 * only changes when the user changes the filter, so the query key is stable);
 * custom days are interpreted in the site's time zone and the end day is
 * inclusive (sent as the start of the next day, the API end being exclusive).
 */
export function filtersToQuery(
  filters: EventFilters,
  opts: { timeZone: string; now: Date; page: number; pageSize: number }
): SiteEventQuery {
  const query: SiteEventQuery = {
    limit: opts.pageSize,
    offset: Math.max(0, (opts.page - 1) * opts.pageSize),
  }
  if (filters.type) query.type = filters.type
  if (filters.reason) query.reason = filters.reason
  if (filters.period in PRESET_HOURS) {
    query.start = new Date(opts.now.getTime() - PRESET_HOURS[filters.period] * 3_600_000).toISOString()
  } else if (filters.period === 'custom') {
    const start = filters.from ? zonedMidnightIso(filters.from, opts.timeZone) : null
    const end = filters.to ? zonedMidnightIso(filters.to, opts.timeZone, 1) : null
    if (start) query.start = start
    if (end) query.end = end
  }
  return query
}

/** True when a custom period has both ends and start is not before end. */
export function isPeriodInvalid(filters: EventFilters): boolean {
  return (
    filters.period === 'custom' &&
    Boolean(filters.from) &&
    Boolean(filters.to) &&
    filters.from > filters.to
  )
}

/** '?a=b&c=d' (or '') from a query; undefined/empty values are skipped. */
export function eventQueryString(query: SiteEventQuery): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
