import { useEffect, useRef, useSyncExternalStore } from 'react'
import { hasUpdateDeferrals, subscribeUpdateDeferrals } from '@/lib/deferUpdate'

/**
 * Routes where a reload is an outage, not an inconvenience.
 *
 * The test is not "is this page important" but "does a reload here destroy
 * something the user cannot get back". Each entry below holds in-memory state
 * that exists nowhere else until it is submitted.
 *
 * Forks must edit this list. It is the single most product-specific value in
 * the whole update model: a route that takes payment, records a live session,
 * or drives a long multi-step form belongs here, and none of those exist in the
 * template.
 *
 * - `/onboarding` — a multi-step form whose draft is in memory until the last
 *   step posts it.
 * - `/setup-2fa` — the secret is shown once. A reload mid-enrolment restarts it
 *   and, worse, can leave a half-configured authenticator app behind.
 * - `/register`, `/reset-password` — one-shot token flows; a reload spends the
 *   token without completing the action.
 * - `/settings/security/export` — kicks off a long-running job whose progress
 *   is streamed to this page.
 */
const PROTECTED_PATHS = [
  /^\/onboarding(\/|$)/,
  /^\/setup-2fa(\/|$)/,
  /^\/register(\/|$)/,
  /^\/reset-password(\/|$)/,
  /\/security\/export(\/|$)/,
]

/** How long the app must stay backgrounded before a swap counts as unobserved. */
const HIDDEN_SETTLE_MS = 30 * 1000

/**
 * Away this long, and whatever the user was doing is over. iOS suspends timers
 * while Safari or a home-screen PWA is backgrounded, so the settle timer below
 * never fires there; a staged build is applied on the way back in instead. The
 * reload costs a fresh boot at the one moment the user is reorienting anyway.
 */
const RESUME_APPLY_AFTER_MS = 5 * 60 * 1000

/**
 * A build that finishes staging this soon after a long-absence resume is
 * treated as if it had been staged during the absence. On iOS the update check
 * itself only runs on resume (registerSW.ts), so the worker is still installing
 * when the user lands; without this window they would sit on the old build,
 * against a possibly changed API, until they tapped the banner.
 */
const RESUME_STAGED_WINDOW_MS = 60 * 1000

/**
 * Spread the resulting reloads out. A deploy lands on every device at once and
 * `visibilitychange` fires for all of them together; a cold boot is ~10 requests
 * against a per-IP rate limiter, so an office behind one NAT can rate-limit
 * itself simply by being updated simultaneously.
 */
const JITTER_MAX_MS = 45 * 1000

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PATHS.some((pattern) => pattern.test(pathname))
}

interface UseAutoApplyUpdateOptions {
  /** A build is staged locally and applying it costs no network. */
  staged: boolean
  applyUpdate: () => void
  enabled?: boolean
}

/**
 * Apply a staged update while nobody is looking — or on the way back from a
 * long absence, which is the only path platforms that suspend timers offer.
 *
 * Every condition must hold: the build is staged (not merely announced by the
 * origin), nothing has claimed a deferral, the route is not one where a reload
 * costs real work, and the app has either been backgrounded long enough that
 * the user is demonstrably elsewhere or has just returned from an absence long
 * enough that nothing was in progress. Anything short of that leaves it to the
 * badge.
 *
 * Deliberately NOT triggered on navigation. Anything the app shell hoists above
 * the router — a persistent player, an upload queue, a websocket — survives a
 * route change and would not survive a reload, so navigation is exactly the
 * wrong moment to swap the build.
 */
export function useAutoApplyUpdate({
  staged,
  applyUpdate,
  enabled = true,
}: UseAutoApplyUpdateOptions): void {
  const deferred = useSyncExternalStore(
    subscribeUpdateDeferrals,
    hasUpdateDeferrals,
    () => false
  )
  // The latest callback without re-arming the timer on every render.
  const applyRef = useRef(applyUpdate)
  useEffect(() => {
    applyRef.current = applyUpdate
  }, [applyUpdate])

  // Absence tracking outlives the staged/deferred effect below: the app is
  // usually hidden long before anything is staged, and the resume that matters
  // is often the one that triggers the update check in the first place.
  const hiddenAtRef = useRef<number | null>(null)
  const longResumeAtRef = useRef<number | null>(null)
  // Set by the effect below while a staged build may be applied; the resume
  // listener calls it so the two effects share one set of guards.
  const onLongResumeRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (typeof document === 'undefined') return

    const noteHidden = () => {
      if (hiddenAtRef.current === null) hiddenAtRef.current = Date.now()
    }
    const noteVisible = () => {
      const hiddenAt = hiddenAtRef.current
      hiddenAtRef.current = null
      if (hiddenAt === null) return
      if (Date.now() - hiddenAt < RESUME_APPLY_AFTER_MS) return
      longResumeAtRef.current = Date.now()
      onLongResumeRef.current?.()
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') noteHidden()
      else noteVisible()
    }

    // iOS restores a backgrounded app from a page snapshot and fires
    // `pagehide`/`pageshow` without reliably firing `visibilitychange`.
    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('pagehide', noteHidden)
    window.addEventListener('pageshow', noteVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('pagehide', noteHidden)
      window.removeEventListener('pageshow', noteVisible)
    }
  }, [])

  useEffect(() => {
    if (!enabled || !staged || deferred) return
    if (typeof document === 'undefined') return

    let timer: number | undefined

    const cancel = () => {
      if (timer !== undefined) window.clearTimeout(timer)
      timer = undefined
    }

    const applyIfAllowed = () => {
      if (hasUpdateDeferrals()) return
      if (isProtectedPath(window.location.pathname)) return
      applyRef.current()
    }

    const arm = () => {
      cancel()
      if (document.visibilityState !== 'hidden') return
      // Re-checked when the timer fires, not just now: the user can navigate or
      // start work from a backgrounded tab (a notification, a media key).
      timer = window.setTimeout(() => {
        if (document.visibilityState !== 'hidden') return
        applyIfAllowed()
      }, HIDDEN_SETTLE_MS + Math.random() * JITTER_MAX_MS)
    }

    // Staged after a long-absence resume rather than before it: apply now, while
    // the user is still arriving, instead of leaving it to the badge.
    const longResumeAt = longResumeAtRef.current
    if (longResumeAt !== null && Date.now() - longResumeAt <= RESUME_STAGED_WINDOW_MS) {
      longResumeAtRef.current = null
      applyIfAllowed()
      return
    }

    arm()
    onLongResumeRef.current = applyIfAllowed
    document.addEventListener('visibilitychange', arm)

    return () => {
      cancel()
      onLongResumeRef.current = null
      document.removeEventListener('visibilitychange', arm)
    }
  }, [enabled, staged, deferred])
}
