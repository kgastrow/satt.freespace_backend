/**
 * Every API request carries the build it came from.
 *
 * Updates are staged rather than forced now, so a tab can go on running an
 * older bundle for hours instead of the seconds it used to. `X-App-Commit` is
 * how the backend can tell which build it is answering — without it there is no
 * way to know how long that tail actually is.
 *
 * Asserted on a real request rather than by inspecting `prepareHeaders`: the
 * header only matters if it survives all the way onto the wire.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'
import { createUnauthenticatedState } from '@/test/fixtures'

// Stub an absolute base BEFORE `@/store/api` is first imported (hence the
// dynamic imports below — static imports are hoisted above this call).
vi.stubEnv('VITE_API_URL', API_BASE)

let createTestStore: (typeof import('@/test/utils'))['createTestStore']
let pushApi: (typeof import('@/store/api/pushApi'))['pushApi']

beforeAll(async () => {
  ;({ createTestStore } = await import('@/test/utils'))
  ;({ pushApi } = await import('@/store/api/pushApi'))
})

async function captureRequestHeaders(): Promise<Headers> {
  let seen: Headers | null = null
  server.use(
    http.get(`${API_BASE}/notifications/push/vapid-key`, ({ request }) => {
      seen = request.headers
      return HttpResponse.json({ public_key: 'test-key' })
    })
  )

  const store = createTestStore(createUnauthenticatedState())
  await store.dispatch(pushApi.endpoints.getVapidKey.initiate())

  if (!seen) throw new Error('request never reached the handler')
  return seen
}

describe('X-App-Commit', () => {
  it('is sent on API requests', async () => {
    const headers = await captureRequestHeaders()

    expect(headers.get('x-app-commit')).toBeTruthy()
  })

  it('reports the build commit, matching what version.json advertises', async () => {
    const headers = await captureRequestHeaders()

    expect(headers.get('x-app-commit')).toBe(
      import.meta.env.VITE_BUILD_COMMIT || 'development'
    )
  })

  it('is sent even when signed out, so unauthenticated traffic is attributable too', async () => {
    const headers = await captureRequestHeaders()

    expect(headers.get('authorization')).toBeNull()
    expect(headers.get('x-app-commit')).toBeTruthy()
  })
})
