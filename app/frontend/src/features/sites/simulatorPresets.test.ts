import { describe, it, expect } from 'vitest'
import {
  buildPreset,
  maxHoldStepS,
  matchExpectation,
  MAX_HOLD_STEP_S,
  PRESET_IDS,
  snapshotFromSpec,
} from './simulatorPresets'

const ctx = { triggerPct: 90, resetPct: 80, stabilisationS: 300 }

describe('buildPreset', () => {
  it('builds every acceptance scenario AT-01 to AT-08', () => {
    for (const id of PRESET_IDS) {
      const preset = buildPreset(id, ctx)
      expect(preset?.id).toBe(id)
      expect(preset!.steps.length).toBeGreaterThan(0)
      for (const step of preset!.steps) {
        expect(step.expectedKey).toMatch(/^sites:simulator\.expected\./)
      }
    }
    expect(buildPreset('AT-99', ctx)).toBeNull()
  })

  it('AT-03 holds the trigger past the stabilisation time in short hops, ending ACTIVE', () => {
    const steps = buildPreset('AT-03', ctx)!.steps
    expect(steps[0].expected.state).toBe('PENDING')
    expect(steps[steps.length - 1].expected.state).toBe('ACTIVE')
    const advanced = steps.reduce((sum, s) => sum + (s.advanceSeconds ?? 0), 0)
    expect(advanced).toBeGreaterThanOrEqual(ctx.stabilisationS)
    expect(Math.max(...steps.map((s) => s.advanceSeconds ?? 0))).toBeLessThanOrEqual(MAX_HOLD_STEP_S)
  })

  it('AT-02 falls back before stabilisation and expects IDLE', () => {
    const steps = buildPreset('AT-02', ctx)!.steps
    const advanced = steps.slice(0, -1).reduce((sum, s) => sum + (s.advanceSeconds ?? 0), 0)
    expect(advanced).toBeLessThan(ctx.stabilisationS)
    expect(steps[steps.length - 1].expected.state).toBe('IDLE')
    expect(steps[steps.length - 1].snapshot?.sitePct).toBeLessThan(ctx.triggerPct)
  })

  it('follows the site settings, not fixed numbers', () => {
    const steps = buildPreset('AT-06', { triggerPct: 70, resetPct: 60, stabilisationS: 120 })!.steps
    expect(steps[0].snapshot?.sitePct).toBe(70)
    expect(steps.find((s) => s.id === 'reset')?.snapshot?.sitePct).toBe(59)
  })

  it('AT-08 moves the clock without a snapshot and expects stale data', () => {
    const silence = buildPreset('AT-08', ctx)!.steps.find((s) => s.id === 'silence')!
    expect(silence.snapshot).toBeUndefined()
    expect(silence.advanceSeconds).toBe(180)
    expect(silence.expected.stale).toBe(true)
  })
})

describe('matchExpectation', () => {
  const seen = { state: 'PENDING' as const, stale: false, recommendedZoneId: 'b1' }
  it('compares only the named fields', () => {
    expect(matchExpectation({ state: 'PENDING' }, seen)).toBe('match')
    expect(matchExpectation({ state: 'ACTIVE' }, seen)).toBe('differs')
    expect(matchExpectation({ stale: true }, seen)).toBe('differs')
    expect(matchExpectation({ recommendation: 'some' }, seen)).toBe('match')
    expect(matchExpectation({ recommendation: 'none' }, seen)).toBe('differs')
    expect(matchExpectation({}, seen)).toBe('unchecked')
  })
})

describe('snapshotFromSpec', () => {
  const zones = [
    { slug: 'b1', name: 'B1', capacity: 100 },
    { slug: 'b2', name: 'B2', capacity: 50 },
  ]
  it('builds camelCase counts that add up and marks offline zones', () => {
    const body = snapshotFromSpec('alice', 200, zones, { sitePct: 85, zonePcts: [98], restPct: 40, offlineZones: [1] })
    expect(body.siteId).toBe('alice')
    expect(body.site).toMatchObject({ capacity: 200, occupied: 170, freeUsable: 30, health: 'OK' })
    expect(body.zones[0]).toMatchObject({ zoneId: 'b1', occupied: 98, freeUsable: 2, health: 'OK' })
    expect(body.zones[1]).toMatchObject({ zoneId: 'b2', occupied: 20, freeUsable: 30, health: 'OFFLINE' })
    expect(body.measuredAt).toBeUndefined()
  })
})

describe('stale limit of the site', () => {
  it('derives the longest hold step from the stale limit', () => {
    expect(maxHoldStepS()).toBe(MAX_HOLD_STEP_S)
    expect(maxHoldStepS(60)).toBe(45)
    expect(maxHoldStepS(600)).toBe(450)
  })

  it('keeps every hold step inside a short stale limit', () => {
    const steps = buildPreset('AT-03', { ...ctx, staleLimitS: 60 })!.steps
    expect(Math.max(...steps.map((s) => s.advanceSeconds ?? 0))).toBeLessThanOrEqual(45)
  })

  it('AT-08 silence outlasts the site stale limit', () => {
    const silence = buildPreset('AT-08', { ...ctx, staleLimitS: 600 })!.steps[1]
    expect(silence.advanceSeconds).toBeGreaterThan(600)
    expect(buildPreset('AT-08', ctx)!.steps[1].advanceSeconds).toBeGreaterThan(120)
  })
})
