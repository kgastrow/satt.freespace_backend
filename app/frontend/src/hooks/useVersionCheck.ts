import { useEffect, useState, useCallback, useRef } from 'react'
import type { VersionInfo } from '@/types/version'

const VERSION_CHECK_INTERVAL = 5 * 60 * 1000 // 5 minutes in milliseconds
// Minimum gap between foreground-triggered checks. Backgrounding and
// foregrounding an app fires visibilitychange/pageshow in quick succession, and
// there is nothing to learn from re-asking the server seconds apart.
const RESUME_CHECK_THROTTLE = 30 * 1000
const LAST_KNOWN_VERSION_KEY = 'lastKnownVersion'

interface UseVersionCheckOptions {
  interval?: number
  enabled?: boolean
}

interface UseVersionCheckReturn {
  hasUpdate: boolean
  serverVersion: VersionInfo | null
  currentVersion: VersionInfo
  isChecking: boolean
}

/**
 * Reports whether the origin is serving a different build than the one running.
 *
 * Advisory only. A version delta says a new build EXISTS; it says nothing about
 * whether this device can boot it, so it must not by itself drive a prompt when
 * the service worker is in play — see `useAppUpdate`, which treats this as a
 * fallback and a watchdog. Applying an update belongs to `lib/swUpdate`.
 */
export function useVersionCheck(
  options: UseVersionCheckOptions = {}
): UseVersionCheckReturn {
  const { interval = VERSION_CHECK_INTERVAL, enabled = true } = options

  const [serverVersion, setServerVersion] = useState<VersionInfo | null>(null)
  const [hasUpdate, setHasUpdate] = useState(false)
  const [isChecking, setIsChecking] = useState(false)
  const abortControllerRef = useRef<AbortController | null>(null)
  const lastCheckedAtRef = useRef(0)

  // Current version embedded at build time
  const currentVersion: VersionInfo = {
    version: import.meta.env.VITE_BUILD_VERSION || '0.0.0',
    commit_hash: import.meta.env.VITE_BUILD_COMMIT || 'development',
    build_time: import.meta.env.VITE_BUILD_TIME || new Date().toISOString(),
  }

  /**
   * Check if there's a version mismatch
   */
  const checkVersion = useCallback(async () => {
    if (!enabled) return

    // Cancel any in-flight request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()
    lastCheckedAtRef.current = Date.now()
    setIsChecking(true)

    try {
      // Fetch version.json with cache-busting query param. `no-store` on top of
      // that because Cloudflare enforces a minimum browser cache TTL on
      // anything it caches, which has overridden the origin's `no-cache`
      // headers before.
      const response = await fetch(`/version.json?_cb=${Date.now()}`, {
        signal: abortControllerRef.current.signal,
        cache: 'no-store',
      })

      if (!response.ok) {
        throw new Error(`Failed to fetch version: ${response.status}`)
      }

      const result: VersionInfo = await response.json()
      setServerVersion(result)

      // Get last known version from localStorage
      const lastKnownVersionStr = localStorage.getItem(LAST_KNOWN_VERSION_KEY)
      const lastKnownVersion: VersionInfo | null = lastKnownVersionStr
        ? JSON.parse(lastKnownVersionStr)
        : null

      // Update last known version
      localStorage.setItem(LAST_KNOWN_VERSION_KEY, JSON.stringify(result))

      // Check for version mismatch
      // Compare commit hash as the primary version indicator
      if (result.commit_hash !== currentVersion.commit_hash) {
        // Only set hasUpdate if we've seen a previous version
        // This prevents showing update banner on first load
        if (lastKnownVersion) {
          setHasUpdate(true)
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        // Request was cancelled, ignore
        return
      }
      // Version check failed - silently ignore, will retry on next interval
    } finally {
      setIsChecking(false)
    }
  }, [enabled, currentVersion.commit_hash])

  // Initial check on mount and when enabled changes
  useEffect(() => {
    checkVersion()
  }, [checkVersion, enabled])

  // Set up polling interval
  useEffect(() => {
    if (!enabled) return

    const intervalId = setInterval(checkVersion, interval)

    return () => clearInterval(intervalId)
  }, [enabled, interval, checkVersion])

  // Re-check whenever the app returns to the foreground.
  //
  // The polling interval above is not enough on iOS. Backgrounding Safari or a
  // home-screen PWA suspends timers, and reopening it restores the page from a
  // snapshot instead of navigating — so no interval fires, no navigation
  // happens, and nothing ever asks the server whether this build is still
  // current. A phone can sit on a weeks-old build indefinitely, which is
  // exactly what it did. `pageshow` covers the back/forward-cache restore,
  // which does not reliably come with a visibilitychange.
  useEffect(() => {
    if (!enabled) return

    const checkOnResume = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastCheckedAtRef.current < RESUME_CHECK_THROTTLE) return
      checkVersion()
    }

    document.addEventListener('visibilitychange', checkOnResume)
    window.addEventListener('pageshow', checkOnResume)

    return () => {
      document.removeEventListener('visibilitychange', checkOnResume)
      window.removeEventListener('pageshow', checkOnResume)
    }
  }, [enabled, checkVersion])

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return {
    hasUpdate,
    serverVersion,
    currentVersion,
    isChecking,
  }
}
