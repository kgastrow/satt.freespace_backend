/**
 * SSOConfirmLinkPage tests.
 *
 * `POST /auth/sso/link` used to accept the link token on its own. A link token
 * only proves that somebody completed an OAuth flow for an address that happens
 * to match an existing account, so anyone able to create a provider account on
 * a victim's email address got a full session on the victim's account. The
 * endpoint now demands proof that the caller controls the existing account:
 * either a bearer session for that same user, or its password re-entered here.
 *
 * That makes this page the client half of a breaking API contract, and two
 * things have to hold for it:
 *
 *   1. The password actually reaches the wire. It is carried in the request
 *      body, so these tests assert the outgoing JSON from an MSW handler rather
 *      than that a mock was called - a payload that typechecks but arrives
 *      empty is exactly the failure mode a mock assertion misses.
 *   2. The refusals are told apart. `detail_code` separates "retype your
 *      password" from "go and sign in" from "try again shortly". The statuses
 *      now differ too (403 wrong password, 401 missing proof, 429 throttled,
 *      503 nonce store down), but the page matches the code FIRST and treats
 *      status only as a fallback - so every error case below asserts on
 *      rendered text, and a wrong code match fails here rather than shipping a
 *      misleading message.
 *
 * The real store and the real RTK Query endpoint are driven throughout; MSW
 * stubs only the HTTP layer.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { waitFor, screen } from '@testing-library/react'
import { server, API_BASE } from '@/test/server'
import { render } from '@/test/utils'
import {
  tokens,
  regularUser,
  createAuthState,
  createUnauthenticatedState,
} from '@/test/fixtures'
import { SSOConfirmLinkPage } from './SSOConfirmLinkPage'

const LINK_ROUTE = '/sso/confirm-link'
const LINK_TOKEN = 'link-token-xyz'
const LINK_URL = `${API_BASE}/auth/sso/link`

/** Stand-in screens so navigation is observable through what renders. */
const routes = [
  { path: LINK_ROUTE, element: <SSOConfirmLinkPage /> },
  { path: '/login', element: <div>LOGIN SCREEN</div> },
  { path: '/dashboard', element: <div>DASHBOARD SCREEN</div> },
]

function renderPage(preloadedState: Record<string, unknown>) {
  return render(<SSOConfirmLinkPage />, { route: LINK_ROUTE, routes, preloadedState })
}

function renderSignedOut() {
  return renderPage(createUnauthenticatedState())
}

function renderSignedIn() {
  return renderPage(createAuthState(regularUser))
}

/** Capture the exact body (and auth header) the page puts on the wire. */
function captureLinkRequest() {
  const seen: { body: Record<string, unknown> | null; authorization: string | null } = {
    body: null,
    authorization: null,
  }
  server.use(
    http.post(LINK_URL, async ({ request }) => {
      seen.authorization = request.headers.get('Authorization')
      seen.body = (await request.json()) as Record<string, unknown>
      return HttpResponse.json({ access_token: tokens.validAccessToken })
    })
  )
  return seen
}

/**
 * Stub a refusal in the shape FastAPI actually produces: `create_http_exception`
 * nests both the message and the code under `detail`.
 */
function stubLinkFailure(status: number, detailCode?: string) {
  server.use(
    http.post(LINK_URL, () =>
      HttpResponse.json(
        {
          detail: detailCode
            ? { detail: 'refused', detail_code: detailCode }
            : 'refused',
        },
        { status }
      )
    )
  )
}

function passwordField() {
  return screen.getByLabelText('auth:sso.linkPasswordLabel')
}

function submitButton() {
  return screen.getByRole('button', { name: 'auth:sso.linkAccount' })
}

describe('SSOConfirmLinkPage', () => {
  beforeEach(() => {
    // Stashed by OAuthCallback when the SSO callback answers requires_linking.
    sessionStorage.setItem('sso_link_token', LINK_TOKEN)
    sessionStorage.setItem('sso_provider', 'google')
  })

  describe('proof input', () => {
    it('asks a signed-out visitor for the existing password', () => {
      renderSignedOut()

      expect(passwordField()).toBeInTheDocument()
      expect(passwordField()).toHaveAttribute('type', 'password')
      expect(screen.getByText('auth:sso.linkPasswordHelp')).toBeInTheDocument()
    })

    it('does not ask for a password when a session already proves control', () => {
      renderSignedIn()

      // The bearer token is the proof, so there is nothing to type. Showing the
      // field here would demand a credential an SSO-only account may not have.
      expect(
        screen.queryByLabelText('auth:sso.linkPasswordLabel')
      ).not.toBeInTheDocument()
      expect(screen.getByText('auth:sso.linkSignedInAs')).toBeInTheDocument()
    })

    it('sends a visitor with no link token back to login', async () => {
      sessionStorage.removeItem('sso_link_token')

      renderSignedOut()

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })
    })
  })

  describe('submit availability', () => {
    it('stays disabled until a signed-out visitor has typed a password', async () => {
      const { user } = renderSignedOut()

      expect(submitButton()).toBeDisabled()

      await user.type(passwordField(), 'hunter2')

      expect(submitButton()).toBeEnabled()
    })

    it('is available immediately when the session is the proof', () => {
      renderSignedIn()

      expect(submitButton()).toBeEnabled()
    })

    it('refuses an empty password submitted with Enter', async () => {
      // Enter routes around the disabled button, so the guard has to hold here
      // too - otherwise the request goes out with no proof and 401s.
      const seen = captureLinkRequest()
      const { user } = renderSignedOut()

      await user.click(passwordField())
      await user.keyboard('{Enter}')

      expect(
        await screen.findByText('auth:sso.linkPasswordRequired')
      ).toBeInTheDocument()
      expect(seen.body).toBeNull()
    })
  })

  describe('request payload', () => {
    it('puts the typed password in the request body', async () => {
      const seen = captureLinkRequest()
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      await waitFor(() => expect(seen.body).not.toBeNull())
      expect(seen.body).toEqual({
        link_token: LINK_TOKEN,
        password: 'hunter2',
      })
    })

    it('submits on Enter from the password field', async () => {
      const seen = captureLinkRequest()
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2{Enter}')

      await waitFor(() => expect(seen.body).not.toBeNull())
      expect(seen.body).toEqual({
        link_token: LINK_TOKEN,
        password: 'hunter2',
      })
    })

    it('omits the password and proves control with the bearer session', async () => {
      const seen = captureLinkRequest()
      const { user } = renderSignedIn()

      await user.click(submitButton())

      await waitFor(() => expect(seen.body).not.toBeNull())
      expect(seen.body).toEqual({ link_token: LINK_TOKEN })
      expect(seen.body).not.toHaveProperty('password')
      expect(seen.authorization).toBe(`Bearer ${tokens.validAccessToken}`)
    })
  })

  describe('success', () => {
    it('stores the session, clears the handshake and lands on the dashboard', async () => {
      captureLinkRequest()
      const { user, store } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      await waitFor(() => {
        expect(screen.getByText('DASHBOARD SCREEN')).toBeInTheDocument()
      })

      const state = store.getState().auth
      expect(state.token).toBe(tokens.validAccessToken)
      expect(state.isAuthenticated).toBe(true)
      // A spent link token must not survive to be replayed on the next visit.
      expect(sessionStorage.getItem('sso_link_token')).toBeNull()
      expect(sessionStorage.getItem('sso_provider')).toBeNull()
    })
  })

  describe('refusals', () => {
    it('tells the user their password was wrong (403 auth.invalid_password)', async () => {
      // 403 rather than 401 so a status-only client can still tell a rejected
      // proof from an absent one. The page matches the code regardless, which
      // is what keeps this correct if the status moves again.
      stubLinkFailure(403, 'auth.invalid_password')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'wrong-password')
      await user.click(submitButton())

      expect(
        await screen.findByText('auth:sso.linkPasswordInvalid')
      ).toBeInTheDocument()
      expect(screen.queryByText('auth:sso.linkProofRequired')).not.toBeInTheDocument()
    })

    it('asks for proof (401 sso.link_proof_required)', async () => {
      stubLinkFailure(401, 'sso.link_proof_required')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(
        await screen.findByText('auth:sso.linkProofRequired')
      ).toBeInTheDocument()
    })

    it('reports linking as temporarily unavailable (503 sso.link_verification_unavailable)', async () => {
      // Raised when the replay-protection nonce store is unreachable; the guard
      // fails closed, so this is a retry-later, not a permanent failure.
      stubLinkFailure(503, 'sso.link_verification_unavailable')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(await screen.findByText('auth:sso.linkUnavailable')).toBeInTheDocument()
    })

    // The two cases below deliberately pair each detail_code with a status that
    // has NO fallback branch. That is what pins the assertion to the code
    // itself: with the status fallbacks in place, a 401/503 would render the
    // right message even if the code string were wrong, and the match would be
    // dead code that merely looks live.
    it('matches sso.link_proof_required on its code, not on 401', async () => {
      stubLinkFailure(403, 'sso.link_proof_required')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(
        await screen.findByText('auth:sso.linkProofRequired')
      ).toBeInTheDocument()
    })

    it('matches sso.link_verification_unavailable on its code, not on 503', async () => {
      stubLinkFailure(500, 'sso.link_verification_unavailable')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(await screen.findByText('auth:sso.linkUnavailable')).toBeInTheDocument()
    })

    it('still guides the user when an unexpected 401 carries no code', async () => {
      stubLinkFailure(401)
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(
        await screen.findByText('auth:sso.linkProofRequired')
      ).toBeInTheDocument()
    })

    it('still guides the user when an unexpected 503 carries no code', async () => {
      stubLinkFailure(503)
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(await screen.findByText('auth:sso.linkUnavailable')).toBeInTheDocument()
    })

    it('falls back to the generic message for an unrecognised failure', async () => {
      stubLinkFailure(400, 'sso.link_token_expired')
      const { user } = renderSignedOut()

      await user.type(passwordField(), 'hunter2')
      await user.click(submitButton())

      expect(await screen.findByText('auth:sso.linkError')).toBeInTheDocument()
    })

    it('keeps the user on the page and the link token intact after a refusal', async () => {
      stubLinkFailure(401, 'auth.invalid_password')
      const { user, store } = renderSignedOut()

      await user.type(passwordField(), 'wrong-password')
      await user.click(submitButton())

      await screen.findByText('auth:sso.linkPasswordInvalid')

      expect(screen.queryByText('DASHBOARD SCREEN')).not.toBeInTheDocument()
      expect(store.getState().auth.isAuthenticated).toBe(false)
      // The backend burns the nonce only after the proof passes, so a mistyped
      // password must leave the token available for a retry.
      expect(sessionStorage.getItem('sso_link_token')).toBe(LINK_TOKEN)
    })
  })

  describe('cancel', () => {
    it('discards the handshake and returns to login', async () => {
      const { user } = renderSignedOut()

      await user.click(screen.getByRole('button', { name: 'common:cancel' }))

      await waitFor(() => {
        expect(screen.getByText('LOGIN SCREEN')).toBeInTheDocument()
      })
      expect(sessionStorage.getItem('sso_link_token')).toBeNull()
      expect(sessionStorage.getItem('sso_provider')).toBeNull()
    })
  })
})
