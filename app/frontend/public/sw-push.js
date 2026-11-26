/**
 * sw-push.js — Web Push handlers for the generated service worker.
 *
 * VitePWA builds the worker with workbox `generateSW`, which emits precache +
 * runtime-caching logic but no push handlers. This file is pulled into that
 * generated worker via `workbox.importScripts` (see vite.config.ts), so it runs
 * in the same service-worker scope as `self.registration`.
 *
 * The backend `web_push_provider` signs a JSON payload of the shape
 * `{ title, body, url }` (see services/notifications/web_push_provider.py), so
 * that is exactly what we parse here. The two are a contract: change one and
 * the other stops rendering anything.
 *
 * KNOWN GAP: `pushsubscriptionchange` is not handled. When a push service
 * retires this device's endpoint the browser announces it only to this scope,
 * and reporting the replacement needs a server route to report it to. Without
 * that, a rotated device goes quiet until the next authenticated app load
 * re-registers it through `useWebPush`.
 */
/* global self */

self.addEventListener('push', (event) => {
  let payload = {}
  try {
    payload = event.data ? event.data.json() : {}
  } catch {
    // Non-JSON payload — fall back to the raw text as the body.
    payload = { body: event.data ? event.data.text() : '' }
  }

  const title = payload.title || 'Notification'
  const url = payload.url || '/'
  const options = {
    body: payload.body || '',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    data: { url },
    // Collapse repeats of the same notification rather than stacking them.
    tag: payload.tag || 'app-notification',
    renotify: true,
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const targetUrl = (event.notification.data && event.notification.data.url) || '/'

  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then(async (windowClients) => {
        const focusable = windowClients.filter((c) => 'focus' in c)
        if (focusable.length === 0) {
          return self.clients.openWindow ? self.clients.openWindow(targetUrl) : undefined
        }

        // Prefer a window already showing the target. Focusing the first window
        // regardless navigates a user with the app open on another screen away
        // from whatever they were doing.
        const absolute = new URL(targetUrl, self.location.origin).href
        const alreadyThere = focusable.find((c) => c.url === absolute)
        const client = alreadyThere || focusable[0]

        // These are promises. Discarding them let `waitUntil` settle — and the
        // worker be killed — before the navigation had actually happened, so
        // the tap opened the app on the wrong page or on nothing at all.
        await client.focus()
        if (!alreadyThere && 'navigate' in client) {
          await client.navigate(absolute)
        }
        return undefined
      })
  )
})
