/**
 * Service worker update detection, with iOS as the demanding case.
 *
 * On iOS the hourly poll never runs while the app is away — backgrounding
 * Safari or a home-screen PWA suspends timers — so a resume event is the only
 * thing that ever asks whether a newer build exists. iOS also restores a
 * backgrounded app from a page snapshot rather than navigating, and that
 * bfcache restore fires `pageshow` without reliably firing `visibilitychange`.
 *
 * These tests exercise the listener wiring directly rather than importing
 * `registerSW.ts`, which is a side-effecting module gated on a build-time env
 * flag and a `virtual:pwa-register` import that has no test double.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const RESUME_CHECK_THROTTLE_MS = 30 * 1000

/** The resume wiring from registerSW.ts, in the shape the module installs it. */
function installResumeCheck(checkForUpdate: () => void) {
  let lastCheckedAt = 0
  const checkOnResume = () => {
    if (document.visibilityState !== 'visible') return
    if (Date.now() - lastCheckedAt < RESUME_CHECK_THROTTLE_MS) return
    lastCheckedAt = Date.now()
    checkForUpdate()
  }
  document.addEventListener('visibilitychange', checkOnResume)
  window.addEventListener('pageshow', checkOnResume)
  return () => {
    document.removeEventListener('visibilitychange', checkOnResume)
    window.removeEventListener('pageshow', checkOnResume)
  }
}

function setVisibility(state: DocumentVisibilityState) {
  Object.defineProperty(document, 'visibilityState', { value: state, configurable: true })
}

let teardown: (() => void) | undefined

beforeEach(() => {
  vi.useFakeTimers()
  setVisibility('visible')
})

afterEach(() => {
  teardown?.()
  teardown = undefined
  vi.useRealTimers()
})

describe('update check on resume', () => {
  it('runs on a bfcache restore that fires only pageshow', () => {
    const checkForUpdate = vi.fn()
    teardown = installResumeCheck(checkForUpdate)

    // How iOS actually returns a backgrounded home-screen PWA to the user.
    window.dispatchEvent(new Event('pageshow'))

    expect(checkForUpdate).toHaveBeenCalledTimes(1)
  })

  it('runs on a plain visibilitychange, as every other platform sends', () => {
    const checkForUpdate = vi.fn()
    teardown = installResumeCheck(checkForUpdate)

    document.dispatchEvent(new Event('visibilitychange'))

    expect(checkForUpdate).toHaveBeenCalledTimes(1)
  })

  it('asks once when a resume fires both events together', () => {
    const checkForUpdate = vi.fn()
    teardown = installResumeCheck(checkForUpdate)

    document.dispatchEvent(new Event('visibilitychange'))
    window.dispatchEvent(new Event('pageshow'))

    expect(checkForUpdate).toHaveBeenCalledTimes(1)
  })

  it('asks again once the throttle window has passed', () => {
    const checkForUpdate = vi.fn()
    teardown = installResumeCheck(checkForUpdate)

    window.dispatchEvent(new Event('pageshow'))
    vi.advanceTimersByTime(RESUME_CHECK_THROTTLE_MS + 1)
    window.dispatchEvent(new Event('pageshow'))

    expect(checkForUpdate).toHaveBeenCalledTimes(2)
  })

  it('does not ask while the app is still hidden', () => {
    const checkForUpdate = vi.fn()
    teardown = installResumeCheck(checkForUpdate)

    setVisibility('hidden')
    document.dispatchEvent(new Event('visibilitychange'))
    window.dispatchEvent(new Event('pageshow'))

    expect(checkForUpdate).not.toHaveBeenCalled()
  })
})
