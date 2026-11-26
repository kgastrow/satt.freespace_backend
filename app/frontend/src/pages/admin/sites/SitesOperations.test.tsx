import { describe, it, expect, vi, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '@/test/utils'
import { server, API_BASE } from '@/test/server'
import { createAuthState } from '@/test/fixtures'
import {
  administratorSiteUser,
  historyFixture,
  viewerSiteUser,
  eventsFixture,
  liveFixture,
  siteFixture,
} from '@/test/sitesHandlers'
import { SitesListPage } from './SitesListPage'
import { SiteLivePage } from './SiteLivePage'
import { SiteEventsPage } from './SiteEventsPage'
import { SiteHistoryPage } from './SiteHistoryPage'
import { SiteDevicesPage } from './SiteDevicesPage'
import { DeviceStatsPage } from './DeviceStatsPage'
import { SimulatorPage } from './SimulatorPage'
import { SimulatorPanel } from '@/features/sites/components/SimulatorPanel'

const MOCK_BASE = 'http://localhost:8000/mock'
const admin = createAuthState(administratorSiteUser)
const viewer = createAuthState(viewerSiteUser)

function renderSitePage(element: React.ReactElement, tab: string, preloadedState = admin) {
  return render(<div />, {
    preloadedState,
    route: `/admin/sites/site-1/${tab}`,
    routes: [{ path: `/admin/sites/:siteId/${tab}`, element }],
  })
}

describe('Sites list live columns', () => {
  it('shows data age, stale flag, engine state, occupancy, recommendation and devices from the summary', async () => {
    render(<SitesListPage />, { preloadedState: admin })
    expect(await screen.findByText('Alice Lane')).toBeInTheDocument()
    expect(await screen.findByText('Basement 1')).toBeInTheDocument()
    expect(screen.getByText('41')).toBeInTheDocument()
    expect(screen.getByText('live.stale')).toBeInTheDocument()
    expect(screen.getByText('engineState.PENDING')).toBeInTheDocument()
    expect(screen.getByText('sites:age.minutes')).toBeInTheDocument()
    expect(screen.getByText('sites:list.occupancyValue')).toBeInTheDocument()
  })

  it('still lists sites when the summary fails', async () => {
    server.use(http.get(`${API_BASE}/admin/sites/summary`, () => HttpResponse.json({}, { status: 500 })))
    render(<SitesListPage />, { preloadedState: admin })
    expect(await screen.findByText('Alice Lane')).toBeInTheDocument()
    expect(screen.queryByText('Basement 1')).not.toBeInTheDocument()
  })
})

describe('SiteLivePage', () => {
  it('shows the zone table as the app sees it, with recommended and not-enabled markers', async () => {
    renderSitePage(<SiteLivePage />, 'live')
    const b1 = await screen.findByTestId('zone-row-b1')
    expect(within(b1).getByText('status.AVAILABLE')).toBeInTheDocument()
    expect(within(b1).getByText('live.zones.recommended')).toBeInTheDocument()
    expect(within(b1).getByText('70%')).toBeInTheDocument()
    const b2 = screen.getByTestId('zone-row-b2')
    expect(b2).toHaveAttribute('data-enabled', 'false')
    expect(within(b2).getByText('live.zones.notEnabled')).toBeInTheDocument()
    expect(within(b2).getByText('status.FULL')).toBeInTheDocument()
  })

  it('states the engine timers in words in the site time zone and the in-flight advisory', async () => {
    renderSitePage(<SiteLivePage />, 'live')
    await screen.findByTestId('zone-row-b1')
    expect(screen.getByTestId('engine-timers')).toHaveTextContent('live.engine.pending')
    expect(screen.getByText('live.engine.inflight.title')).toBeInTheDocument()
    expect(screen.getByText('live.engine.lastNotifiedValue')).toBeInTheDocument()
  })

  it('shows the server error', async () => {
    server.use(
      http.get(`${API_BASE}/admin/sites/:id/live`, () =>
        HttpResponse.json({ detail: { detail: 'x', detail_code: 'site.not_found' } }, { status: 404 })
      )
    )
    renderSitePage(<SiteLivePage />, 'live')
    expect(await screen.findByText('sites:live.loadError')).toBeInTheDocument()
  })
})

describe('SiteEventsPage', () => {
  it('lists events, expands one to show counts, repeat count and rendered text', async () => {
    const { user } = renderSitePage(<SiteEventsPage />, 'events')
    const row = await screen.findByTestId('event-row-event-1')
    expect(within(row).getByText('sites:events.types.CANDIDATE')).toBeInTheDocument()
    expect(within(row).getByText('×3')).toBeInTheDocument()
    await user.click(within(row).getByRole('button', { name: 'sites:events.expand' }))
    const detail = await screen.findByTestId('event-detail-event-1')
    expect(within(detail).getByText('events.outcomes.SENT')).toBeInTheDocument()
    expect(within(detail).getByText('Alice Lane parking')).toBeInTheDocument()
    expect(within(detail).getByText('events.detail.repeatValue')).toBeInTheDocument()
    expect(detail).not.toHaveTextContent(/device.?id|token/i)
  })

  it('pages through results using offset', async () => {
    const offsets: string[] = []
    server.use(
      http.get(`${API_BASE}/admin/sites/:id/events`, ({ request }) => {
        offsets.push(new URL(request.url).searchParams.get('offset') ?? '')
        return HttpResponse.json({ items: eventsFixture, total: 60, limit: 25, offset: 0 })
      })
    )
    const { user } = renderSitePage(<SiteEventsPage />, 'events')
    await screen.findByTestId('event-row-event-1')
    await user.click(screen.getByRole('button', { name: 'sites:events.next' }))
    await waitFor(() => expect(offsets).toContain('25'))
    expect(offsets[0]).toBe('0')
  })

  it('exports the current filter as a CSV download through the API layer', async () => {
    const createObjectURL = vi.fn(() => 'blob:csv')
    const revokeObjectURL = vi.fn()
    Object.assign(URL, { createObjectURL, revokeObjectURL })
    let exportUrl = ''
    server.use(
      http.get(`${API_BASE}/admin/sites/:id/events/export.csv`, ({ request }) => {
        exportUrl = request.url
        return new HttpResponse('a,b\n', { headers: { 'Content-Type': 'text/csv' } })
      })
    )
    const { user } = renderSitePage(<SiteEventsPage />, 'events')
    await screen.findByTestId('event-row-event-1')
    await user.click(screen.getByRole('button', { name: /sites:events.export/ }))
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled())
    expect(exportUrl).toContain('/events/export.csv')
    expect(exportUrl).not.toContain('limit=')
  })

  it('shows the server error', async () => {
    server.use(http.get(`${API_BASE}/admin/sites/:id/events`, () => HttpResponse.json({}, { status: 500 })))
    renderSitePage(<SiteEventsPage />, 'events')
    expect(await screen.findByText('sites:events.loadError')).toBeInTheDocument()
  })
})

describe('Test push and announcement dialogs (site shell)', () => {
  beforeEach(() => {
    server.use(
      http.get(`${API_BASE}/admin/sites/:id`, () =>
        HttpResponse.json({
          id: 'site-1',
          organization_id: 'org-1',
          slug: 'absa-alice-lane',
          name: 'Alice Lane',
          time_zone: 'Africa/Johannesburg',
          fcm_topic: 'freespace-alice-lane',
          managed: false,
          listed: true,
          created_time: null,
          updated_time: null,
        })
      )
    )
  })

  it('hides both buttons from viewers', async () => {
    renderSitePage(<SiteLivePage />, 'live', viewer)
    await screen.findByTestId('zone-row-b1')
    expect(screen.queryByRole('button', { name: /push.test.open/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /push.announce.open/ })).not.toBeInTheDocument()
  })

  it('sends a device test push and words the result as accepted by FCM', async () => {
    let body: unknown
    server.use(
      http.post(`${API_BASE}/admin/sites/:id/test-push`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          message: 'ok',
          message_code: 'site_push.test_sent',
          event_id: 'e',
          target: 'device',
          outcome: 'ACCEPTED_BY_FCM',
          accepted_by_fcm: true,
          latency_ms: 150,
        })
      })
    )
    const { user } = renderSitePage(<SiteLivePage />, 'live')
    await user.click(await screen.findByRole('button', { name: /push.test.open/ }))
    const send = screen.getByRole('button', { name: 'sites:push.test.send' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('sites:push.test.suffixLabel'), 'abc123')
    expect(send).toBeEnabled()
    await user.click(send)
    expect(await screen.findByText('push.result.accepted')).toBeInTheDocument()
    expect(body).toEqual({ target: 'device', device_suffix: 'abc123' })
    expect(screen.queryByText(/delivered/i)).not.toBeInTheDocument()
  })

  it('requires typing the topic name for a topic test push', async () => {
    const { user } = renderSitePage(<SiteLivePage />, 'live')
    await user.click(await screen.findByRole('button', { name: /push.test.open/ }))
    await user.click(screen.getByLabelText('sites:push.test.targetTopic'))
    expect(screen.getByText('push.topicWarning')).toBeInTheDocument()
    const send = screen.getByRole('button', { name: 'sites:push.test.send' })
    expect(send).toBeDisabled()
    const input = screen.getByLabelText('push.confirmLabel')
    await user.type(input, 'wrong')
    expect(send).toBeDisabled()
    await user.clear(input)
    await user.type(input, 'freespace-alice-lane')
    expect(send).toBeEnabled()
  })

  it('shows each backend error of a device push with its own message', async () => {
    server.use(
      http.post(`${API_BASE}/admin/sites/:id/test-push`, () =>
        HttpResponse.json(
          { detail: { detail: 'No device', detail_code: 'site_push.device_not_found' } },
          { status: 404 }
        )
      )
    )
    const { user } = renderSitePage(<SiteLivePage />, 'live')
    await user.click(await screen.findByRole('button', { name: /push.test.open/ }))
    await user.type(screen.getByLabelText('sites:push.test.suffixLabel'), 'abc123')
    await user.click(screen.getByRole('button', { name: 'sites:push.test.send' }))
    expect(await screen.findByText('No device')).toBeInTheDocument()
  })

  it('announcement needs a message and the typed topic, and sends both', async () => {
    let body: unknown
    server.use(
      http.post(`${API_BASE}/admin/sites/:id/announcements`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          message: 'ok',
          message_code: 'site_push.announcement_sent',
          event_id: 'e',
          target: 'topic',
          outcome: 'ACCEPTED_BY_FCM',
          accepted_by_fcm: true,
          latency_ms: 90,
        })
      })
    )
    const { user } = renderSitePage(<SiteLivePage />, 'live')
    await user.click(await screen.findByRole('button', { name: /push.announce.open/ }))
    const send = screen.getByRole('button', { name: 'sites:push.announce.send' })
    await user.type(screen.getByLabelText('sites:push.announce.messageLabel'), 'Car park closes at 18:00')
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('push.confirmLabel'), 'freespace-alice-lane')
    await user.click(send)
    expect(await screen.findByText('push.result.accepted')).toBeInTheDocument()
    expect(body).toEqual({ message: 'Car park closes at 18:00', confirm_topic: 'freespace-alice-lane' })
  })
})

describe('Device statistics', () => {
  it('site tab shows counts by platform and version', async () => {
    renderSitePage(<SiteDevicesPage />, 'devices')
    expect(await screen.findByText('devices.total')).toBeInTheDocument()
    expect(screen.getByText('57')).toBeInTheDocument()
    expect(screen.getByText('devices.platforms.ANDROID')).toBeInTheDocument()
    expect(screen.getByText('1.2.0')).toBeInTheDocument()
    expect(screen.getByText('devices.unknownVersion')).toBeInTheDocument()
    expect(screen.queryByText('devices.bySite')).not.toBeInTheDocument()
  })

  it('section page adds the per-site breakdown', async () => {
    render(<DeviceStatsPage />, { preloadedState: admin })
    expect(await screen.findByText('devices.bySite')).toBeInTheDocument()
    expect(screen.getByText('Alice Lane')).toBeInTheDocument()
  })
})

describe('SiteHistoryPage', () => {
  it('draws the chart with legend, reference lines and an accessible table view', async () => {
    const { user } = renderSitePage(<SiteHistoryPage />, 'history')
    expect(await screen.findByTestId('occupancy-chart')).toBeInTheDocument()
    expect(screen.getByText('history.triggerLine')).toBeInTheDocument()
    expect(screen.getByText('history.resetLine')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Alice Lane/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Basement 1/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'history.showTable' }))
    const table = screen.getByTestId('history-table')
    // the zone has no data at 09:00 and the site has a hole between: shown as no data, not 0
    expect(within(table).getAllByText('history.noData').length).toBeGreaterThan(0)
    expect(within(table).queryByText('0%')).not.toBeInTheDocument()
  })

  it('shows an empty state for a day without data', async () => {
    server.use(
      http.get(`${API_BASE}/admin/sites/:id/history`, () =>
        HttpResponse.json({ ...historyFixture, site: [], zones: [] })
      )
    )
    renderSitePage(<SiteHistoryPage />, 'history')
    expect(await screen.findByTestId('history-empty')).toBeInTheDocument()
  })

  it('requests the chosen day and moves back a day', async () => {
    const dates: Array<string | null> = []
    server.use(
      http.get(`${API_BASE}/admin/sites/:id/history`, ({ request }) => {
        dates.push(new URL(request.url).searchParams.get('date'))
        return HttpResponse.json(historyFixture)
      })
    )
    const { user } = renderSitePage(<SiteHistoryPage />, 'history')
    await screen.findByTestId('occupancy-chart')
    await user.click(screen.getByRole('button', { name: 'sites:history.previousDay' }))
    await waitFor(() => expect(dates.length).toBe(2))
    expect(dates[0]).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(dates[1]! < dates[0]!).toBe(true)
  })
})

describe('SimulatorPage', () => {
  it('says it is not available when mock mode is off (GET /mock/status is 404)', async () => {
    render(<SimulatorPage />, { preloadedState: admin })
    expect(await screen.findByTestId('simulator-unavailable')).toBeInTheDocument()
    expect(screen.queryByLabelText('sites:simulator.site')).not.toBeInTheDocument()
  })

  it('shows the site picker when mock mode is on', async () => {
    server.use(
      http.get(`${MOCK_BASE}/status`, () =>
        HttpResponse.json({ mockMode: true, mockTime: '2026-11-26T05:00:00Z', offsetSeconds: 0 })
      )
    )
    render(<SimulatorPage />, { preloadedState: admin })
    expect(await screen.findByText('sites:simulator.notice')).toBeInTheDocument()
    expect(screen.queryByTestId('simulator-unavailable')).not.toBeInTheDocument()
  })
})

describe('SimulatorPanel', () => {
  it('walks AT-01 step by step: posts a camelCase snapshot, then shows expected beside observed', async () => {
    let posted: Record<string, unknown> | null = null
    server.use(
      http.get(`${MOCK_BASE}/status`, () =>
        HttpResponse.json({ mockMode: true, mockTime: '2026-11-26T05:00:00Z', offsetSeconds: 0 })
      ),
      http.post(`${MOCK_BASE}/sites/:slug/occupancy`, async ({ request, params }) => {
        posted = { slug: params.slug, ...((await request.json()) as object) }
        return HttpResponse.json({
          accepted: true,
          receivedAt: '2026-11-26T05:00:00Z',
          site: { stale: false, state: 'IDLE', recommendedZoneId: 'b1' },
        })
      }),
      // after the snapshot the site is idle, as AT-01 expects
      http.get(`${API_BASE}/admin/sites/:id/live`, () =>
        HttpResponse.json({ ...liveFixture, engine: { ...liveFixture.engine!, state: 'IDLE', inflight: false } })
      )
    )
    const { user } = render(<SimulatorPanel site={siteFixture} initial={liveFixture} />, { preloadedState: admin })
    await user.click(screen.getByRole('button', { name: 'AT-01' }))
    expect(screen.getByTestId('preset-step-0')).toHaveTextContent('sites:simulator.expected.idleNoCandidate')
    await user.click(screen.getByRole('button', { name: /sites:simulator.presets.runNext/ }))
    await waitFor(() => expect(screen.getByTestId('preset-match-0')).toHaveTextContent('sites:simulator.presets.match.match'))
    expect(posted).toMatchObject({ slug: 'absa-alice-lane', siteId: 'absa-alice-lane' })
    expect((posted as unknown as { site: { freeUsable: number } }).site.freeUsable).toBeGreaterThan(0)
    expect((posted as unknown as { zones: Array<{ zoneId: string }> }).zones.map((z) => z.zoneId)).toEqual(['b1', 'b2'])
  })

  it('advances the clock', async () => {
    let body: unknown
    server.use(
      http.post(`${MOCK_BASE}/clock`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          mockTime: '2026-11-26T05:05:00Z',
          offsetSeconds: 300,
          tick: { ran: true, sitesEvaluated: 1, sitesFailed: 0, fanoutsEnqueued: 0 },
        })
      })
    )
    const { user } = render(<SimulatorPanel site={siteFixture} initial={liveFixture} />, { preloadedState: admin })
    await user.click(screen.getAllByRole('button', { name: /sites:simulator.clock.advance/ })[0])
    await waitFor(() => expect(body).toEqual({ seconds: 60 }))
  })
})
