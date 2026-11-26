/**
 * MSW handlers and fixtures for the Freespace sites section.
 * Shapes follow app/backend/src/serialisers/freespace_*.py.
 */
import { http, HttpResponse } from 'msw'
import type {
  Site,
  SiteConfig,
  SiteTemplate,
  Zone,
  IngestKey,
  AppKey,
} from '@/types/site'
import type {
  DeviceStatsResponse,
  SiteEvent,
  SiteHistoryResponse,
  SiteLiveResponse,
  SiteSummaryResponse,
} from '@/types/siteLive'
import type { User } from '@/types/auth'
import { regularUser } from './fixtures'

const API_BASE = 'http://localhost:8000/api/v1'

export const siteFixture: Site = {
  id: 'site-1',
  organization_id: 'org-1',
  organization_name: 'Customer One',
  slug: 'absa-alice-lane',
  name: 'Alice Lane',
  time_zone: 'Africa/Johannesburg',
  fcm_topic: 'freespace-alice-lane',
  managed: false,
  listed: true,
  created_time: '2026-01-01T08:00:00Z',
  updated_time: '2026-01-02T08:00:00Z',
}

export const siteConfigFixture: SiteConfig = {
  site_id: 'site-1',
  managed: false,
  listed: true,
  time_zone: 'Africa/Johannesburg',
  trigger_pct: 90,
  reset_pct: 80,
  change_points: 5,
  change_direction: 'RISING',
  stabilisation_s: 300,
  recommendation_margin: 10,
  stale_limit_s: 120,
  partial_is_stale: true,
  recovery_push: false,
  zone_advisory: false,
  zone_reset_gap: 10,
  notification_window: [{ weekdays: [1, 2, 3, 4, 5], start: '06:00', end: '10:00' }],
  cooldown_s: 1800,
  daily_cap: 2,
  push_expiry_s: 1800,
  updated_time: null,
}

export const zonesFixture: Zone[] = [
  {
    id: 'zone-1',
    site_id: 'site-1',
    slug: 'b1',
    name: 'Basement 1',
    display_order: 1,
    enabled: true,
    recommendable: true,
    preferred: false,
    priority: 100,
    limited_pct: 80,
    full_pct: 95,
    full_min_free: 5,
    unknown_limit_pct: 25,
    advisory_pct: 90,
    note: 'Sensed by cameras',
    discovered: false,
    created_time: null,
    updated_time: null,
  },
  {
    id: 'zone-2',
    site_id: 'site-1',
    slug: 'b2',
    name: 'Basement 2',
    display_order: 2,
    enabled: false,
    recommendable: true,
    preferred: false,
    priority: 100,
    limited_pct: 80,
    full_pct: 95,
    full_min_free: 5,
    unknown_limit_pct: 25,
    advisory_pct: null,
    note: '',
    discovered: true,
    created_time: null,
    updated_time: null,
  },
]

export const templatesFixture: SiteTemplate[] = [
  {
    advisory_type: 'SITE_INITIAL',
    locale: 'en',
    title: '{site} parking',
    body: '{topZones} currently have the most available bays.',
    default_title: '{site} parking',
    default_body: '{topZones} currently have the most available bays.',
    allowed_placeholders: ['occupancyPct', 'site', 'topZones', 'zone'],
  },
  {
    advisory_type: 'ZONE_ADVISORY',
    locale: 'en',
    title: '{site} parking',
    body: '{fullZone} is full. {zone} has available bays.',
    default_title: '{site} parking',
    default_body: '{fullZone} is full. {zone} has available bays.',
    allowed_placeholders: ['fullZone', 'occupancyPct', 'site', 'topZones', 'zone'],
  },
]

export const ingestKeysFixture: IngestKey[] = [
  {
    id: 'key-1',
    site_id: 'site-1',
    name: 'ParkIT production',
    key_hint: 'fsi_ab12',
    expires_at: null,
    revoked_at: null,
    last_used_at: '2026-11-24T05:45:00Z',
    last_used_ip: '203.0.113.7',
    created_by: 'user-1',
    created_time: '2026-01-01T08:00:00Z',
  },
  {
    id: 'key-2',
    site_id: 'site-1',
    name: 'Old key',
    key_hint: 'fsi_zz99',
    expires_at: null,
    revoked_at: '2026-06-01T08:00:00Z',
    last_used_at: null,
    last_used_ip: null,
    created_by: null,
    created_time: '2025-01-01T08:00:00Z',
  },
]

export const appKeysFixture: AppKey[] = [
  {
    id: 'app-1',
    name: 'Android 1.0',
    key_hint: 'fsa_1234',
    revoked_at: null,
    created_by: null,
    created_time: '2026-01-01T08:00:00Z',
  },
]

/** Permissions per role (specs/freespace_contracts.md section 7). */
export const viewerSiteUser: User = {
  ...regularUser,
  id: 'user-viewer',
  roles: ['viewer'],
  permissions: ['sites:read', 'site_events:read'],
}

export const administratorSiteUser: User = {
  ...regularUser,
  id: 'user-sites-admin',
  roles: ['admin'],
  permissions: [
    'sites:read',
    'sites:write',
    'site_keys:write',
    'site_events:read',
    'site_push:test',
    'site_push:announce',
  ],
}

export const summaryFixture: SiteSummaryResponse = {
  items: [
    {
      id: 'site-1',
      organization_id: 'org-1',
      organization_name: 'Customer One',
      slug: 'absa-alice-lane',
      name: 'Alice Lane',
      managed: false,
      listed: true,
      mode: 'shadow',
      as_of: '2026-11-26T07:40:00Z',
      age_seconds: 180,
      stale: true,
      engine_state: 'PENDING',
      capacity: 200,
      occupied: 184,
      occupancy_pct: 92,
      recommended_zone_slug: 'b1',
      recommended_zone_name: 'Basement 1',
      devices_opted_in: 41,
    },
  ],
  total: 1,
}

export const liveFixture: SiteLiveResponse = {
  site: {
    id: 'site-1',
    slug: 'absa-alice-lane',
    name: 'Alice Lane',
    managed: false,
    listed: true,
    time_zone: 'Africa/Johannesburg',
    stabilisation_s: 300,
    stale_limit_s: 120,
    trigger_pct: 90,
    reset_pct: 80,
  },
  availability: {
    as_of: '2026-11-26T05:40:00Z',
    age_seconds: 45,
    stale: false,
    capacity: 200,
    occupied: 184,
    free_usable: 16,
    occupancy_pct: 92,
    health: 'OK',
    recommended_zone_id: 'b1',
    top_zones: ['b1'],
    zones: [
      {
        id: 'b1',
        name: 'Basement 1',
        enabled: true,
        recommendable: true,
        capacity: 100,
        occupied: 70,
        free: 30,
        occupancy_pct: 70,
        status: 'AVAILABLE',
        stale: false,
        health: 'OK',
        as_of: '2026-11-26T05:40:00Z',
      },
      {
        id: 'b2',
        name: 'Basement 2',
        enabled: false,
        recommendable: true,
        capacity: 100,
        occupied: 100,
        free: 0,
        occupancy_pct: 100,
        status: 'FULL',
        stale: false,
        health: 'OK',
        as_of: '2026-11-26T05:40:00Z',
      },
    ],
  },
  engine: {
    state: 'PENDING',
    state_entered_at: '2026-11-26T05:41:00Z',
    pending_since: '2026-11-26T05:41:00Z',
    fires_at: '2026-11-26T05:46:00Z',
    cycle_id: 'cycle-1',
    last_notified_pct: 90,
    last_notified_zone_slug: 'b1',
    last_notified_top_zones: ['b1'],
    last_sent_at: '2026-11-25T05:50:00Z',
    current_zone_slug: 'b1',
    current_zone_since: '2026-11-26T05:30:00Z',
    stale: false,
    stale_since: null,
    inflight_event_id: 'event-9',
    inflight: true,
    zone_advisories: [],
    last_evaluated_at: '2026-11-26T05:41:30Z',
  },
}

export const eventsFixture: SiteEvent[] = [
  {
    id: 'event-1',
    site_id: 'site-1',
    occurred_at: '2026-11-26T05:46:00Z',
    last_seen_at: '2026-11-26T05:50:00Z',
    repeat_count: 3,
    type: 'CANDIDATE',
    reason: 'NO_MATERIAL_CHANGE',
    advisory_type: 'SITE_CHANGE',
    zone_slug: null,
    recommended_zone_slug: 'b1',
    figures: { site: { occupancyPct: 92 } },
    rendered_title: 'Alice Lane parking',
    rendered_body: 'Basement 1 has the most bays.',
    counts: { SENT: 12, COOLDOWN: 3 },
    fanout_status: 'COMPLETED',
    fcm_latency_ms: 240,
    details: null,
  },
  {
    id: 'event-2',
    site_id: 'site-1',
    occurred_at: '2026-11-26T05:41:00Z',
    last_seen_at: null,
    repeat_count: 1,
    type: 'STATE_CHANGE',
    reason: 'TRIGGER_CROSSED',
    advisory_type: null,
    zone_slug: null,
    recommended_zone_slug: null,
    figures: null,
    rendered_title: null,
    rendered_body: null,
    counts: null,
    fanout_status: null,
    fcm_latency_ms: null,
    details: null,
  },
]

export const historyFixture: SiteHistoryResponse = {
  site_id: 'site-1',
  date: '2026-11-26',
  time_zone: 'Africa/Johannesburg',
  start: '2026-11-25T22:00:00Z',
  end: '2026-11-26T22:00:00Z',
  trigger_pct: 90,
  reset_pct: 80,
  site: [
    { at: '2026-11-26T05:00:00Z', occupied: 150, capacity: 200, free_usable: 50, occupancy_pct: 75, health: 'OK' },
    { at: '2026-11-26T05:01:00Z', occupied: 160, capacity: 200, free_usable: 40, occupancy_pct: 80, health: 'OK' },
    { at: '2026-11-26T09:00:00Z', occupied: 180, capacity: 200, free_usable: 20, occupancy_pct: 90, health: 'OK' },
  ],
  zones: [
    {
      id: 'b1',
      name: 'Basement 1',
      points: [
        { at: '2026-11-26T05:00:00Z', occupied: 60, capacity: 100, free_usable: 40, occupancy_pct: 60, health: 'OK' },
      ],
    },
  ],
}

export const deviceStatsFixture: DeviceStatsResponse = {
  total_devices: 57,
  opted_in: 41,
  by_platform: [
    { platform: 'ANDROID', count: 40 },
    { platform: 'IOS', count: 17 },
  ],
  by_app_version: [
    { app_version: '1.2.0', count: 50 },
    { app_version: null, count: 7 },
  ],
  by_site: [{ site_id: 'site-1', slug: 'absa-alice-lane', name: 'Alice Lane', devices: 57, opted_in: 41 }],
}

export const siteHandlers = [
  // Literal routes before /admin/sites/:id
  http.get(`${API_BASE}/admin/sites/summary`, () => HttpResponse.json(summaryFixture)),
  http.get(`${API_BASE}/admin/sites/device-stats`, () => HttpResponse.json(deviceStatsFixture)),
  http.get(`${API_BASE}/admin/sites/:id/live`, () => HttpResponse.json(liveFixture)),
  http.get(`${API_BASE}/admin/sites/:id/history`, () => HttpResponse.json(historyFixture)),
  http.get(`${API_BASE}/admin/sites/:id/device-stats`, () => HttpResponse.json(deviceStatsFixture)),
  http.get(`${API_BASE}/admin/sites/:id/events/export.csv`, () =>
    new HttpResponse('occurred_at,type\n2026-11-26T05:46:00Z,CANDIDATE\n', {
      headers: { 'Content-Type': 'text/csv' },
    })
  ),
  http.get(`${API_BASE}/admin/sites/:id/events`, () =>
    HttpResponse.json({ items: eventsFixture, total: eventsFixture.length, limit: 25, offset: 0 })
  ),
  http.post(`${API_BASE}/admin/sites/:id/test-push`, () =>
    HttpResponse.json({
      message: 'Test push accepted by FCM',
      message_code: 'site_push.test_sent',
      event_id: 'event-10',
      target: 'device',
      outcome: 'ACCEPTED_BY_FCM',
      accepted_by_fcm: true,
      latency_ms: 180,
    })
  ),
  http.post(`${API_BASE}/admin/sites/:id/announcements`, () =>
    HttpResponse.json({
      message: 'Announcement accepted by FCM',
      message_code: 'site_push.announcement_sent',
      event_id: 'event-11',
      target: 'topic',
      outcome: 'ACCEPTED_BY_FCM',
      accepted_by_fcm: true,
      latency_ms: 210,
    })
  ),
  // Mock mode lives at the backend root, not under /api/v1; off by default in tests.
  http.get('http://localhost:8000/mock/status', () => new HttpResponse(null, { status: 404 })),
  http.get(`${API_BASE}/admin/sites`, () =>
    HttpResponse.json({ items: [siteFixture], total: 1, limit: 25, offset: 0 })
  ),
  http.get(`${API_BASE}/admin/sites/:id`, () => HttpResponse.json(siteFixture)),
  http.post(`${API_BASE}/admin/sites`, () =>
    HttpResponse.json(
      { message: 'Site created', message_code: 'site.created', site: siteFixture },
      { status: 201 }
    )
  ),
  http.get(`${API_BASE}/admin/sites/:id/config`, () => HttpResponse.json(siteConfigFixture)),
  http.put(`${API_BASE}/admin/sites/:id/config`, async ({ request }) => {
    const body = (await request.json()) as Partial<SiteConfig>
    return HttpResponse.json({
      message: 'Site settings updated',
      message_code: 'site.config_updated',
      config: { ...siteConfigFixture, ...body },
    })
  }),
  http.get(`${API_BASE}/admin/sites/:id/templates`, () =>
    HttpResponse.json({ items: templatesFixture })
  ),
  http.get(`${API_BASE}/admin/sites/:id/zones`, () =>
    HttpResponse.json({ items: zonesFixture, total: zonesFixture.length })
  ),
  http.get(`${API_BASE}/admin/sites/:id/ingest-keys`, () =>
    HttpResponse.json({ items: ingestKeysFixture })
  ),
  http.get(`${API_BASE}/admin/app-keys`, () => HttpResponse.json({ items: appKeysFixture })),
]
