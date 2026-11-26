// Service worker registration + update detection.
//
// The SW is built with `skipWaiting: false` and `registerType: 'prompt'` (see
// vite.config.ts), so a new deploy installs and precaches the entire build in
// the background, then parks in `waiting` without disturbing the running page.
// It is promoted only when the user asks, via `applyUpdate()`, or by the
// quiet-swap policy in `useAutoApplyUpdate`.
//
// This file previously reloaded unconditionally on `controllerchange`, with an
// update check on every return to foreground. That force-reloads a user mid
// checkout, mid form, mid anything, with no prompt — leaving the update banner
// as a second, gentler path most users never reach.
import { isApplyingUpdate, markUpdateReady } from '@/lib/swUpdate'

const UPDATE_POLL_INTERVAL_MS = 60 * 60 * 1000

// Backgrounding and foregrounding fires visibilitychange and pageshow in quick
// succession; there is nothing to learn from asking the server twice a second
// apart.
const RESUME_CHECK_THROTTLE_MS = 30 * 1000

if (import.meta.env.VITE_ENABLE_PWA === 'true') {
  import('virtual:pwa-register').then(({ registerSW }) => {
    if ('serviceWorker' in navigator) {
      // Whether a worker already controlled this page at startup. If not, this
      // is a first-ever visit and the initial `clientsClaim` handover is not an
      // update — it must neither reload nor raise the badge.
      const hadController = Boolean(navigator.serviceWorker.controller)
      let reloading = false

      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (!hadController) return
        if (!isApplyingUpdate()) {
          // Someone else promoted the worker — another tab, or the browser
          // activating it after every client closed. This page is now running
          // old code against a new worker, but it is still usable and may be
          // mid-task, so surface the badge rather than reloading underneath it.
          // A chunk that has since been pruned is handled by retryImport.
          markUpdateReady()
          return
        }
        if (reloading) return
        reloading = true
        window.location.reload()
      })
    }

    registerSW({
      immediate: true,
      onOfflineReady() {
        console.log('App is ready for offline use')
      },
      onNeedRefresh() {
        markUpdateReady()
      },
      onRegisteredSW(_swUrl, registration) {
        if (!registration) return

        const noteWaiting = () => {
          if (registration.waiting) markUpdateReady(registration)
        }

        // A worker staged during an earlier session is already parked.
        noteWaiting()

        // Own the detection rather than relying on `onNeedRefresh` alone.
        // workbox-window stops listening for `updatefound` once an update is
        // detected more than 60s after registration, or on the second one it
        // sees (Workbox.ts) — and every check below is past that window. The
        // first deploy a long-lived tab saw would prompt; no later one would.
        registration.addEventListener('updatefound', () => {
          const installing = registration.installing
          if (!installing) return
          installing.addEventListener('statechange', () => {
            // `controller` distinguishes an update from a first install.
            if (installing.state === 'installed' && navigator.serviceWorker.controller) {
              markUpdateReady(registration)
            }
          })
        })

        const checkForUpdate = () =>
          registration
            .update()
            .then(noteWaiting)
            .catch(() => {})

        // Long-lived tabs: poll hourly so a deploy is eventually picked up.
        setInterval(checkForUpdate, UPDATE_POLL_INTERVAL_MS)

        // And whenever the app comes back to the foreground. On iOS this is the
        // ONLY one of the two that ever runs: backgrounding Safari or a
        // home-screen PWA suspends timers, so the hourly poll above never fires
        // while away and the app can sit on a weeks-old build indefinitely.
        //
        // Both events are needed. iOS restores a backgrounded app from a page
        // snapshot rather than navigating, and that bfcache restore fires
        // `pageshow` without reliably firing `visibilitychange` — the same
        // lesson useVersionCheck already learned the hard way. Since this is now
        // the primary update path, listening to only one of them would leave
        // iOS with no path at all.
        let lastCheckedAt = 0
        const checkOnResume = () => {
          if (document.visibilityState !== 'visible') return
          if (Date.now() - lastCheckedAt < RESUME_CHECK_THROTTLE_MS) return
          lastCheckedAt = Date.now()
          checkForUpdate()
        }
        document.addEventListener('visibilitychange', checkOnResume)
        window.addEventListener('pageshow', checkOnResume)
      },
    })
  })
}
