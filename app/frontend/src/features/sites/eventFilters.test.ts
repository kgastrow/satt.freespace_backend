import { describe, it, expect } from 'vitest'
import {
  EMPTY_EVENT_FILTERS,
  eventQueryString,
  filtersToQuery,
  isPeriodInvalid,
  zonedMidnightIso,
} from './eventFilters'

const NOW = new Date('2026-11-26T12:00:00Z')
const base = { timeZone: 'Africa/Johannesburg', now: NOW, page: 1, pageSize: 25 }

describe('filtersToQuery', () => {
  it('maps empty filters to paging only', () => {
    expect(filtersToQuery(EMPTY_EVENT_FILTERS, base)).toEqual({ limit: 25, offset: 0 })
  })

  it('maps type, reason and page', () => {
    const query = filtersToQuery(
      { ...EMPTY_EVENT_FILTERS, type: 'CANDIDATE', reason: 'COOLDOWN' },
      { ...base, page: 3 }
    )
    expect(query).toEqual({ type: 'CANDIDATE', reason: 'COOLDOWN', limit: 25, offset: 50 })
  })

  it('maps presets relative to now', () => {
    const query = filtersToQuery({ ...EMPTY_EVENT_FILTERS, period: '24h' }, base)
    expect(query.start).toBe('2026-11-25T12:00:00.000Z')
    expect(query.end).toBeUndefined()
    expect(filtersToQuery({ ...EMPTY_EVENT_FILTERS, period: '7d' }, base).start).toBe('2026-11-19T12:00:00.000Z')
  })

  it('maps custom days in the site zone with an exclusive end the day after', () => {
    const query = filtersToQuery(
      { ...EMPTY_EVENT_FILTERS, period: 'custom', from: '2026-11-20', to: '2026-11-22' },
      base
    )
    expect(query.start).toBe('2026-11-19T22:00:00.000Z')
    expect(query.end).toBe('2026-11-22T22:00:00.000Z')
  })

  it('honours daylight saving in the site zone', () => {
    // Europe/London is UTC+1 in summer, UTC+0 in winter
    expect(zonedMidnightIso('2026-07-01', 'Europe/London')).toBe('2026-06-30T23:00:00.000Z')
    expect(zonedMidnightIso('2026-12-01', 'Europe/London')).toBe('2026-12-01T00:00:00.000Z')
    expect(zonedMidnightIso('bad', 'UTC')).toBeNull()
  })
})

describe('period validation and query string', () => {
  it('flags an inverted custom period', () => {
    expect(
      isPeriodInvalid({ ...EMPTY_EVENT_FILTERS, period: 'custom', from: '2026-11-22', to: '2026-11-20' })
    ).toBe(true)
    expect(isPeriodInvalid({ ...EMPTY_EVENT_FILTERS, period: 'custom', from: '2026-11-20' })).toBe(false)
  })

  it('serialises only set values', () => {
    expect(eventQueryString({})).toBe('')
    expect(eventQueryString({ type: 'ADVISORY', limit: 25, offset: 0, reason: '' })).toBe(
      '?type=ADVISORY&limit=25&offset=0'
    )
  })
})
