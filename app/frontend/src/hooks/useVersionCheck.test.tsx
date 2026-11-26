/**
 * useVersionCheck: returning to the foreground re-checks the deployed version,
 * because on iOS the polling interval is suspended while backgrounded and
 * reopening the app restores the page instead of navigating — so without this
 * the app never finds out it is running a stale build.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

import { useVersionCheck } from './useVersionCheck'

const BUILT_COMMIT = import.meta.env.VITE_BUILD_COMMIT || 'development'

function serveVersion(commit: string) {
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ version: '1.0.0', commit_hash: commit, build_time: '2026-07-26T04:33:09Z' }),
  })
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
}

function fire(target: Document | Window, type: string) {
  act(() => {
    target.dispatchEvent(new Event(type))
  })
}

describe('useVersionCheck', () => {
  beforeEach(() => {
    localStorage.clear()
    setVisibility('visible')
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('re-checks when the app returns to the foreground', async () => {
    const fetchMock = serveVersion(BUILT_COMMIT)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useVersionCheck())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    // Past the resume throttle, so a genuine foreground event should ask again.
    await act(async () => {
      vi.advanceTimersByTime(31_000)
    })
    fire(document, 'visibilitychange')

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('re-checks on pageshow, which is how iOS restores a backgrounded app', async () => {
    const fetchMock = serveVersion(BUILT_COMMIT)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useVersionCheck())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    await act(async () => {
      vi.advanceTimersByTime(31_000)
    })
    fire(window, 'pageshow')

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('ignores a foreground event that lands inside the throttle window', async () => {
    const fetchMock = serveVersion(BUILT_COMMIT)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useVersionCheck())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    fire(document, 'visibilitychange')
    fire(window, 'pageshow')

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not check while the app is still hidden', async () => {
    const fetchMock = serveVersion(BUILT_COMMIT)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useVersionCheck())
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    await act(async () => {
      vi.advanceTimersByTime(31_000)
    })
    setVisibility('hidden')
    fire(document, 'visibilitychange')

    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('reports an update once a resume check sees a different commit', async () => {
    // A previously seen version is what distinguishes "stale build" from "first
    // ever visit", so seed it the way an earlier check would have.
    localStorage.setItem(
      'lastKnownVersion',
      JSON.stringify({ version: '1.0.0', commit_hash: BUILT_COMMIT, build_time: '' })
    )
    const fetchMock = serveVersion('714b47d3cce4109b76682c6f1577732a48a23b95')
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useVersionCheck())

    await waitFor(() => expect(result.current.hasUpdate).toBe(true))
    expect(result.current.serverVersion?.commit_hash).toBe(
      '714b47d3cce4109b76682c6f1577732a48a23b95'
    )
  })

  it('does not check at all when disabled', async () => {
    const fetchMock = serveVersion(BUILT_COMMIT)
    vi.stubGlobal('fetch', fetchMock)

    renderHook(() => useVersionCheck({ enabled: false }))

    await act(async () => {
      vi.advanceTimersByTime(31_000)
    })
    fire(document, 'visibilitychange')
    fire(window, 'pageshow')

    expect(fetchMock).not.toHaveBeenCalled()
  })
})
