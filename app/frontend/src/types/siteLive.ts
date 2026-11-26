/**
 * Freespace operations types (live view, events, push, statistics, history,
 * mock mode). Hand-written; mirror app/backend/src/serialisers/freespace_stats.py,
 * freespace_events.py, freespace_push.py (snake_case) and freespace_mock.py /
 * freespace_ingest.py (camelCase, mock endpoints only).
 */

// ---------------------------------------------------------------- summary

export type EngineState = 'IDLE' | 'PENDING' | 'ACTIVE'
export type ZoneStatus = 'AVAILABLE' | 'LIMITED' | 'FULL' | 'UNKNOWN'
export type Health = 'OK' | 'PARTIAL' | 'OFFLINE'

export interface SiteSummaryItem {
  id: string
  organization_id: string
  organization_name: string | null
  slug: string
  name: string
  managed: boolean
  listed: boolean
  mode: 'managed' | 'shadow'
  as_of: string | null
  age_seconds: number | null
  stale: boolean
  engine_state: EngineState | null
  capacity: number | null
  occupied: number | null
  occupancy_pct: number | null
  recommended_zone_slug: string | null
  recommended_zone_name: string | null
  devices_opted_in: number
}

export interface SiteSummaryResponse {
  items: SiteSummaryItem[]
  total: number
}

// ---------------------------------------------------------------- live view

export interface LiveZone {
  /** zone slug */
  id: string
  name: string
  enabled: boolean
  recommendable: boolean
  capacity: number | null
  occupied: number | null
  free: number | null
  occupancy_pct: number | null
  status: ZoneStatus
  stale: boolean
  health: Health | null
  as_of: string | null
}

export interface LiveAvailability {
  as_of: string | null
  age_seconds: number | null
  stale: boolean
  capacity: number | null
  occupied: number | null
  free_usable: number | null
  occupancy_pct: number | null
  health: Health | null
  recommended_zone_id: string | null
  top_zones: string[]
  zones: LiveZone[]
}

export interface LiveZoneAdvisory {
  zone: string
  above_since: string | null
  advised: boolean
}

export interface LiveEngine {
  state: EngineState
  state_entered_at: string | null
  pending_since: string | null
  fires_at: string | null
  cycle_id: string | null
  last_notified_pct: number | null
  last_notified_zone_slug: string | null
  last_notified_top_zones: string[]
  last_sent_at: string | null
  current_zone_slug: string | null
  current_zone_since: string | null
  stale: boolean
  stale_since: string | null
  inflight_event_id: string | null
  inflight: boolean
  zone_advisories: LiveZoneAdvisory[]
  last_evaluated_at: string | null
}

export interface LiveSite {
  id: string
  slug: string
  name: string
  managed: boolean
  listed: boolean
  time_zone: string
  stabilisation_s: number
  /** Seconds without data after which the site counts as stale */
  stale_limit_s: number
  trigger_pct: number
  reset_pct: number
}

export interface SiteLiveResponse {
  site: LiveSite
  availability: LiveAvailability
  engine: LiveEngine | null
}

// ---------------------------------------------------------------- devices

export interface DeviceStatsResponse {
  total_devices: number
  opted_in: number
  by_platform: Array<{ platform: string; count: number }>
  by_app_version: Array<{ app_version: string | null; count: number }>
  by_site: Array<{
    site_id: string
    slug: string
    name: string
    devices: number
    opted_in: number
  }>
}

// ---------------------------------------------------------------- history

export interface HistoryPoint {
  at: string
  occupied: number
  capacity: number
  free_usable: number
  occupancy_pct: number | null
  health: Health
}

export interface ZoneSeries {
  /** zone slug */
  id: string
  name: string
  points: HistoryPoint[]
}

export interface SiteHistoryResponse {
  site_id: string
  date: string
  time_zone: string
  start: string
  end: string
  trigger_pct: number
  reset_pct: number
  site: HistoryPoint[]
  zones: ZoneSeries[]
}

// ---------------------------------------------------------------- events

export type EventType =
  | 'STATE_CHANGE'
  | 'CANDIDATE'
  | 'ADVISORY'
  | 'DATA_STALE'
  | 'DATA_RECOVERED'
  | 'INGEST_REJECTED'
  | 'INGEST_INCONSISTENT'
  | 'ZONE_DISCOVERED'
  | 'FCM_ERROR'
  | 'CONFIG_CHANGED'
  | 'TEST_PUSH'
  | 'ANNOUNCEMENT'

export interface SiteEvent {
  id: string
  site_id: string
  occurred_at: string
  last_seen_at: string | null
  repeat_count: number
  type: EventType | string
  reason: string | null
  advisory_type: string | null
  zone_slug: string | null
  recommended_zone_slug: string | null
  figures: Record<string, unknown> | null
  rendered_title: string | null
  rendered_body: string | null
  /** per-reason device counts (BF-58/66), never device ids */
  counts: Record<string, number> | null
  fanout_status: string | null
  fcm_latency_ms: number | null
  details: Record<string, unknown> | null
}

export interface SiteEventListResponse {
  items: SiteEvent[]
  total: number
  limit: number
  offset: number
}

export interface SiteEventQuery {
  type?: string
  reason?: string
  /** ISO datetime, inclusive */
  start?: string
  /** ISO datetime, exclusive */
  end?: string
  limit?: number
  offset?: number
}

// ---------------------------------------------------------------- push

export interface TestPushRequest {
  target: 'device' | 'topic'
  device_suffix?: string
  confirm_topic?: string
}

export interface AnnouncementRequest {
  message: string
  title?: string
  confirm_topic: string
}

export interface PushResponse {
  message: string
  message_code: string
  event_id: string
  target: 'device' | 'topic'
  outcome: string
  accepted_by_fcm: boolean
  latency_ms: number
}

// ---------------------------------------------------------------- mock mode (camelCase)

export interface MockStatus {
  /** false when GET /mock/status answered 404 (or the backend is unreachable) */
  enabled: boolean
  mockTime?: string
  offsetSeconds?: number
}

export type MockHealth = Health

export interface MockCounts {
  capacity: number
  occupied: number
  freeUsable: number
  freeReserved?: number
  freeDisabled?: number
  unknown?: number
}

export interface MockSiteBlock extends MockCounts {
  health: MockHealth
}

export interface MockZoneBlock extends MockCounts {
  zoneId: string
  name?: string
  health: MockHealth
}

export interface MockOccupancyRequest {
  siteId: string
  measuredAt?: string
  site: MockSiteBlock
  zones: MockZoneBlock[]
}

export interface MockOccupancyResponse {
  accepted?: boolean
  receivedAt?: string
  site?: { stale: boolean; state: string; recommendedZoneId: string | null }
  discoveredZones?: string[]
  warnings?: string[]
  ignored?: string
}

export interface MockClockResponse {
  mockTime: string
  offsetSeconds: number
  tick: {
    ran: boolean
    sitesEvaluated: number
    sitesFailed: number
    fanoutsEnqueued: number
  }
}
