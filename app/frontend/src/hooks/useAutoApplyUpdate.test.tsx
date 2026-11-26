/**
 * useAutoApplyUpdate: when a staged build is allowed to swap itself in.
 *
 * The rule these tests defend is that a user is never reloaded out of something
 * they cannot resume - a half-typed multi-step form, a one-shot token flow, an
 * export they are watching.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

import { useAutoApplyUpdate, isProtectedPath } from './useAutoApplyUpdate'
import { claimUpdateDeferral, resetUpdateDeferrals } from '@/lib/deferUpdate'

/** Longer than HIDDEN_SETTLE_MS + JITTER_MAX_MS. */
const PAST_EVERY_DELAY = 90_000

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
}

function setPath(pathname: string) {
  Object.defineProperty(window, 'location', {
    value: { ...window.location, pathname },
    writable: true,
    configurable: true,
  })
}

function hide() {
  setVisibility('hidden')
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'))
  })
}

function show() {
  setVisibility('visible')
  act(() => {
    document.dispatchEvent(new Event('visibilitychange'))
  })
}

/**
 * Model iOS: the wall clock moves while the app is suspended, but no timer
 * fires. `setSystemTime` advances Date.now() without running fake timers.
 */
function suspendFor(ms: number) {
  vi.setSystemTime(Date.now() + ms)
}

const LONG_ABSENCE = 6 * 60_000
const SHORT_ABSENCE = 2 * 60_000

beforeEach(() => {
  resetUpdateDeferrals()
  vi.useFakeTimers()
  setVisibility('visible')
  setPath('/dashboard')
})

afterEach(() => {
  vi.useRealTimers()
})

describe('isProtectedPath', () => {
  it.each([
    '/onboarding',
    '/onboarding/step/2',
    '/setup-2fa',
    '/register',
    '/reset-password',
    '/settings/security/export',
  ])('protects %s', (path) => {
    expect(isProtectedPath(path)).toBe(true)
  })

  it.each([
    '/dashboard',
    '/files',
    '/notifications',
    '/settings/account/profile',
    '/admin/users',
  ])('leaves %s updatable', (path) => {
    expect(isProtectedPath(path)).toBe(false)
  })
})

describe('useAutoApplyUpdate', () => {
  it('applies once the app has been backgrounded long enough', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    hide()
    expect(applyUpdate).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))
    expect(applyUpdate).toHaveBeenCalledTimes(1)
  })

  it('never applies while the user is looking at the app', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('stands down if the user comes back before the timer fires', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    hide()
    setVisibility('visible')
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'))
    })
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('does nothing for a build that is merely announced, not staged', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: false, applyUpdate }))

    hide()
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('refuses while something has claimed a deferral', () => {
    const applyUpdate = vi.fn()
    claimUpdateDeferral('upload:avatar')
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    hide()
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('refuses on a route where a reload costs real work', () => {
    const applyUpdate = vi.fn()
    setPath('/onboarding/step/2')
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    hide()
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('re-checks at fire time, not only when the timer was armed', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

    hide()
    // A backgrounded tab can still start work - a notification, a media key.
    claimUpdateDeferral('upload:avatar')
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })

  it('staggers devices so one deploy is not one synchronised stampede', () => {
    const delays: number[] = []
    const random = vi.spyOn(Math, 'random')
    for (const r of [0, 0.5, 1]) {
      random.mockReturnValue(r)
      const applyUpdate = vi.fn()
      const { unmount } = renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))
      hide()
      let elapsed = 0
      while (!applyUpdate.mock.calls.length && elapsed < PAST_EVERY_DELAY) {
        act(() => vi.advanceTimersByTime(1_000))
        elapsed += 1_000
      }
      delays.push(elapsed)
      unmount()
      setVisibility('visible')
    }
    random.mockRestore()

    expect(new Set(delays).size).toBe(delays.length)
    // Never sooner than the settle window, whatever the draw.
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(30_000)
  })

  describe('returning from a long absence (timers suspended)', () => {
    it('applies a build that was staged before the app was backgrounded', () => {
      const applyUpdate = vi.fn()
      renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

      hide()
      suspendFor(LONG_ABSENCE)
      expect(applyUpdate).not.toHaveBeenCalled()

      show()
      expect(applyUpdate).toHaveBeenCalledTimes(1)
    })

    it('leaves a short absence to the settle timer', () => {
      const applyUpdate = vi.fn()
      renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

      hide()
      suspendFor(SHORT_ABSENCE)
      show()

      expect(applyUpdate).not.toHaveBeenCalled()
    })

    it('applies a build that finishes staging shortly after the return', () => {
      // On iOS the update check itself only runs on resume, so the worker is
      // still installing when the user lands.
      const applyUpdate = vi.fn()
      const { rerender } = renderHook(
        ({ staged }) => useAutoApplyUpdate({ staged, applyUpdate }),
        { initialProps: { staged: false } }
      )

      hide()
      suspendFor(LONG_ABSENCE)
      show()
      expect(applyUpdate).not.toHaveBeenCalled()

      suspendFor(20_000)
      rerender({ staged: true })
      expect(applyUpdate).toHaveBeenCalledTimes(1)
    })

    it('does not treat a build staged well after the return as part of it', () => {
      const applyUpdate = vi.fn()
      const { rerender } = renderHook(
        ({ staged }) => useAutoApplyUpdate({ staged, applyUpdate }),
        { initialProps: { staged: false } }
      )

      hide()
      suspendFor(LONG_ABSENCE)
      show()
      suspendFor(3 * 60_000)
      rerender({ staged: true })

      expect(applyUpdate).not.toHaveBeenCalled()
    })

    it('honours a bfcache restore that fires pageshow without visibilitychange', () => {
      const applyUpdate = vi.fn()
      renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))

      act(() => {
        window.dispatchEvent(new Event('pagehide'))
      })
      suspendFor(LONG_ABSENCE)
      act(() => {
        window.dispatchEvent(new Event('pageshow'))
      })

      expect(applyUpdate).toHaveBeenCalledTimes(1)
    })

    it('still refuses on a protected route or under a deferral', () => {
      const applyUpdate = vi.fn()
      setPath('/onboarding/step/2')
      renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate }))
      hide()
      suspendFor(LONG_ABSENCE)
      show()
      expect(applyUpdate).not.toHaveBeenCalled()

      setPath('/dashboard')
      claimUpdateDeferral('upload:avatar')
      hide()
      suspendFor(LONG_ABSENCE)
      show()
      expect(applyUpdate).not.toHaveBeenCalled()
    })
  })

  it('does nothing at all when disabled', () => {
    const applyUpdate = vi.fn()
    renderHook(() => useAutoApplyUpdate({ staged: true, applyUpdate, enabled: false }))

    hide()
    act(() => vi.advanceTimersByTime(PAST_EVERY_DELAY))

    expect(applyUpdate).not.toHaveBeenCalled()
  })
})
