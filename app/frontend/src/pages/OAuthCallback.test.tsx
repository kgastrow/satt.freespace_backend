/**
 * OAuthCallback tests - the SSO callback has THREE fulfilled outcomes and the
 * page has to tell them apart.
 *
 * The one that matters most is the 2FA challenge. It carries no access_token,
 * so a page that assumes "fulfilled means signed in" stores an undefined token
 * and bounces the user to /login with nothing stashed. For an SSO-only account
 * (no password) there is no other way in, so that is a permanent lockout - it
 * is why the backend gate SSO_TWO_FACTOR_CHALLENGE_ENABLED stayed off until
 * this page learned the shape.
 *
 * These tests drive the real store and the real RTK Query endpoint (MSW stubs
 * the HTTP layer), so the authSlice matcher is exercised alongside the page.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor, screen } from '@testing-library/react'
import { server, API_BASE } from '@/test/server'
import { render } from '@/test/utils'
import { tokens } from '@/test/fixtures'
import { OAuthCallback } from './OAuthCallback'

// The global setup mock returns a NEW `t` on every render. OAuthCallback lists
// `t` in its effect dependencies (harmless in the app, where react-i18next
// memoises `t`), so that mock would re-fire the callback effect forever here.
// Pin a stable `t` for this file.
const stableT = (key: string, options?: Record<string, unknown>) => {
  if (!options) return key
  let result = key
  Object.entries(options).forEach(([optKey, value]) => {
    result = result.replace(`{{${optKey}}}`, String(value))
  })
  return result
}
const stableI18n = { changeLanguage: vi.fn(), language: 'en' }

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT, i18n: stableI18n }),
  Trans: ({ children }: { children: React.ReactNode }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

const CALLBACK_ROUTE = '/sso/google/callback'
const CALLBACK_URL = `${CALLBACK_ROUTE}?code=test-code&state=test-state`

/** Stand-in screens so navigation is observable through what renders. */
const routes = [
  { path: CALLBACK_ROUTE, element: <OAuthCallback /> },
  { path: '/login', element: <div>LOGIN SCREEN</div> },
  { path: '/dashboard', element: <div>DASHBOARD SCREEN</div> },
  { path: '/sso/confirm-link', element: <div>CONFIRM LINK SCREEN</div> },
  { path: '/files', element: <div>FILES SCREEN</div> },
]

function stubCallback(body: Record<string, unknown>) {
  server.use(
    http.get(`${API_BASE}/sso/google/callback`, () => HttpResponse.json(body))
  )
}

function renderCallback() {
  return render(<OAuthCallback />, { route: CALLBACK_URL, routes })
}

describe('OAuthCallback', () => {
  beforeEach(() => {
    // Set before the OAuth redirect; the page reads the provider back from here.
    sessionStorage.setItem('sso_provider', 'google')
  })

  describe('2FA challenge required', () => {
    const challenge = {
      requires_2fa: true,
      two_factor_token: 'challenge-token-abc',
    }

    it('sends the user to the 2FA screen instead of signing them in', async () => {
      stubCallback(challenge)

      const { store } = renderCallback()

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })

      const state = store.getState().auth
      // The challenge token is stashed where the shared TwoFactorVerification
      // screen reads it - the same place the password login puts it.
      expect(state.twoFactor.required).toBe(true)
      expect(state.twoFactor.token).toBe('challenge-token-abc')
      // Crucially: NOT signed in, and no undefined token stored.
      expect(state.isAuthenticated).toBe(false)
      expect(state.token).toBeNull()
    })

    it('does not fall through to the account-linking screen', async () => {
      stubCallback(challenge)

      renderCallback()

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })
      expect(screen.queryByText('CONFIRM LINK SCREEN')).not.toBeInTheDocument()
      expect(sessionStorage.getItem('sso_link_token')).toBeNull()
    })

    it('clears the SSO handshake state it can no longer use', async () => {
      sessionStorage.setItem('sso_return_url', '/files')
      stubCallback(challenge)

      renderCallback()

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })
      expect(sessionStorage.getItem('sso_provider')).toBeNull()
      // The 2FA screen lands on /dashboard, so a stale return URL must not be
      // left behind to leak into the next SSO login.
      expect(sessionStorage.getItem('sso_return_url')).toBeNull()
    })

    it('does not render the failure screen for a challenge', async () => {
      stubCallback(challenge)

      renderCallback()

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })
      expect(screen.queryByText('Authentication Failed')).not.toBeInTheDocument()
    })
  })

  describe('session issued', () => {
    it('stores the token and navigates to the dashboard', async () => {
      stubCallback({ access_token: tokens.validAccessToken })

      const { store } = renderCallback()

      await waitFor(() => {
        expect(screen.getByText('DASHBOARD SCREEN')).toBeInTheDocument()
      })

      const state = store.getState().auth
      expect(state.token).toBe(tokens.validAccessToken)
      expect(state.isAuthenticated).toBe(true)
      // No stray 2FA challenge left in state.
      expect(state.twoFactor.required).toBe(false)
      expect(state.twoFactor.token).toBeNull()
      expect(sessionStorage.getItem('sso_provider')).toBeNull()
    })

    it('honours a safe stored return URL', async () => {
      sessionStorage.setItem('sso_return_url', '/files')
      stubCallback({ access_token: tokens.validAccessToken })

      const { store } = renderCallback()

      await waitFor(() => {
        expect(screen.getByText('FILES SCREEN')).toBeInTheDocument()
      })
      expect(store.getState().auth.isAuthenticated).toBe(true)
      expect(sessionStorage.getItem('sso_return_url')).toBeNull()
    })
  })

  describe('account linking required', () => {
    it('stashes the link token and navigates to the confirmation screen', async () => {
      stubCallback({
        requires_linking: true,
        link_token: 'link-token-xyz',
        email: 'user@example.com',
        provider: 'google',
      })

      const { store } = renderCallback()

      await waitFor(() => {
        expect(screen.getByText('CONFIRM LINK SCREEN')).toBeInTheDocument()
      })

      expect(sessionStorage.getItem('sso_link_token')).toBe('link-token-xyz')
      const state = store.getState().auth
      expect(state.isAuthenticated).toBe(false)
      expect(state.token).toBeNull()
      // A linking response is not a 2FA challenge.
      expect(state.twoFactor.required).toBe(false)
    })
  })

  describe('failures', () => {
    it('shows the failure screen when the callback is rejected', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () =>
          HttpResponse.json({ detail: 'nope' }, { status: 400 })
        )
      )

      const { store } = renderCallback()

      await waitFor(() => {
        expect(screen.getByText('Authentication Failed')).toBeInTheDocument()
      })
      expect(store.getState().auth.isAuthenticated).toBe(false)
    })
  })
})
