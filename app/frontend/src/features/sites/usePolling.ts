import { useEffect, useState } from 'react'

/** Auto-refresh period of the live pages (sites list, live view). */
export const LIVE_POLL_MS = 15_000

/**
 * Polling interval for RTK Query's `pollingInterval`: the given period while
 * the browser tab is visible, 0 (paused) while it is hidden. On becoming
 * visible again the interval resumes immediately.
 */
export function usePollingInterval(ms: number = LIVE_POLL_MS): number {
  const [visible, setVisible] = useState(
    () => typeof document === 'undefined' || document.visibilityState !== 'hidden'
  )
  useEffect(() => {
    const onChange = () => setVisible(document.visibilityState !== 'hidden')
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])
  return visible ? ms : 0
}
