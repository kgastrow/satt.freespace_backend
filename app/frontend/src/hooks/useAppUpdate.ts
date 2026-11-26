import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { useVersionCheck } from '@/hooks/useVersionCheck'
import { applyUpdate, getUpdateReady, subscribeUpdateReady } from '@/lib/swUpdate'
import type { VersionInfo } from '@/types/version'

const PWA_ENABLED = import.meta.env.VITE_ENABLE_PWA === 'true'

/**
 * How long the service worker gets to stage a build the origin says exists
 * before we stop waiting for it. Generous: staging competes with whatever the
 * user is actually doing, and a premature fallback throws away the whole benefit.
 */
const STAGING_GRACE_MS = 10 * 60 * 1000

const DISMISSED_KEY = 'app.update.dismissed'

/**
 * A build this old should prompt again even if the user dismissed an earlier
 * offer of it. Dismissal means "not right now", not "never" — and a user pinned
 * to a week-old build is running code nobody is fixing bugs against any more.
 */
const STALE_BUILD_MS = 7 * 24 * 60 * 60 * 1000

/** Resolved at import, so nothing reads the clock during a render. */
const BUILD_GOES_STALE_AT = Date.parse(import.meta.env.VITE_BUILD_TIME || '') + STALE_BUILD_MS

function readDismissed(): string | null {
  try {
    return localStorage.getItem(DISMISSED_KEY)
  } catch {
    return null
  }
}

interface UseAppUpdateReturn {
  /** A newer build can be applied, and the user has not waved it away. */
  updateReady: boolean
  /** A newer build is precached locally, so applying it costs no network. */
  staged: boolean
  /** The build the origin is serving, once a version check has answered. */
  serverVersion: VersionInfo | null
  /** Commit the update and reload onto it. */
  applyUpdate: () => void
  /** Stop offering this build until a newer one ships. */
  dismissUpdate: () => void
}

/**
 * Whether a newer build is ready for this device, and how to switch to it.
 *
 * Two signals, deliberately not equivalent:
 *
 * - The service worker's `waiting` registration means the new build is fully
 *   precached locally. This is the one that should drive a prompt: applying it
 *   fetches nothing.
 * - `/version.json` only means the origin is serving a different commit. It is
 *   the sole signal when the PWA is disabled, and otherwise a watchdog — if a
 *   precached asset 404s mid-deploy the new worker's install aborts, no
 *   `waiting` ever appears, and the SW path goes silent with no other recovery.
 *   After the grace period we fall back to a plain reload.
 */
export function useAppUpdate(): UseAppUpdateReturn {
  const staged = useSyncExternalStore(subscribeUpdateReady, getUpdateReady, () => false)
  const { hasUpdate, serverVersion } = useVersionCheck()
  const [stagingStalled, setStagingStalled] = useState(false)
  const [dismissedCommit, setDismissedCommit] = useState(readDismissed)
  const [buildIsStale, setBuildIsStale] = useState(false)

  useEffect(() => {
    if (!PWA_ENABLED || !hasUpdate || staged) return
    const timer = window.setTimeout(() => setStagingStalled(true), STAGING_GRACE_MS)
    // Deliberately not reset: the only thing that sets it is the timer firing,
    // and by then the fallback is wanted. If the worker does stage afterwards,
    // `staged` carries availability on its own.
    return () => window.clearTimeout(timer)
  }, [hasUpdate, staged])

  // A timer rather than a comparison in render: the clock is not a pure input,
  // and a tab left open for days is exactly the case this rule exists for.
  useEffect(() => {
    if (!Number.isFinite(BUILD_GOES_STALE_AT)) return
    const timer = window.setTimeout(
      () => setBuildIsStale(true),
      Math.max(0, BUILD_GOES_STALE_AT - Date.now())
    )
    return () => window.clearTimeout(timer)
  }, [])

  const available = PWA_ENABLED ? staged || stagingStalled : hasUpdate

  // A dismissal only covers the build it was made against. Until a version
  // check tells us which build the origin is on we cannot tell "the one they
  // dismissed" from "a newer one", so we honour the dismissal — re-prompting on
  // a guess is exactly the nagging this replaces.
  const dismissed =
    !buildIsStale &&
    dismissedCommit !== null &&
    (serverVersion === null || dismissedCommit === serverVersion.commit_hash)

  const dismissUpdate = useCallback(() => {
    const commit = serverVersion?.commit_hash
    if (!commit) return
    try {
      localStorage.setItem(DISMISSED_KEY, commit)
    } catch {
      // Storage denied. The caller's own page-load dismissal still applies.
    }
    setDismissedCommit(commit)
  }, [serverVersion])

  return {
    updateReady: available && !dismissed,
    staged,
    serverVersion,
    applyUpdate: useCallback(() => {
      void applyUpdate()
    }, []),
    dismissUpdate,
  }
}
