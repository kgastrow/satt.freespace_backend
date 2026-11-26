import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@/test/utils'
import { server, API_BASE } from '@/test/server'
import { createAuthState, superAdminUser } from '@/test/fixtures'
import {
  administratorSiteUser,
  viewerSiteUser,
  siteFixture,
} from '@/test/sitesHandlers'
import { SitesListPage } from './SitesListPage'
import { SiteOverviewPage } from './SiteOverviewPage'
import { SiteSettingsPage } from './SiteSettingsPage'
import { SiteZonesPage } from './SiteZonesPage'
import { SiteTemplatesPage } from './SiteTemplatesPage'
import { SiteIngestKeysPage } from './SiteIngestKeysPage'
import { AppKeysPage } from '../AppKeysPage'

const admin = createAuthState(administratorSiteUser)
const viewer = createAuthState(viewerSiteUser)

function renderSitePage(element: React.ReactElement, tab: string, preloadedState = admin) {
  return render(<div />, {
    preloadedState,
    route: `/admin/sites/site-1${tab}`,
    routes: [{ path: `/admin/sites/:siteId${tab}`, element }],
  })
}

describe('SitesListPage', () => {
  it('lists sites with managed/shadow and listed badges and a create button for administrators', async () => {
    render(<SitesListPage />, { preloadedState: admin })
    expect(await screen.findByText('Alice Lane')).toBeInTheDocument()
    expect(screen.getByText('sites:badges.shadow')).toBeInTheDocument()
    expect(screen.getByText('sites:badges.listed')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sites:list.create/ })).toBeInTheDocument()
    expect(screen.queryByText('sites:fields.customer')).not.toBeInTheDocument()
  })

  it('hides the create button for viewers', async () => {
    render(<SitesListPage />, { preloadedState: viewer })
    expect(await screen.findByText('Alice Lane')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sites:list.create/ })).not.toBeInTheDocument()
  })

  it('shows the customer column for super admins', async () => {
    render(<SitesListPage />, { preloadedState: createAuthState(superAdminUser) })
    expect(await screen.findByText('sites:fields.customer')).toBeInTheDocument()
    // The name comes from the site list itself, not from a capped organization list.
    expect(await screen.findByText('Customer One')).toBeInTheDocument()
  })

  it('shows the server error when loading fails', async () => {
    server.use(
      http.get(`${API_BASE}/admin/sites`, () =>
        HttpResponse.json(
          { detail: { detail: 'Nope', detail_code: 'site.not_found' } },
          { status: 500 }
        )
      )
    )
    render(<SitesListPage />, { preloadedState: admin })
    expect(await screen.findByText('sites:list.loadError')).toBeInTheDocument()
  })
})

describe('SiteOverviewPage', () => {
  it('shows identity, read-only slug and a managed switch with confirmation', async () => {
    const { user } = renderSitePage(<SiteOverviewPage />, '')
    const slug = await screen.findByDisplayValue(siteFixture.slug)
    expect(slug).toHaveAttribute('readonly')
    await user.click(screen.getByRole('switch', { name: 'sites:fields.managed' }))
    expect(
      await screen.findByText('sites:overview.managedConfirmOn.title')
    ).toBeInTheDocument()
    expect(screen.getByText('sites:overview.managedConfirmOn.description')).toBeInTheDocument()
  })

  it('has no write controls for viewers', async () => {
    renderSitePage(<SiteOverviewPage />, '', viewer)
    await screen.findByDisplayValue(siteFixture.slug)
    expect(screen.queryByRole('button', { name: 'sites:actions.save' })).not.toBeInTheDocument()
    expect(screen.queryByText('sites:overview.delete')).not.toBeInTheDocument()
    expect(screen.getByRole('switch', { name: 'sites:fields.managed' })).toBeDisabled()
  })
})

describe('SiteSettingsPage', () => {
  it('renders every setting with the loaded values and the notification window', async () => {
    renderSitePage(<SiteSettingsPage />, '/settings')
    expect(await screen.findByLabelText('sites:settings.fields.trigger_pct.label')).toHaveValue(90)
    expect(screen.getByLabelText('sites:settings.fields.reset_pct.label')).toHaveValue(80)
    expect(screen.getByLabelText('sites:settings.fields.stale_limit_s.label')).toHaveValue(120)
    expect(screen.getByLabelText('sites:settings.fields.push_expiry_s.label')).toHaveValue(1800)
    expect(screen.getByTestId('notification-window-editor')).toBeInTheDocument()
    expect(screen.getByDisplayValue('06:00')).toBeInTheDocument()
  })

  it('blocks saving a reset at or above the trigger and shows the message', async () => {
    const { user } = renderSitePage(<SiteSettingsPage />, '/settings')
    const reset = await screen.findByLabelText('sites:settings.fields.reset_pct.label')
    await user.clear(reset)
    await user.type(reset, '95')
    await user.click(screen.getByRole('button', { name: 'sites:actions.save' }))
    expect(await screen.findByText('sites:validation.resetBelowTrigger')).toBeInTheDocument()
  })

  it('surfaces a server-side rejection', async () => {
    server.use(
      http.put(`${API_BASE}/admin/sites/:id/config`, () =>
        HttpResponse.json(
          {
            detail: {
              detail: 'stale_limit_s must be at least 120',
              detail_code: 'site.invalid_settings',
            },
          },
          { status: 422 }
        )
      )
    )
    const { user } = renderSitePage(<SiteSettingsPage />, '/settings')
    const daily = await screen.findByLabelText('sites:settings.fields.daily_cap.label')
    await user.clear(daily)
    await user.type(daily, '3')
    await user.click(screen.getByRole('button', { name: 'sites:actions.save' }))
    expect(await screen.findByText('stale_limit_s must be at least 120')).toBeInTheDocument()
  })

  it('is read-only for viewers', async () => {
    renderSitePage(<SiteSettingsPage />, '/settings', viewer)
    expect(await screen.findByLabelText('sites:settings.fields.trigger_pct.label')).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'sites:actions.save' })).not.toBeInTheDocument()
  })
})

describe('SiteZonesPage', () => {
  it('lists zones in order, highlights discovered ones and offers review to administrators', async () => {
    renderSitePage(<SiteZonesPage />, '/zones')
    expect(await screen.findByText('Basement 1')).toBeInTheDocument()
    expect(screen.getByText('Basement 2')).toBeInTheDocument()
    expect(screen.getByText('sites:zones.discovered')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'sites:zones.review' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sites:zones.create/ })).toBeInTheDocument()
  })

  it('sends reviewed: true when reviewing', async () => {
    let body: unknown
    server.use(
      http.put(`${API_BASE}/admin/sites/:id/zones/:zoneId`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ message: 'ok', message_code: 'zone.reviewed', zone: {} })
      })
    )
    const { user } = renderSitePage(<SiteZonesPage />, '/zones')
    await user.click(await screen.findByRole('button', { name: 'sites:zones.review' }))
    await waitFor(() => expect(body).toEqual({ reviewed: true }))
  })

  it('has no write controls for viewers', async () => {
    renderSitePage(<SiteZonesPage />, '/zones', viewer)
    expect(await screen.findByText('Basement 1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'sites:zones.review' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sites:zones.create/ })).not.toBeInTheDocument()
  })
})

describe('SiteTemplatesPage', () => {
  it('renders an editor per advisory type with its allowed placeholders and a live preview', async () => {
    renderSitePage(<SiteTemplatesPage />, '/templates')
    expect(await screen.findByTestId('template-SITE_INITIAL')).toBeInTheDocument()
    expect(screen.getByTestId('template-ZONE_ADVISORY')).toBeInTheDocument()
    expect(screen.getByTestId('preview-body-SITE_INITIAL')).toHaveTextContent(
      'Basement 3 and Basement 4 currently have the most available bays.'
    )
    expect(screen.getByTestId('preview-title-SITE_INITIAL')).toHaveTextContent('Alice Lane parking')
  })

  it('warns about a placeholder the type does not provide and disables save', async () => {
    const { user } = renderSitePage(<SiteTemplatesPage />, '/templates')
    const card = await screen.findByTestId('template-SITE_INITIAL')
    const body = card.querySelector('textarea') as HTMLTextAreaElement
    await user.clear(body)
    await user.paste('{fullZone} is full')
    expect(await screen.findByText('sites:templates.unknownTitle')).toBeInTheDocument()
    const save = card.querySelectorAll('button')
    const saveButton = Array.from(save).find((b) => b.textContent === 'sites:actions.save')
    expect(saveButton).toBeDisabled()
  })

  it('surfaces a server-side placeholder rejection', async () => {
    server.use(
      http.put(`${API_BASE}/admin/sites/:id/templates/:type`, () =>
        HttpResponse.json(
          {
            detail: {
              detail: 'Placeholder(s) {zone} not available',
              detail_code: 'site_template.invalid_placeholder',
            },
          },
          { status: 422 }
        )
      )
    )
    const { user } = renderSitePage(<SiteTemplatesPage />, '/templates')
    const card = await screen.findByTestId('template-SITE_INITIAL')
    const body = card.querySelector('textarea') as HTMLTextAreaElement
    await user.type(body, ' extra')
    await user.click(
      Array.from(card.querySelectorAll('button')).find((b) => b.textContent === 'sites:actions.save')!
    )
    expect(await screen.findByText('Placeholder(s) {zone} not available')).toBeInTheDocument()
  })

  it('is read-only for viewers', async () => {
    renderSitePage(<SiteTemplatesPage />, '/templates', viewer)
    const card = await screen.findByTestId('template-SITE_INITIAL')
    expect(card.querySelector('textarea')).toBeDisabled()
    expect(screen.queryByText('sites:templates.reset')).not.toBeInTheDocument()
  })
})

describe('SiteIngestKeysPage', () => {
  it('lists keys with hint, status and last source IP, and the rotation explanation', async () => {
    renderSitePage(<SiteIngestKeysPage />, '/ingest-keys')
    expect(await screen.findByText('ParkIT production')).toBeInTheDocument()
    expect(screen.getByText('fsi_ab12')).toBeInTheDocument()
    expect(screen.getByText('203.0.113.7')).toBeInTheDocument()
    expect(screen.getByText('sites:keys.status.revoked')).toBeInTheDocument()
    expect(screen.getByText('sites:keys.ingest.rotation')).toBeInTheDocument()
    // Only the active key can be revoked
    expect(screen.getAllByRole('button', { name: /sites:keys.revoke/ })).toHaveLength(1)
  })

  it('shows the created key once in a dialog', async () => {
    server.use(
      http.post(`${API_BASE}/admin/sites/:id/ingest-keys`, () =>
        HttpResponse.json(
          { id: 'k3', site_id: 'site-1', name: 'New', key_hint: 'fsi_new0', expires_at: null,
            revoked_at: null, last_used_at: null, last_used_ip: null, created_by: null,
            created_time: '2026-11-26T08:00:00Z', key: 'fsi_PLAINTEXT_SECRET',
            message: 'Created', message_code: 'ingest_key.created' },
          { status: 201 }
        )
      )
    )
    const { user } = renderSitePage(<SiteIngestKeysPage />, '/ingest-keys')
    await user.click(await screen.findByRole('button', { name: /sites:keys.create/ }))
    await user.type(await screen.findByLabelText('keys.fields.name'), 'New')
    await user.click(screen.getByRole('button', { name: 'keys.create' }))
    expect(await screen.findByDisplayValue('fsi_PLAINTEXT_SECRET')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'keys.reveal.copy' })).toBeInTheDocument()
  })

  it('has no create or revoke controls for viewers', async () => {
    renderSitePage(<SiteIngestKeysPage />, '/ingest-keys', viewer)
    expect(await screen.findByText('ParkIT production')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sites:keys.create/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /sites:keys.revoke/ })).not.toBeInTheDocument()
  })
})

describe('AppKeysPage', () => {
  it('lists app keys with create and revoke controls', async () => {
    render(<AppKeysPage />, { preloadedState: createAuthState(superAdminUser) })
    expect(await screen.findByText('Android 1.0')).toBeInTheDocument()
    expect(screen.getByText('fsa_1234')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sites:keys.create/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sites:keys.revoke/ })).toBeInTheDocument()
  })
})
