import { describe, it, expect } from 'vitest'
import { shapeHistory, shiftDay, todayInZone } from './historySeries'
import type { HistoryPoint, SiteHistoryResponse } from '@/types/siteLive'

const point = (at: string, pct: number | null, health: HistoryPoint['health'] = 'OK'): HistoryPoint => ({
  at,
  occupied: 0,
  capacity: 100,
  free_usable: 0,
  occupancy_pct: pct,
  health,
})

const history = (patch: Partial<SiteHistoryResponse>): SiteHistoryResponse => ({
  site_id: 's',
  date: '2026-11-26',
  time_zone: 'Africa/Johannesburg',
  start: '2026-11-25T22:00:00Z',
  end: '2026-11-26T22:00:00Z',
  trigger_pct: 90,
  reset_pct: 80,
  site: [],
  zones: [],
  ...patch,
})

describe('shapeHistory', () => {
  it('reports an empty day', () => {
    const shaped = shapeHistory(history({}))
    expect(shaped.empty).toBe(true)
    expect(shaped.rows).toEqual([])
  })

  it('merges site and zone series onto one row per instant with nulls for missing values', () => {
    const shaped = shapeHistory(
      history({
        site: [point('2026-11-26T05:00:00Z', 70), point('2026-11-26T05:01:00Z', 72)],
        zones: [{ id: 'b1', name: 'B1', points: [point('2026-11-26T05:01:00Z', 50)] }],
      })
    )
    expect(shaped.series.map((s) => s.key)).toEqual(['site', 'zone:b1'])
    expect(shaped.rows).toHaveLength(2)
    expect(shaped.rows[0]).toMatchObject({ site: 70, 'zone:b1': null })
    expect(shaped.rows[1]).toMatchObject({ site: 72, 'zone:b1': 50 })
  })

  it('breaks the line across a hole instead of connecting or zeroing it', () => {
    const shaped = shapeHistory(
      history({ site: [point('2026-11-26T05:00:00Z', 70), point('2026-11-26T06:00:00Z', 75)] })
    )
    expect(shaped.rows.map((r) => r.site)).toEqual([70, null, 75])
    const gapRow = shaped.rows[1]
    expect(gapRow.t).toBeGreaterThan(shaped.rows[0].t)
    expect(gapRow.t).toBeLessThan(shaped.rows[2].t)
  })

  it('does not insert a break for small steps', () => {
    const shaped = shapeHistory(
      history({ site: [point('2026-11-26T05:00:00Z', 70), point('2026-11-26T05:05:00Z', 75)] })
    )
    expect(shaped.rows.map((r) => r.site)).toEqual([70, 75])
  })

  it('treats null percentages and OFFLINE buckets as no data, never zero', () => {
    const shaped = shapeHistory(
      history({
        site: [
          point('2026-11-26T05:00:00Z', 70),
          point('2026-11-26T05:01:00Z', null),
          point('2026-11-26T05:02:00Z', 0, 'OFFLINE'),
        ],
      })
    )
    expect(shaped.rows.map((r) => r.site)).toEqual([70])
    expect(shaped.rows.some((r) => r.site === 0)).toBe(false)
  })

  it('keeps a real zero percent', () => {
    const shaped = shapeHistory(history({ site: [point('2026-11-26T05:00:00Z', 0)] }))
    expect(shaped.rows[0].site).toBe(0)
  })

  it('caps the number of zone series and uses the day as the domain', () => {
    const zones = ['a', 'b', 'c'].map((id) => ({ id, name: id, points: [point('2026-11-26T05:00:00Z', 10)] }))
    const shaped = shapeHistory(history({ zones }), { maxZones: 2 })
    expect(shaped.series.map((s) => s.key)).toEqual(['site', 'zone:a', 'zone:b'])
    expect(shaped.domain).toEqual([Date.parse('2026-11-25T22:00:00Z'), Date.parse('2026-11-26T22:00:00Z')])
  })
})

describe('day helpers', () => {
  it('shifts days across month ends', () => {
    expect(shiftDay('2026-11-30', 1)).toBe('2026-12-01')
    expect(shiftDay('2026-03-01', -1)).toBe('2026-02-28')
  })
  it('names today in the site zone, not the local one', () => {
    const now = new Date('2026-11-26T23:30:00Z')
    expect(todayInZone('Africa/Johannesburg', now)).toBe('2026-11-27')
    expect(todayInZone('UTC', now)).toBe('2026-11-26')
  })
})
