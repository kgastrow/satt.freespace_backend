/**
 * Dynamic-import recovery for a build that was replaced under the user.
 *
 * A long-lived tab keeps running the index.html it booted with. After a deploy
 * that file references chunk hashes the origin may no longer have, and
 * `/assets/` is configured to return a real 404 rather than fall through to the
 * SPA shell (`FallbackResource disabled`, see
 * app/backend/apache_site_config/ayzer_backend.conf). So the first lazy route
 * the user touches after a deploy can simply fail.
 *
 * Retry once for a transient blip, then reload so the browser fetches the
 * current index.html and its chunk names.
 *
 * The reload guard is a timestamp rather than a flag. A flag set immediately
 * before `location.reload()` cannot distinguish "we just reloaded to recover
 * from this" from "a reload happened at some point", and the previous version
 * cleared it on the `load` event — which fires on the very page it was meant to
 * protect. A genuinely missing chunk reloaded forever.
 */
const RELOAD_GUARD_KEY = 'app:chunk-reload-at'
const RELOAD_GUARD_WINDOW_MS = 30_000

const CHUNK_ERROR_PATTERN =
  /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|ChunkLoadError/i

/**
 * A failed dynamic import surfaces as a TypeError in Chrome/Safari and as a
 * message match elsewhere; neither is a stable contract, so we accept both.
 */
export function isChunkLoadError(error: unknown): boolean {
  if (error instanceof TypeError) return true
  const message =
    error instanceof Error ? error.message : typeof error === 'string' ? error : String(error)
  return CHUNK_ERROR_PATTERN.test(message)
}

function reloadedRecently(): boolean {
  try {
    const at = Number(sessionStorage.getItem(RELOAD_GUARD_KEY))
    return Number.isFinite(at) && at > 0 && Date.now() - at < RELOAD_GUARD_WINDOW_MS
  } catch {
    // Storage denied (private mode, blocked cookies). Without a guard we cannot
    // bound a reload loop, so decline to reload and let the error reach the
    // boundary — a visible error beats an unbreakable refresh cycle.
    return true
  }
}

function markReloaded(): void {
  try {
    sessionStorage.setItem(RELOAD_GUARD_KEY, String(Date.now()))
  } catch {
    // Best effort; reloadedRecently() already fails closed when storage is gone.
  }
}

export function retryImport<T>(importFn: () => Promise<T>): Promise<T> {
  return importFn().catch((error: unknown) => {
    if (!isChunkLoadError(error)) throw error
    return importFn().catch((retryError: unknown) => {
      if (reloadedRecently()) throw retryError
      markReloaded()
      window.location.reload()
      // Never settles: the page is going away, and resolving would let a
      // Suspense boundary render against a module that was never loaded.
      return new Promise<T>(() => {})
    })
  })
}
