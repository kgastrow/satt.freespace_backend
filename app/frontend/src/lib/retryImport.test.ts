/**
 * retryImport: the recovery path for a chunk a deploy removed.
 *
 * The guard is the point of these tests. The previous implementation cleared it
 * on the `load` event — which fires on the page the reload just produced — so a
 * chunk that was genuinely gone reloaded forever.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import { retryImport, isChunkLoadError } from './retryImport'

const reload = vi.fn()

beforeEach(() => {
  sessionStorage.clear()
  reload.mockClear()
  Object.defineProperty(window, 'location', {
    value: { ...window.location, reload },
    writable: true,
    configurable: true,
  })
})

afterEach(() => {
  vi.useRealTimers()
})

const chunkError = () => new TypeError('Failed to fetch dynamically imported module: /assets/x.js')

describe('isChunkLoadError', () => {
  it('accepts the TypeError browsers actually throw', () => {
    expect(isChunkLoadError(chunkError())).toBe(true)
  })

  it('accepts the message-only variants', () => {
    expect(isChunkLoadError(new Error('ChunkLoadError: Loading chunk 42 failed'))).toBe(true)
    expect(isChunkLoadError(new Error('Importing a module script failed'))).toBe(true)
  })

  it('rejects an ordinary application error', () => {
    expect(isChunkLoadError(new RangeError('nope'))).toBe(false)
  })
})

describe('retryImport', () => {
  it('passes a successful import straight through', async () => {
    await expect(retryImport(async () => 'ok')).resolves.toBe('ok')
    expect(reload).not.toHaveBeenCalled()
  })

  it('retries once and succeeds without reloading', async () => {
    const importFn = vi.fn().mockRejectedValueOnce(chunkError()).mockResolvedValueOnce('ok')

    await expect(retryImport(importFn)).resolves.toBe('ok')
    expect(importFn).toHaveBeenCalledTimes(2)
    expect(reload).not.toHaveBeenCalled()
  })

  it('does not retry an error that is not a chunk failure', async () => {
    const boom = new RangeError('boom')
    const importFn = vi.fn().mockRejectedValue(boom)

    await expect(retryImport(importFn)).rejects.toBe(boom)
    expect(importFn).toHaveBeenCalledTimes(1)
    expect(reload).not.toHaveBeenCalled()
  })

  it('reloads once when the retry also fails', async () => {
    const importFn = vi.fn().mockRejectedValue(chunkError())

    // Never settles by design — the page is going away.
    let settled = false
    void retryImport(importFn).then(
      () => (settled = true),
      () => (settled = true)
    )
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1))

    expect(importFn).toHaveBeenCalledTimes(2)
    expect(settled).toBe(false)
  })

  it('refuses a second reload inside the guard window, surfacing the error instead', async () => {
    const importFn = vi.fn().mockRejectedValue(chunkError())

    void retryImport(importFn)
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1))

    // The reloaded page tries the same missing chunk again.
    await expect(retryImport(importFn)).rejects.toThrow(
      /Failed to fetch dynamically imported module/
    )
    expect(reload).toHaveBeenCalledTimes(1)
  })

  it('allows a reload again once the guard window has passed', async () => {
    const importFn = vi.fn().mockRejectedValue(chunkError())

    void retryImport(importFn)
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(1))

    sessionStorage.setItem('app:chunk-reload-at', String(Date.now() - 60_000))

    void retryImport(importFn)
    await vi.waitFor(() => expect(reload).toHaveBeenCalledTimes(2))
  })
})
