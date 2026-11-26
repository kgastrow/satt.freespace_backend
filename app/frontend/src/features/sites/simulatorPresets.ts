import type {
  EngineState,
  Health,
  LiveZone,
  MockOccupancyRequest,
  SiteLiveResponse,
} from '@/types/siteLive'

/** Stale limit used when a site does not report one (the default of a new site). */
export const DEFAULT_STALE_LIMIT_S = 120

/** Longest clock jump between two snapshots with the default stale limit. */
export const MAX_HOLD_STEP_S = 90

/** Longest clock jump between two snapshots that keeps the data fresh: three quarters of the site's stale limit. */
export function maxHoldStepS(staleLimitS: number = DEFAULT_STALE_LIMIT_S): number {
  return Math.max(1, Math.floor(staleLimitS * 0.75))
}

export interface PresetContext {
  triggerPct: number
  resetPct: number
  stabilisationS: number
  /** The site's stale limit in seconds; defaults to DEFAULT_STALE_LIMIT_S */
  staleLimitS?: number
}

export interface SnapshotSpec {
  sitePct: number
  /** Occupancy % per zone by position (display order); missing zones use `restPct`. */
  zonePcts?: number[]
  restPct?: number
  /** Zone positions reported OFFLINE */
  offlineZones?: number[]
}

/** What the step should produce; only the fields set are compared. */
export interface Expectation {
  state?: EngineState
  stale?: boolean
  /** a recommendation is (some) or is not (none) shown */
  recommendation?: 'some' | 'none'
}

export interface PresetStep {
  id: string
  /** Mock clock moves forward by this before the snapshot (a step with no snapshot only moves the clock). */
  advanceSeconds?: number
  snapshot?: SnapshotSpec
  expected: Expectation
  /** i18n key (sites namespace) of the written expected outcome, shown beside the observed one */
  expectedKey: string
  /** Interpolation values for the expected text */
  values?: Record<string, string | number>
}

export interface Preset {
  /** AT-01 ... AT-08 */
  id: string
  /** i18n key of the scenario title */
  titleKey: string
  /** i18n key of the Given / when text */
  descriptionKey: string
  steps: PresetStep[]
}

export const PRESET_IDS = [
  'AT-01',
  'AT-02',
  'AT-03',
  'AT-04',
  'AT-05',
  'AT-06',
  'AT-07',
  'AT-08',
] as const

const clamp = (n: number) => Math.min(100, Math.max(0, Math.round(n)))

/** Steps that hold `pct` for `seconds`, each at most `maxStep` seconds apart. */
function hold(
  pct: number,
  seconds: number,
  expected: Expectation,
  expectedKey: string,
  prefix: string,
  maxStep: number
): PresetStep[] {
  const steps: PresetStep[] = []
  let left = Math.max(0, seconds)
  let n = 1
  while (left > 0) {
    const chunk = Math.min(maxStep, left)
    left -= chunk
    const last = left === 0
    steps.push({
      id: `${prefix}-${n}`,
      advanceSeconds: chunk,
      snapshot: { sitePct: pct },
      expected: last ? expected : { stale: false },
      expectedKey: last ? expectedKey : 'sites:simulator.expected.holding',
      values: last ? undefined : { pct, seconds: chunk },
    })
    n += 1
  }
  return steps
}

/** Steps that reach ACTIVE: cross the trigger, hold past the stabilisation time. */
function toActive(ctx: PresetContext): PresetStep[] {
  return [
    {
      id: 'cross',
      snapshot: { sitePct: ctx.triggerPct },
      expected: { state: 'PENDING' },
      expectedKey: 'sites:simulator.expected.pending',
      values: { pct: ctx.triggerPct },
    },
    ...hold(
      ctx.triggerPct,
      ctx.stabilisationS + 30,
      { state: 'ACTIVE' },
      'sites:simulator.expected.active',
      'stabilise',
      maxHoldStepS(ctx.staleLimitS)
    ),
  ]
}

export function buildPreset(id: string, ctx: PresetContext): Preset | null {
  const trigger = ctx.triggerPct
  const staleLimit = ctx.staleLimitS ?? DEFAULT_STALE_LIMIT_S
  const maxStep = maxHoldStepS(staleLimit)
  const meta = (n: string) => ({
    id: n,
    titleKey: `sites:simulator.presets.${n}.title`,
    descriptionKey: `sites:simulator.presets.${n}.description`,
  })
  switch (id) {
    case 'AT-01':
      return {
        ...meta(id),
        steps: [
          {
            id: 'low',
            snapshot: { sitePct: clamp(trigger - 15) },
            expected: { state: 'IDLE', stale: false },
            expectedKey: 'sites:simulator.expected.idleNoCandidate',
            values: { pct: clamp(trigger - 15) },
          },
        ],
      }
    case 'AT-02':
      return {
        ...meta(id),
        steps: [
          {
            id: 'cross',
            snapshot: { sitePct: trigger },
            expected: { state: 'PENDING' },
            expectedKey: 'sites:simulator.expected.pending',
            values: { pct: trigger },
          },
          ...hold(
            trigger,
            Math.max(maxStep, ctx.stabilisationS - 60),
            { state: 'PENDING' },
            'sites:simulator.expected.stillPending',
            'wait',
            maxStep
          ),
          {
            id: 'drop',
            advanceSeconds: 30,
            snapshot: { sitePct: clamp(trigger - 2) },
            expected: { state: 'IDLE' },
            expectedKey: 'sites:simulator.expected.notStable',
            values: { pct: clamp(trigger - 2) },
          },
        ],
      }
    case 'AT-03':
      return { ...meta(id), steps: toActive(ctx) }
    case 'AT-04':
      return {
        ...meta(id),
        steps: [
          ...toActive(ctx),
          {
            id: 'higher',
            advanceSeconds: 30,
            snapshot: { sitePct: clamp(trigger + 2) },
            expected: { state: 'ACTIVE' },
            expectedKey: 'sites:simulator.expected.noCandidate',
            values: { pct: clamp(trigger + 2) },
          },
        ],
      }
    case 'AT-05':
      return {
        ...meta(id),
        steps: [
          ...toActive(ctx),
          {
            id: 'same-shape',
            advanceSeconds: 30,
            snapshot: { sitePct: clamp(trigger + 5), zonePcts: [60, 50], restPct: 70 },
            expected: { state: 'ACTIVE' },
            expectedKey: 'sites:simulator.expected.noMaterialChange',
            values: { pct: clamp(trigger + 5) },
          },
          {
            id: 'new-recommendation',
            advanceSeconds: 30,
            snapshot: { sitePct: clamp(trigger + 5), zonePcts: [50, 90], restPct: 70 },
            expected: { state: 'ACTIVE' },
            expectedKey: 'sites:simulator.expected.newRecommendation',
            values: { pct: clamp(trigger + 5) },
          },
        ],
      }
    case 'AT-06':
      return {
        ...meta(id),
        steps: [
          ...toActive(ctx),
          {
            id: 'reset',
            advanceSeconds: 30,
            snapshot: { sitePct: clamp(ctx.resetPct - 1) },
            expected: { state: 'IDLE' },
            expectedKey: 'sites:simulator.expected.reset',
            values: { pct: clamp(ctx.resetPct - 1) },
          },
          {
            id: 'rise',
            advanceSeconds: 30,
            snapshot: { sitePct: trigger },
            expected: { state: 'PENDING' },
            expectedKey: 'sites:simulator.expected.newCycle',
            values: { pct: trigger },
          },
        ],
      }
    case 'AT-07':
      return {
        ...meta(id),
        steps: [
          {
            id: 'zone-full',
            snapshot: { sitePct: 85, zonePcts: [98, 55], restPct: 60 },
            expected: { state: 'IDLE', recommendation: 'some' },
            expectedKey: 'sites:simulator.expected.recommendOther',
            values: { pct: 85 },
          },
        ],
      }
    case 'AT-08':
      return {
        ...meta(id),
        steps: [
          {
            id: 'fresh',
            snapshot: { sitePct: 60, restPct: 50 },
            expected: { stale: false },
            expectedKey: 'sites:simulator.expected.fresh',
          },
          {
            id: 'silence',
            advanceSeconds: staleLimit + 60,
            expected: { stale: true },
            expectedKey: 'sites:simulator.expected.staleData',
            values: { seconds: staleLimit + 60 },
          },
          {
            id: 'zone-offline',
            snapshot: { sitePct: 60, restPct: 50, offlineZones: [0] },
            expected: { stale: false },
            expectedKey: 'sites:simulator.expected.zoneUnknown',
          },
        ],
      }
    default:
      return null
  }
}

// ----------------------------------------------------------------------------

export interface Observed {
  state: EngineState
  stale: boolean
  recommendedZoneId: string | null
}

export function observedFromLive(live: SiteLiveResponse): Observed {
  return {
    state: live.engine?.state ?? 'IDLE',
    stale: live.availability.stale,
    recommendedZoneId: live.availability.recommended_zone_id,
  }
}

export type MatchResult = 'match' | 'differs' | 'unchecked'

/** Compares only the fields the expectation names. */
export function matchExpectation(expected: Expectation, observed: Observed): MatchResult {
  let checked = false
  const compare = (ok: boolean): boolean => {
    checked = true
    return ok
  }
  const results = [
    expected.state !== undefined ? compare(expected.state === observed.state) : true,
    expected.stale !== undefined ? compare(expected.stale === observed.stale) : true,
    expected.recommendation !== undefined
      ? compare((expected.recommendation === 'some') === (observed.recommendedZoneId !== null))
      : true,
  ]
  if (!checked) return 'unchecked'
  return results.every(Boolean) ? 'match' : 'differs'
}

// ----------------------------------------------------------------------------

export interface SimZone {
  slug: string
  name: string
  capacity: number
}

export interface SimFigures {
  capacity: number
  occupied: number
  health: Health
}

/** Zone list for the simulator from the live view (display order as served). */
export function simZonesFromLive(zones: LiveZone[], defaultCapacity = 50): SimZone[] {
  return zones.map((z) => ({ slug: z.id, name: z.name, capacity: z.capacity ?? defaultCapacity }))
}

const occupiedFor = (capacity: number, pct: number) => Math.round((capacity * clamp(pct)) / 100)

/** Intake body for a figures set; free = capacity - occupied, other counts zero. */
export function buildOccupancyRequest(
  slug: string,
  site: SimFigures,
  zones: Array<SimFigures & { zoneId: string; name?: string }>
): MockOccupancyRequest {
  const counts = (f: SimFigures) => ({
    capacity: f.capacity,
    occupied: f.occupied,
    freeUsable: Math.max(0, f.capacity - f.occupied),
    freeReserved: 0,
    freeDisabled: 0,
    unknown: 0,
    health: f.health,
  })
  return {
    siteId: slug,
    site: counts(site),
    zones: zones.map((z) => ({ zoneId: z.zoneId, name: z.name, ...counts(z) })),
  }
}

/** Snapshot of a preset step for the given site. */
export function snapshotFromSpec(
  slug: string,
  siteCapacity: number,
  zones: SimZone[],
  spec: SnapshotSpec
): MockOccupancyRequest {
  const rest = spec.restPct ?? spec.sitePct
  return buildOccupancyRequest(
    slug,
    { capacity: siteCapacity, occupied: occupiedFor(siteCapacity, spec.sitePct), health: 'OK' },
    zones.map((zone, index) => {
      const offline = spec.offlineZones?.includes(index) ?? false
      return {
        zoneId: zone.slug,
        name: zone.name,
        capacity: zone.capacity,
        occupied: occupiedFor(zone.capacity, spec.zonePcts?.[index] ?? rest),
        health: offline ? ('OFFLINE' as const) : ('OK' as const),
      }
    })
  )
}
