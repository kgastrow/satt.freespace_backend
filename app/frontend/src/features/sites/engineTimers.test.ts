import { describe, it, expect } from 'vitest'
import { describeAge, describeEngineTimers, formatClock } from './engineTimers'
import type { LiveEngine } from '@/types/siteLive'

const TZ = 'Africa/Johannesburg' // UTC+2, no DST

const engine = (patch: Partial<LiveEngine>): LiveEngine => ({
  state: 'IDLE',
  state_entered_at: null,
  pending_since: null,
  fires_at: null,
  cycle_id: null,
  last_notified_pct: null,
  last_notified_zone_slug: null,
  last_notified_top_zones: [],
  last_sent_at: null,
  current_zone_slug: null,
  current_zone_since: null,
  stale: false,
  stale_since: null,
  inflight_event_id: null,
  inflight: false,
  zone_advisories: [],
  last_evaluated_at: null,
  ...patch,
})

describe('formatClock', () => {
  it('formats in the site time zone, 24 hour', () => {
    expect(formatClock('2026-11-26T05:41:00Z', TZ)).toBe('07:41')
    expect(formatClock('2026-11-26T23:30:00Z', TZ)).toBe('01:30')
  })
  it('returns null for missing or invalid input', () => {
    expect(formatClock(null, TZ)).toBeNull()
    expect(formatClock('nope', TZ)).toBeNull()
    expect(formatClock('2026-11-26T05:41:00Z', 'Not/AZone')).toBeNull()
  })
})

describe('describeEngineTimers', () => {
  const pending = engine({
    state: 'PENDING',
    pending_since: '2026-11-26T05:41:00Z',
    fires_at: '2026-11-26T05:46:00Z',
  })

  it('says pending since and fires at in the site zone, with minutes remaining', () => {
    const now = new Date('2026-11-26T05:43:00Z').getTime()
    const lines = describeEngineTimers(pending, now, TZ)
    expect(lines[0]).toEqual({ key: 'sites:live.engine.pending', values: { since: '07:41', at: '07:46' } })
    expect(lines[1]).toEqual({ key: 'sites:live.engine.inMinutes', values: { count: 3 } })
  })

  it('switches to seconds in the last minute and to due-now afterwards', () => {
    const near = describeEngineTimers(pending, new Date('2026-11-26T05:45:30Z').getTime(), TZ)
    expect(near[1]).toEqual({ key: 'sites:live.engine.inSeconds', values: { count: 30 } })
    const past = describeEngineTimers(pending, new Date('2026-11-26T05:46:05Z').getTime(), TZ)
    expect(past[1].key).toBe('sites:live.engine.dueNow')
  })

  it('describes active, idle and missing engines', () => {
    const active = engine({ state: 'ACTIVE', state_entered_at: '2026-11-26T05:46:00Z' })
    expect(describeEngineTimers(active, 0, TZ)).toEqual([
      { key: 'sites:live.engine.active', values: { since: '07:46' } },
    ])
    expect(describeEngineTimers(engine({}), 0, TZ)[0].key).toBe('sites:live.engine.idle')
    expect(describeEngineTimers(null, 0, TZ)[0].key).toBe('sites:live.engine.noState')
  })
})

describe('describeAge', () => {
  it('picks the unit', () => {
    expect(describeAge(45)).toEqual({ key: 'sites:age.seconds', values: { count: 45 } })
    expect(describeAge(180)).toEqual({ key: 'sites:age.minutes', values: { count: 3 } })
    expect(describeAge(7300)).toEqual({ key: 'sites:age.hours', values: { count: 2 } })
    expect(describeAge(null)).toBeNull()
  })
})
