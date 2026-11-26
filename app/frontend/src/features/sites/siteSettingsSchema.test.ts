import { describe, it, expect } from 'vitest'
import {
  createSiteSettingsSchema,
  createZoneSchema,
  createSiteCreateSchema,
  isValidTimeZone,
  SITE_SETTINGS_DEFAULTS,
} from './siteSettingsSchema'

const t = (key: string) => key
const schema = createSiteSettingsSchema(t)

const valid = () => ({ ...SITE_SETTINGS_DEFAULTS, notification_window: [...SITE_SETTINGS_DEFAULTS.notification_window] })

function issuePaths(input: unknown): string[] {
  const result = schema.safeParse(input)
  return result.success ? [] : result.error.issues.map((i) => i.path.join('.'))
}

describe('site settings schema (functional description 10.1)', () => {
  it('accepts the defaults', () => {
    expect(schema.safeParse(valid()).success).toBe(true)
  })

  describe.each([
    ['trigger_pct', 0, 1, 100, 101],
    ['change_points', 0, 1, 50, 51],
    ['stabilisation_s', -1, 0, 3600, 3601],
    ['stale_limit_s', 119, 120, undefined, undefined],
    ['zone_reset_gap', 0, 1, 50, 51],
    ['push_expiry_s', 59, 60, 86400, 86401],
    ['recommendation_margin', -1, 0, undefined, undefined],
    ['cooldown_s', -1, 0, undefined, undefined],
    ['daily_cap', -1, 0, undefined, undefined],
  ] as const)('%s', (field, below, min, max, above) => {
    it(`refuses ${below}, accepts ${min}`, () => {
      expect(issuePaths({ ...valid(), [field]: below })).toContain(field)
      expect(issuePaths({ ...valid(), [field]: min })).not.toContain(field)
    })
    if (max !== undefined) {
      it(`accepts ${max}, refuses ${above}`, () => {
        expect(issuePaths({ ...valid(), [field]: max })).not.toContain(field)
        expect(issuePaths({ ...valid(), [field]: above })).toContain(field)
      })
    }
  })

  it('refuses a reset below trigger violation: reset must be < trigger', () => {
    expect(issuePaths({ ...valid(), trigger_pct: 80, reset_pct: 80 })).toContain('reset_pct')
    expect(issuePaths({ ...valid(), trigger_pct: 80, reset_pct: 90 })).toContain('reset_pct')
    expect(issuePaths({ ...valid(), trigger_pct: 80, reset_pct: 79 })).toEqual([])
  })

  it('refuses non-integers instead of rounding them', () => {
    expect(issuePaths({ ...valid(), trigger_pct: 90.5 })).toContain('trigger_pct')
  })

  it('refuses a missing number', () => {
    expect(issuePaths({ ...valid(), daily_cap: undefined })).toContain('daily_cap')
  })

  it('accepts RISING and BOTH only', () => {
    expect(issuePaths({ ...valid(), change_direction: 'BOTH' })).toEqual([])
    expect(issuePaths({ ...valid(), change_direction: 'FALLING' })).toContain('change_direction')
  })

  it('accepts an empty notification window (any time)', () => {
    expect(issuePaths({ ...valid(), notification_window: [] })).toEqual([])
  })

  it('refuses an overnight or empty notification rule, pointing at the rule', () => {
    const overnight = [{ weekdays: [1], start: '22:00', end: '02:00' }]
    expect(issuePaths({ ...valid(), notification_window: overnight })).toContain('notification_window.0')
    const noDays = [{ weekdays: [], start: '06:00', end: '10:00' }]
    expect(issuePaths({ ...valid(), notification_window: noDays })).toContain('notification_window.0')
  })

  it('refuses more than 20 notification rules', () => {
    const rule = { weekdays: [1], start: '06:00', end: '10:00' }
    expect(issuePaths({ ...valid(), notification_window: Array(21).fill(rule) })).toContain(
      'notification_window'
    )
  })
})

describe('time zone check', () => {
  it('accepts IANA names and refuses others', () => {
    expect(isValidTimeZone('Africa/Johannesburg')).toBe(true)
    expect(isValidTimeZone('Mars/Olympus')).toBe(false)
    expect(isValidTimeZone('')).toBe(false)
  })
})

describe('site create schema', () => {
  const create = createSiteCreateSchema(t)
  const base = { slug: 'alice-lane', name: 'Alice Lane', time_zone: '', fcm_topic: '', organization_id: '' }
  it('accepts a valid slug and refuses invalid ones', () => {
    expect(create.safeParse(base).success).toBe(true)
    expect(create.safeParse({ ...base, slug: 'Alice Lane' }).success).toBe(false)
    expect(create.safeParse({ ...base, slug: '-x' }).success).toBe(false)
  })
})

describe('zone schema (functional description 10.2)', () => {
  const zone = createZoneSchema(t, 'create')
  const base = {
    slug: 'b1', name: 'Basement 1', display_order: 1, enabled: true, recommendable: true,
    preferred: false, priority: 100, limited_pct: 80, full_pct: 95, full_min_free: 5,
    unknown_limit_pct: 25, advisory_pct: undefined, note: '',
  }
  it('accepts defaults and an unset advisory', () => {
    expect(zone.safeParse(base).success).toBe(true)
  })
  it('refuses limited above full', () => {
    const r = zone.safeParse({ ...base, limited_pct: 96 })
    expect(r.success).toBe(false)
  })
  it('bounds the advisory percentage to 1-100', () => {
    expect(zone.safeParse({ ...base, advisory_pct: 0 }).success).toBe(false)
    expect(zone.safeParse({ ...base, advisory_pct: 100 }).success).toBe(true)
    expect(zone.safeParse({ ...base, advisory_pct: 101 }).success).toBe(false)
  })
  it('requires a name', () => {
    expect(zone.safeParse({ ...base, name: '  ' }).success).toBe(false)
  })
})
