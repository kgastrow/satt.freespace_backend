/**
 * Token refresh on 401: who gets signed out, and how many refreshes it takes.
 *
 * Two behaviours are load-bearing here.
 *
 * A failed refresh used to end the session no matter WHY it failed. A 502 from
 * a box mid-rolling-restart, or a 429 from a shared address, looks nothing like
 * an expired cookie, but it signed the user out and hard-redirected them to
 * /login all the same. Only 401/403 - the refresh cookie itself being gone,
 * expired, revoked, or the account suspended - may end a session now; anything
 * else waits briefly and retries the original request once.
 *
 * And a cold load fires several authenticated requests at once, so an expired
 * access token produces several simultaneous 401s. They must share one refresh
 * rather than each posting their own to the one endpoint whose failure signs
 * the user out.
 */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { http, HttpResponse, delay } from 'msw'
import { server, API_BASE } from '@/test/server'
import { createAuthState, createUnauthenticatedState, regularUser } from '@/test/fixtures'

// Stub an absolute base BEFORE `@/store/api` is first imported (hence the
// dynamic imports below - static imports are hoisted above this call).
vi.stubEnv('VITE_API_URL', API_BASE)

let createTestStore: (typeof import('@/test/utils'))['createTestStore']
let usersApi: (typeof import('@/features/users/usersApi'))['usersApi']
let authApi: (typeof import('@/features/auth/authApi'))['authApi']
let resetRefreshState: (typeof import('@/store/api'))['resetRefreshState']

beforeAll(async () => {
  ;({ createTestStore } = await import('@/test/utils'))
  ;({ usersApi } = await import('@/features/users/usersApi'))
  ;({ authApi } = await import('@/features/auth/authApi'))
  ;({ resetRefreshState } = await import('@/store/api'))
})

beforeEach(() => {
  // The refresh latch is module state and outlives any single store.
  resetRefreshState()
})

/** Counters shared by the handlers a test installs. */
interface Traffic {
  refreshes: number
  userRequests: number
}

/**
 * Install handlers for `/users/:id` and `/auth/refresh`.
 *
 * `/users/:id` answers 401 until a refresh has succeeded, which is what an
 * expired access token looks like from the client. `refreshResponder` decides
 * what the refresh itself does.
 */
function installHandlers(refreshResponder: () => Response | Promise<Response>): Traffic {
  const traffic: Traffic = { refreshes: 0, userRequests: 0 }
  let refreshSucceeded = false

  server.use(
    http.get(`${API_BASE}/users/:id`, async () => {
      traffic.userRequests++
      // Small delay so concurrent requests land together, before any refresh
      // started by the first of them can resolve.
      await delay(10)
      if (!refreshSucceeded) {
        return HttpResponse.json({ detail: 'Token expired' }, { status: 401 })
      }
      return HttpResponse.json(regularUser)
    }),
    http.post(`${API_BASE}/auth/refresh`, async () => {
      traffic.refreshes++
      await delay(50)
      const response = await refreshResponder()
      if (response.status === 200) refreshSucceeded = true
      return response
    })
  )

  return traffic
}

const refreshOk = () => HttpResponse.json({ access_token: 'refreshed-access-token' })

function authedStore() {
  return createTestStore(createAuthState(regularUser))
}

/** Fire several authenticated requests at once, as a cold load does. */
function fetchUsers(store: ReturnType<typeof authedStore>, ids: string[]) {
  return Promise.all(
    ids.map((id) => store.dispatch(usersApi.endpoints.getUser.initiate(id)))
  )
}

describe('shared refresh', () => {
  it('makes exactly one POST /auth/refresh for concurrent 401s', async () => {
    const traffic = installHandlers(refreshOk)
    const store = authedStore()

    const results = await fetchUsers(store, ['u1', 'u2', 'u3', 'u4'])

    expect(traffic.refreshes).toBe(1)
    // All four still get their data - sharing the refresh must not cost anyone
    // their response.
    for (const result of results) {
      expect(result.data).toMatchObject({ id: regularUser.id })
    }
    expect(store.getState().auth.token).toBe('refreshed-access-token')
  })

  it('refreshes again on a later expiry, so the latch is not sticky', async () => {
    const first = installHandlers(refreshOk)
    const store = authedStore()
    await fetchUsers(store, ['a1', 'a2'])
    expect(first.refreshes).toBe(1)

    // A second expiry later in the session: fresh handlers, fresh 401s.
    const second = installHandlers(refreshOk)
    await fetchUsers(store, ['b1', 'b2'])

    expect(second.refreshes).toBe(1)
  })

  it('never recurses into the refresh endpoint itself', async () => {
    const traffic = installHandlers(() =>
      HttpResponse.json({ detail: 'Invalid refresh token' }, { status: 401 })
    )
    const store = authedStore()

    await store.dispatch(authApi.endpoints.refreshToken.initiate())

    // A 401 on the refresh call must not trigger another refresh.
    expect(traffic.refreshes).toBe(1)
  })
})

describe('only a definitive auth failure ends the session', () => {
  it('keeps the session and retries the request when refresh returns 502', async () => {
    const traffic = installHandlers(
      () => new HttpResponse(null, { status: 502, statusText: 'Bad Gateway' })
    )
    const store = authedStore()

    await fetchUsers(store, ['u1'])

    // Not signed out: a restarting backend says nothing about the session.
    expect(store.getState().auth.token).not.toBeNull()
    expect(store.getState().auth.isAuthenticated).toBe(true)
    // The original request was retried once after the delay.
    expect(traffic.userRequests).toBe(2)
  })

  it('keeps the session when refresh is rate limited (429)', async () => {
    installHandlers(() => new HttpResponse(null, { status: 429 }))
    const store = authedStore()

    await fetchUsers(store, ['u1'])

    expect(store.getState().auth.token).not.toBeNull()
    expect(store.getState().auth.isAuthenticated).toBe(true)
  })

  it('recovers on its own once the backend comes back', async () => {
    installHandlers(() => new HttpResponse(null, { status: 503 }))
    const store = authedStore()
    await fetchUsers(store, ['u1'])
    expect(store.getState().auth.isAuthenticated).toBe(true)

    // Backend recovers; the next 401 refreshes normally. No user action, and
    // no window where the session is stuck broken.
    installHandlers(refreshOk)
    const results = await fetchUsers(store, ['u2'])

    expect(store.getState().auth.token).toBe('refreshed-access-token')
    expect(results[0].data).toMatchObject({ id: regularUser.id })
  })

  it('signs the user out when the refresh cookie is rejected (401)', async () => {
    installHandlers(() =>
      HttpResponse.json({ detail: 'Invalid refresh token' }, { status: 401 })
    )
    const store = authedStore()

    await fetchUsers(store, ['u1'])

    expect(store.getState().auth.token).toBeNull()
    expect(store.getState().auth.isAuthenticated).toBe(false)
  })

  it('signs the user out when refresh is forbidden (403)', async () => {
    installHandlers(() => HttpResponse.json({ detail: 'Suspended' }, { status: 403 }))
    const store = authedStore()

    await fetchUsers(store, ['u1'])

    expect(store.getState().auth.token).toBeNull()
    expect(store.getState().auth.isAuthenticated).toBe(false)
  })
})

describe('signed-out 401s', () => {
  it('does not attempt a refresh when there was no session to expire', async () => {
    const traffic = installHandlers(refreshOk)
    const store = createTestStore(createUnauthenticatedState())

    const results = await fetchUsers(store, ['u1'])

    // No refresh, so no failed refresh, so no bogus "your session has expired"
    // toast and hard redirect to /login for a visitor who was never signed in.
    expect(traffic.refreshes).toBe(0)
    expect(results[0].error).toMatchObject({ status: 401 })
    expect(store.getState().auth.isAuthenticated).toBe(false)
  })
})
