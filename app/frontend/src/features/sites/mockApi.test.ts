import { afterEach, describe, expect, it, vi } from 'vitest'
import { configureStore } from '@reduxjs/toolkit'
import { api } from '@/store/api'
import { mockApi } from './mockApi'

function makeStore() {
  return configureStore({
    reducer: { [api.reducerPath]: api.reducer },
    middleware: (gdm) => gdm().concat(api.middleware),
  })
}

async function status(response: Response) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
  const store = makeStore()
  const result = await store.dispatch(mockApi.endpoints.getMockStatus.initiate())
  return result.data
}

describe('getMockStatus', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('is disabled when a 200 answers with an HTML body', async () => {
    const data = await status(
      new Response('<!doctype html><html></html>', {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }),
    )
    expect(data).toEqual({ enabled: false })
  })

  it('is enabled for a 200 with the status JSON', async () => {
    const body = { mockMode: true, mockTime: '2026-01-01T00:00:00Z', offsetSeconds: 5 }
    const data = await status(new Response(JSON.stringify(body), { status: 200 }))
    expect(data).toMatchObject({
      enabled: true,
      mockTime: '2026-01-01T00:00:00Z',
      offsetSeconds: 5,
    })
  })

  it('is disabled on 404', async () => {
    const data = await status(new Response('{"detail":"Not Found"}', { status: 404 }))
    expect(data).toEqual({ enabled: false })
  })
})
