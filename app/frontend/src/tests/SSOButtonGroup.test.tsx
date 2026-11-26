import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { SSOButtonGroup } from '@/components/sso/SSOButtonGroup'
import { server, API_BASE } from '@/test/server'
import { http, HttpResponse } from 'msw'

describe('SSOButtonGroup', () => {
  beforeEach(() => {
    server.resetHandlers()
  })

  it('renders nothing when no providers are enabled', async () => {
    server.use(
      http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
        return HttpResponse.json({ providers: [] })
      })
    )

    const { container } = render(<SSOButtonGroup organizationSlug="test-org" />)

    await waitFor(() => {
      expect(container.firstChild).toBeNull()
    })
  })

  it('renders Google button when Google provider is enabled', async () => {
    server.use(
      http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
        return HttpResponse.json({ providers: ['google'] })
      })
    )

    render(<SSOButtonGroup organizationSlug="test-org" />)

    // The mock i18n returns the translation key directly
    await waitFor(() => {
      expect(screen.getByText('common:sso.continueWithGoogle')).toBeInTheDocument()
    })
  })

  it('shows error message when API request fails', async () => {
    server.use(
      http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
        return HttpResponse.json({ error: 'Server error' }, { status: 500 })
      })
    )

    render(<SSOButtonGroup organizationSlug="test-org" />)

    await waitFor(() => {
      expect(screen.getByText(/failed to load sso providers/i)).toBeInTheDocument()
    })
  })
})
