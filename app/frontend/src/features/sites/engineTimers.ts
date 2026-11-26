import type { LiveEngine } from '@/types/siteLive'

/** "07:41" in the given IANA time zone (24 h); null for missing/invalid input. */
export function formatClock(iso: string | null | undefined, timeZone: string): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone,
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(date)
  } catch {
    return null
  }
}

/** "26 Nov, 07:41" in the given time zone; null for missing/invalid input. */
export function formatDayClock(iso: string | null | undefined, timeZone: string): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone,
      day: 'numeric',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).format(date)
  } catch {
    return null
  }
}

/** A translatable phrase: i18n key (sites namespace) plus its interpolation values. */
export interface Phrase {
  key: string
  values: Record<string, string | number>
}

/** Data age as a phrase with a plural `count` ("45 seconds", "3 minutes", "2 hours"). */
export function describeAge(seconds: number | null | undefined): Phrase | null {
  if (seconds === null || seconds === undefined || seconds < 0) return null
  if (seconds < 60) return { key: 'sites:age.seconds', values: { count: Math.floor(seconds) } }
  if (seconds < 3600) return { key: 'sites:age.minutes', values: { count: Math.floor(seconds / 60) } }
  return { key: 'sites:age.hours', values: { count: Math.floor(seconds / 3600) } }
}

/**
 * The engine's timers in words, in the site's time zone, e.g. "pending since
 * 07:41, fires at 07:46" followed by "in 3 minutes" (or "due now" once past).
 */
export function describeEngineTimers(
  engine: LiveEngine | null,
  nowMs: number,
  timeZone: string
): Phrase[] {
  if (!engine) return [{ key: 'sites:live.engine.noState', values: {} }]
  const lines: Phrase[] = []
  if (engine.state === 'PENDING') {
    const since = formatClock(engine.pending_since, timeZone)
    const fires = formatClock(engine.fires_at, timeZone)
    lines.push({
      key: 'sites:live.engine.pending',
      values: { since: since ?? '-', at: fires ?? '-' },
    })
    if (engine.fires_at) {
      const remaining = Math.ceil((new Date(engine.fires_at).getTime() - nowMs) / 1000)
      if (Number.isNaN(remaining)) return lines
      if (remaining <= 0) lines.push({ key: 'sites:live.engine.dueNow', values: {} })
      else if (remaining < 60) lines.push({ key: 'sites:live.engine.inSeconds', values: { count: remaining } })
      else lines.push({ key: 'sites:live.engine.inMinutes', values: { count: Math.ceil(remaining / 60) } })
    }
  } else if (engine.state === 'ACTIVE') {
    lines.push({
      key: 'sites:live.engine.active',
      values: { since: formatClock(engine.state_entered_at, timeZone) ?? '-' },
    })
  } else {
    lines.push({ key: 'sites:live.engine.idle', values: {} })
  }
  return lines
}
