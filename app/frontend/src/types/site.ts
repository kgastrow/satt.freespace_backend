/**
 * Freespace site types (hand-written; mirror the backend serialisers in
 * app/backend/src/serialisers/freespace_*.py - all snake_case).
 */

export type ChangeDirection = 'RISING' | 'BOTH'

export const CHANGE_DIRECTIONS: readonly ChangeDirection[] = ['RISING', 'BOTH']

/** ISO weekday numbers: 1 = Monday ... 7 = Sunday. */
export interface NotificationWindowRule {
  weekdays: number[]
  /** HH:MM, site local time */
  start: string
  /** HH:MM, site local time; must be after start (no overnight span) */
  end: string
}

export interface Site {
  id: string
  organization_id: string
  /** Customer name; set by the list endpoint, may be absent on create/update responses */
  organization_name?: string | null
  slug: string
  name: string
  time_zone: string
  fcm_topic: string
  managed: boolean
  listed: boolean
  created_time: string | null
  updated_time: string | null
}

export interface SiteListResponse {
  items: Site[]
  total: number
  limit: number
  offset: number
}

export interface SiteListParams {
  limit?: number
  offset?: number
  /** Super admin only */
  organization_id?: string
}

export interface CreateSiteRequest {
  slug: string
  name: string
  time_zone?: string
  fcm_topic?: string
  /** Super admin only */
  organization_id?: string
}

export interface UpdateSiteRequest {
  name?: string
  fcm_topic?: string
}

export interface SiteMutationResponse {
  message: string
  message_code: string
  site: Site
}

export interface MessageResponse {
  message: string
  message_code: string
}

export interface SiteConfig {
  site_id: string
  managed: boolean
  listed: boolean
  time_zone: string
  trigger_pct: number
  reset_pct: number
  change_points: number
  change_direction: ChangeDirection
  stabilisation_s: number
  recommendation_margin: number
  stale_limit_s: number
  partial_is_stale: boolean
  recovery_push: boolean
  zone_advisory: boolean
  zone_reset_gap: number
  notification_window: NotificationWindowRule[]
  cooldown_s: number
  daily_cap: number
  push_expiry_s: number
  updated_time: string | null
}

/** Every field optional: omitted fields keep their value server side. */
export type UpdateSiteConfigRequest = Partial<Omit<SiteConfig, 'site_id' | 'updated_time'>>

export interface UpdateSiteConfigResponse {
  message: string
  message_code: string
  config: SiteConfig
}

export type AdvisoryType =
  | 'SITE_INITIAL'
  | 'SITE_CHANGE'
  | 'ZONE_ADVISORY'
  | 'RECOVERY'
  | 'TEST'

export interface SiteTemplate {
  advisory_type: AdvisoryType
  locale: string
  title: string
  body: string
  default_title: string
  default_body: string
  allowed_placeholders: string[]
}

export interface SiteTemplateListResponse {
  items: SiteTemplate[]
}

export interface UpdateSiteTemplateResponse {
  message: string
  message_code: string
  template: SiteTemplate
}

export interface Zone {
  id: string
  site_id: string
  slug: string
  name: string
  display_order: number
  enabled: boolean
  recommendable: boolean
  preferred: boolean
  priority: number
  limited_pct: number
  full_pct: number
  full_min_free: number
  unknown_limit_pct: number
  advisory_pct: number | null
  note: string
  discovered: boolean
  created_time: string | null
  updated_time: string | null
}

export interface ZoneListResponse {
  items: Zone[]
  total: number
}

export interface CreateZoneRequest {
  slug: string
  name: string
  display_order?: number
  enabled?: boolean
  recommendable?: boolean
  preferred?: boolean
  priority?: number
  limited_pct?: number
  full_pct?: number
  full_min_free?: number
  unknown_limit_pct?: number
  advisory_pct?: number | null
  note?: string
}

export interface UpdateZoneRequest {
  name?: string
  display_order?: number
  enabled?: boolean
  recommendable?: boolean
  preferred?: boolean
  priority?: number
  limited_pct?: number
  full_pct?: number
  full_min_free?: number
  unknown_limit_pct?: number
  /** null unsets the zone advisory */
  advisory_pct?: number | null
  note?: string
  /** true clears the `discovered` flag */
  reviewed?: boolean
}

export interface ZoneMutationResponse {
  message: string
  message_code: string
  zone: Zone
}

export interface IngestKey {
  id: string
  site_id: string
  name: string
  key_hint: string
  expires_at: string | null
  revoked_at: string | null
  last_used_at: string | null
  last_used_ip: string | null
  created_by: string | null
  created_time: string
}

export interface IngestKeyListResponse {
  items: IngestKey[]
}

export interface CreateIngestKeyRequest {
  name: string
  /** ISO datetime, must be in the future */
  expires_at?: string | null
}

/** The plaintext `key` is returned once, by the create call only. */
export interface CreateIngestKeyResponse extends IngestKey {
  key: string
  message: string
  message_code: string
}

export interface RevokeIngestKeyResponse {
  key: IngestKey
  message: string
  message_code: string
}

export interface AppKey {
  id: string
  name: string
  key_hint: string
  revoked_at: string | null
  created_by: string | null
  created_time: string
}

export interface AppKeyListResponse {
  items: AppKey[]
}

export interface CreateAppKeyRequest {
  name: string
}

export interface CreateAppKeyResponse extends AppKey {
  key: string
  message: string
  message_code: string
}

export interface RevokeAppKeyResponse {
  key: AppKey
  message: string
  message_code: string
}
