/**
 * swUpdate: promoting a staged build, and the cases where the promotion cannot
 * happen quietly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  API_RUNTIME_CACHE,
  applyUpdate,
  clearApiRuntimeCache,
  getUpdateReady,
  markUpdateReady,
  isApplyingUpdate,
  resetUpdateState,
  subscribeUpdateReady,
} from './swUpdate'

const reload = vi.fn()

const unregister = vi.fn(async () => true)

function stubRegistration(waiting: { postMessage: ReturnType<typeof vi.fn> } | null) {
  const registration = { waiting, unregister } as unknown as ServiceWorkerRegistration
  Object.defineProperty(navigator, 'serviceWorker', {
    value: { getRegistration: vi.fn().mockResolvedValue(registration) },
    configurable: true,
  })
  return registration
}

/** PWA disabled, or a browser without service workers: no registration at all. */
function stubNoRegistration() {
  Object.defineProperty(navigator, 'serviceWorker', {
    value: { getRegistration: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  })
}

beforeEach(() => {
  resetUpdateState()
  reload.mockClear()
  unregister.mockClear()
  vi.useFakeTimers()
  Object.defineProperty(window, 'location', {
    value: { ...window.location, reload },
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('markUpdateReady', () => {
  it('notifies subscribers exactly once', () => {
    const listener = vi.fn()
    subscribeUpdateReady(listener)

    markUpdateReady()
    markUpdateReady()

    expect(listener).toHaveBeenCalledTimes(1)
    expect(getUpdateReady()).toBe(true)
  })

  it('stops notifying after unsubscribe', () => {
    const listener = vi.fn()
    subscribeUpdateReady(listener)()

    markUpdateReady()

    expect(listener).not.toHaveBeenCalled()
  })
})

describe('applyUpdate', () => {
  it('promotes the waiting worker rather than reloading straight away', async () => {
    const postMessage = vi.fn()
    markUpdateReady(stubRegistration({ postMessage }))

    await applyUpdate()

    expect(postMessage).toHaveBeenCalledWith({ type: 'SKIP_WAITING' })
    expect(reload).not.toHaveBeenCalled()
    // registerSW's controllerchange handler owns the reload from here.
    expect(isApplyingUpdate()).toBe(true)
  })

  it('reloads anyway if the promoted worker never takes control', async () => {
    markUpdateReady(stubRegistration({ postMessage: vi.fn() }))

    await applyUpdate()
    expect(reload).not.toHaveBeenCalled()

    // postMessage to a worker that has since gone away is dropped silently,
    // which would otherwise leave the user looking at a dead button.
    vi.advanceTimersByTime(3_000)
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('falls back to a plain reload when there is no registration at all', async () => {
    stubNoRegistration()

    await applyUpdate()

    expect(reload).toHaveBeenCalledTimes(1)
    expect(unregister).not.toHaveBeenCalled()
  })

  it('drops a registration with nothing staged before reloading', async () => {
    // The new worker never reached `waiting` (a chunk 404'd mid-deploy, quota,
    // a bad package). A bare reload would be answered by the OLD worker's
    // navigateFallback from precache — same build, banner back in ten minutes.
    stubRegistration(null)

    await applyUpdate()

    expect(unregister).toHaveBeenCalledTimes(1)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(unregister.mock.invocationCallOrder[0]).toBeLessThan(reload.mock.invocationCallOrder[0])
  })

  it('still reloads if unregistering fails', async () => {
    stubRegistration(null)
    unregister.mockRejectedValueOnce(new Error('denied'))

    await applyUpdate()

    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('ignores a second call while one is already in flight', async () => {
    stubRegistration(null)

    await applyUpdate()
    await applyUpdate()

    expect(reload).toHaveBeenCalledTimes(1)
  })
})

describe('clearApiRuntimeCache', () => {
  it('deletes the api-cache runtime cache', async () => {
    const del = vi.fn().mockResolvedValue(true)
    vi.stubGlobal('caches', { delete: del })

    await clearApiRuntimeCache()

    expect(del).toHaveBeenCalledWith(API_RUNTIME_CACHE)
    vi.unstubAllGlobals()
  })

  it('is a no-op where the Cache API is missing or denied', async () => {
    vi.stubGlobal('caches', undefined)
    await expect(clearApiRuntimeCache()).resolves.toBeUndefined()

    vi.stubGlobal('caches', { delete: vi.fn().mockRejectedValue(new Error('denied')) })
    await expect(clearApiRuntimeCache()).resolves.toBeUndefined()
    vi.unstubAllGlobals()
  })
})
