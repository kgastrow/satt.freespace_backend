/**
 * Service-worker update state: the one place that knows whether a newer build
 * is fully staged on this device, and the only place that reloads for it.
 *
 * The worker is built with `skipWaiting: false` (vite.config.ts), so a new
 * deploy installs, precaches the entire build, and then parks in `waiting`
 * without touching the running page. Workbox's install step is wrapped in
 * `event.waitUntil` and rejects on any non-OK precache response, so a worker
 * only ever reaches `waiting` when the whole build is on disk. That makes
 * `waiting` the authoritative "the new version is ready" signal — unlike a
 * /version.json delta, which only says a new build exists on the origin and
 * says nothing about whether this device can boot it.
 *
 * Nothing here reloads on its own. Applying an update is a user gesture, or the
 * quiet-swap policy in `useAutoApplyUpdate`. A worker that takes control
 * without us asking — another tab applied the update — raises the badge instead
 * of reloading, because reloading a page in use costs the user whatever they
 * were part-way through.
 */
type Listener = () => void

/**
 * How long the new worker gets to take control after we ask it to. `postMessage`
 * to a worker that has since gone away is silently dropped, which would
 * otherwise leave the user looking at a dead button.
 */
const SKIP_WAITING_TIMEOUT_MS = 3_000

const listeners = new Set<Listener>()
let updateReady = false
let readyRegistration: ServiceWorkerRegistration | null = null
let applying = false

function emit(): void {
  for (const listener of listeners) listener()
}

export function subscribeUpdateReady(listener: Listener): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export function getUpdateReady(): boolean {
  return updateReady
}

/** True once `applyUpdate()` has committed to reloading this page. */
export function isApplyingUpdate(): boolean {
  return applying
}

/** Record that a newer build is staged and ready to be promoted. */
export function markUpdateReady(registration?: ServiceWorkerRegistration | null): void {
  if (registration) readyRegistration = registration
  if (updateReady) return
  updateReady = true
  emit()
}

/**
 * Promote the staged build and reload onto it.
 *
 * With a waiting worker this is near-instant and entirely local: the new build
 * is already precached, so nothing is fetched.
 *
 * Without one, a plain reload is not enough while a worker controls the page:
 * its `navigateFallback` answers the navigation from the OLD precache, so the
 * page lands back on the build it was trying to leave and the banner comes
 * back ten minutes later, indefinitely. That is exactly the case this path is
 * for — the new worker could not install (a chunk 404'd mid-deploy, quota, a
 * bad package) — so the registration is dropped first. A registration that is
 * unregistering no longer matches navigations, the reload fetches index.html
 * from the origin (served `no-store`), and the fresh page registers again.
 * With the PWA disabled there is no registration and this is a plain reload.
 */
export async function applyUpdate(): Promise<void> {
  if (applying) return
  applying = true

  let registration = readyRegistration
  if (!registration?.waiting && 'serviceWorker' in navigator) {
    registration = (await navigator.serviceWorker.getRegistration().catch(() => null)) ?? null
  }

  const waiting = registration?.waiting
  if (!waiting) {
    if (registration) await registration.unregister().catch(() => false)
    window.location.reload()
    return
  }

  window.setTimeout(() => window.location.reload(), SKIP_WAITING_TIMEOUT_MS)
  waiting.postMessage({ type: 'SKIP_WAITING' })
}

/** Runtime cache name of the `/api/` NetworkFirst route in vite.config.ts. */
export const API_RUNTIME_CACHE = 'api-cache'

/**
 * Drop the service worker's cached API responses. Called on logout so nothing
 * of one session survives into the next on a shared device. Best effort: the
 * Cache API is absent in insecure contexts and some in-app browsers.
 */
export async function clearApiRuntimeCache(): Promise<void> {
  if (typeof caches === 'undefined') return
  try {
    await caches.delete(API_RUNTIME_CACHE)
  } catch {
    // Storage denied or the cache never existed. Nothing to clear.
  }
}

/** Test seam — module state outlives a render tree. */
export function resetUpdateState(): void {
  updateReady = false
  readyRegistration = null
  applying = false
  listeners.clear()
}
