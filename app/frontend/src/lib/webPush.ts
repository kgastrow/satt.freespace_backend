/**
 * webPush.ts — browser Web Push helpers.
 *
 * Pure browser-API utilities: feature detection, VAPID key conversion, and
 * service-worker push (un)subscription. Network calls (VAPID key fetch +
 * subscription persistence) live in `pushApi.ts`; the orchestration lives in
 * the `useWebPush` hook.
 */
import type { PushSubscriptionPayload } from '@/store/api/pushApi'

/** Push permission/availability state surfaced to the UI. */
export type PushState =
  | 'unsupported' // browser lacks SW / PushManager / Notification
  | 'blocked' // user denied notification permission
  | 'default' // permission not yet requested
  | 'subscribed' // active push subscription present
  | 'unsubscribed' // supported + permitted, no active subscription

/** True when the browser supports the Web Push + service-worker APIs. */
export function isPushSupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    'serviceWorker' in navigator &&
    'PushManager' in window &&
    'Notification' in window
  )
}

/** True when the page is running as an installed app rather than a browser tab. */
export function isStandaloneDisplay(): boolean {
  if (typeof window === 'undefined') return false
  if (window.matchMedia?.('(display-mode: standalone)').matches) return true
  // iOS Safari's own flag, which predates (and still accompanies) display-mode.
  return (navigator as { standalone?: boolean }).standalone === true
}

/** True on iPhone/iPad, including iPadOS reporting itself as a Mac with touch. */
export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false
  const ua = navigator.userAgent || ''
  if (/iPad|iPhone|iPod/.test(ua)) return true
  return /Macintosh/.test(ua) && (navigator.maxTouchPoints ?? 0) > 1
}

/**
 * Why push cannot be switched on here, when it cannot.
 *
 * `null` means "nothing in the way". The iOS case is the one worth naming: on
 * iPhone, Web Push exists ONLY for a site the user has added to their Home
 * Screen — in a normal Safari tab `window.PushManager` is simply absent. That
 * surfaces as a permanently greyed toggle with a "this browser does not support
 * push notifications" line, which reads as a dead end when it is in fact a
 * two-tap fix the user can do themselves.
 */
export type PushBlockReason = 'ios-needs-install' | 'unsupported' | 'blocked' | null

export function pushBlockReason(state: PushState): PushBlockReason {
  if (state === 'blocked') return 'blocked'
  if (state !== 'unsupported') return null
  if (isIOS() && !isStandaloneDisplay()) return 'ios-needs-install'
  return 'unsupported'
}

/** Server-side column width for `user_agent`; anything longer is a 422. */
export const MAX_USER_AGENT_LENGTH = 255

/** Convert a base64url VAPID public key into the Uint8Array push expects. */
export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const rawData = window.atob(base64)
  const output = new Uint8Array(rawData.length)
  for (let i = 0; i < rawData.length; i += 1) {
    output[i] = rawData.charCodeAt(i)
  }
  return output
}

/** Serialise a browser `PushSubscription` into the backend payload shape. */
export function serializeSubscription(
  subscription: PushSubscription
): PushSubscriptionPayload {
  const json = subscription.toJSON()
  return {
    endpoint: subscription.endpoint,
    keys: {
      p256dh: json.keys?.p256dh ?? '',
      auth: json.keys?.auth ?? '',
    },
    // Bounded to the server's column width. `navigator.userAgent` has no upper
    // limit and some real browsers (and every UA-spoofing extension) run past
    // 255 characters, which the API rejected with a 422 — on every retry, from
    // the same device, forever. The tail is diagnostic only.
    user_agent:
      typeof navigator !== 'undefined'
        ? navigator.userAgent.slice(0, MAX_USER_AGENT_LENGTH)
        : undefined,
  }
}

/** Resolve the active service-worker registration (registered by VitePWA). */
async function getRegistration(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.ready
}

/** Return the current push subscription, if any. */
export async function getExistingSubscription(): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null
  const registration = await getRegistration()
  return registration.pushManager.getSubscription()
}

/** Byte-compare two BufferSources. */
function sameKey(a: ArrayBuffer | null | undefined, b: Uint8Array): boolean {
  if (!a) return false
  const left = new Uint8Array(a)
  if (left.length !== b.length) return false
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== b[i]) return false
  }
  return true
}

/**
 * True when `subscription` was created against a DIFFERENT VAPID public key
 * than the one the server is signing with now.
 *
 * A subscription is bound to the applicationServerKey it was created with. When
 * the server's keypair changes — a rotation, or a saved keypair that was being
 * shadowed by one in config.json — every push to that subscription comes back
 * 403. That is not 404/410, so nothing prunes it: the device just goes quiet,
 * indefinitely, with the switch still reading "on".
 */
export function isStaleSubscription(
  subscription: PushSubscription,
  vapidPublicKey: string
): boolean {
  const current = subscription.options?.applicationServerKey
  if (!current) return false // Browser does not expose it — assume usable.
  return !sameKey(current as ArrayBuffer, urlBase64ToUint8Array(vapidPublicKey))
}

/**
 * Request notification permission for this browser.
 *
 * Split out from {@link subscribeToPush} because WebKit only honours
 * `Notification.requestPermission()` under TRANSIENT ACTIVATION — it must be
 * reached from the click that the user just made, with no `await` on anything
 * else in between. Fetching the VAPID key first (as the caller used to) spends
 * the activation, and on an installed iOS PWA the call then rejects and the
 * tap does nothing at all. Callers must invoke this FIRST in the handler and
 * fetch the key afterwards.
 */
export async function requestPushPermission(): Promise<NotificationPermission> {
  if (!isPushSupported()) return 'denied'
  return Notification.requestPermission()
}

/**
 * Subscribe the browser to push with `vapidPublicKey`.
 *
 * Assumes permission has already been granted (see {@link requestPushPermission}).
 * Returns the subscription, or `null` if permission is not granted.
 */
export async function subscribeToPush(
  vapidPublicKey: string
): Promise<PushSubscription | null> {
  if (!isPushSupported()) return null
  if (Notification.permission !== 'granted') return null

  const registration = await getRegistration()
  const existing = await registration.pushManager.getSubscription()
  if (existing) {
    // Reusing a subscription signed against a retired key is how a device goes
    // permanently silent. Drop it and subscribe fresh against the current one.
    if (!isStaleSubscription(existing, vapidPublicKey)) return existing
    try {
      await existing.unsubscribe()
    } catch {
      // Already gone as far as the browser is concerned; subscribe anyway.
    }
  }

  // `applicationServerKey` expects a BufferSource; pass the underlying buffer
  // to satisfy the DOM lib typing across TS lib versions.
  const key = urlBase64ToUint8Array(vapidPublicKey)
  return registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: key.buffer as ArrayBuffer,
  })
}

/** Unsubscribe the browser from push. Returns the endpoint that was removed. */
export async function unsubscribeFromPush(): Promise<string | null> {
  const subscription = await getExistingSubscription()
  if (!subscription) return null
  const { endpoint } = subscription
  await subscription.unsubscribe()
  return endpoint
}
