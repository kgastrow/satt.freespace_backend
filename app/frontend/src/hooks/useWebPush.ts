/**
 * useWebPush — orchestrates Web Push opt-in for the notification-preferences UI.
 *
 * Wires the browser helpers in `lib/webPush.ts` to the `pushApi` endpoints:
 * fetch the VAPID key, request permission, subscribe, and persist the
 * subscription (or unsubscribe + delete). Gracefully reports unsupported /
 * blocked states so the UI can show `push.unsupported` / `push.blocked`.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  useLazyGetVapidKeyQuery,
  useCreatePushSubscriptionMutation,
  useDeletePushSubscriptionMutation,
} from '@/store/api/pushApi'
import {
  isPushSupported,
  getExistingSubscription,
  requestPushPermission,
  subscribeToPush,
  unsubscribeFromPush,
  serializeSubscription,
  type PushState,
} from '@/lib/webPush'

/**
 * Why the last enable/disable did not work. Distinguishing these is the whole
 * point: they were all swallowed by a bare `catch`, so the user saw the same
 * silent snap-back whether they had blocked notifications, whether push was
 * unconfigured server-side, or whether their connection had dropped.
 */
export type PushError =
  | 'denied' // user chose Block, or the OS refuses
  | 'dismissed' // prompt closed without an answer
  | 'not-configured' // server has no VAPID keypair (503)
  | 'rejected' // server refused the subscription (422 / 409)
  | 'network' // request never completed
  | 'unsupported'

export interface UseWebPushReturn {
  /** Coarse state for rendering (unsupported / blocked / subscribed / …). */
  state: PushState
  /** Convenience booleans derived from `state`. */
  isSupported: boolean
  isSubscribed: boolean
  /** A (un)subscribe request is in flight. */
  isBusy: boolean
  /** Why the last attempt failed, or `null`. Cleared when a new one starts. */
  error: PushError | null
  /**
   * Subscribe the current device to Web Push (requests permission).
   *
   * Resolves `true` ONLY when a subscription actually exists afterwards.
   * Callers must not treat "the promise settled" as consent: a user who hits
   * Block, dismisses the prompt, or is offline gets `false`, and flipping the
   * `web_push_enabled` preference on for them would leave the channel switched
   * on with nothing able to deliver through it.
   */
  enable: () => Promise<boolean>
  /** Unsubscribe the current device. Resolves `true` when it completed. */
  disable: () => Promise<boolean>
}

function permissionToState(hasSubscription: boolean): PushState {
  if (!isPushSupported()) return 'unsupported'
  if (Notification.permission === 'denied') return 'blocked'
  if (hasSubscription) return 'subscribed'
  if (Notification.permission === 'granted') return 'unsubscribed'
  return 'default'
}

/** Map an RTK Query / fetch rejection onto a reportable cause. */
function classifyError(err: unknown): PushError {
  const status = (err as { status?: number | string } | undefined)?.status
  if (status === 503) return 'not-configured'
  if (status === 422 || status === 409 || status === 400) return 'rejected'
  if (status === 'FETCH_ERROR' || status === 'TIMEOUT_ERROR') return 'network'
  if (typeof status === 'number' && status >= 400) return 'rejected'
  return 'network'
}

export function useWebPush(): UseWebPushReturn {
  const [state, setState] = useState<PushState>(() =>
    isPushSupported() ? 'default' : 'unsupported'
  )
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<PushError | null>(null)

  const [fetchVapidKey] = useLazyGetVapidKeyQuery()
  const [createSubscription] = useCreatePushSubscriptionMutation()
  const [deleteSubscription] = useDeletePushSubscriptionMutation()

  // Resolve the initial state from the existing subscription, if any.
  useEffect(() => {
    let cancelled = false
    if (!isPushSupported()) {
      setState('unsupported')
      return
    }
    getExistingSubscription()
      .then((subscription) => {
        if (!cancelled) setState(permissionToState(Boolean(subscription)))
      })
      .catch(() => {
        if (!cancelled) setState(permissionToState(false))
      })
    return () => {
      cancelled = true
    }
  }, [])

  const enable = useCallback(async (): Promise<boolean> => {
    if (!isPushSupported()) {
      setState('unsupported')
      setError('unsupported')
      return false
    }
    setError(null)
    setIsBusy(true)
    try {
      // Permission FIRST, before any await that could spend the user gesture.
      // WebKit only grants `requestPermission()` under transient activation, so
      // fetching the VAPID key ahead of it made the call reject outright on an
      // installed iOS PWA — the tap appeared to do nothing.
      const permission = await requestPushPermission()
      if (permission !== 'granted') {
        setState(permission === 'denied' ? 'blocked' : 'default')
        setError(permission === 'denied' ? 'denied' : 'dismissed')
        return false
      }

      const { public_key } = await fetchVapidKey().unwrap()
      const subscription = await subscribeToPush(public_key)
      if (!subscription) {
        setState(permissionToState(false))
        setError('denied')
        return false
      }
      await createSubscription(serializeSubscription(subscription)).unwrap()
      setState('subscribed')
      return true
    } catch (err) {
      setState(permissionToState(false))
      setError(classifyError(err))
      return false
    } finally {
      setIsBusy(false)
    }
  }, [fetchVapidKey, createSubscription])

  const disable = useCallback(async (): Promise<boolean> => {
    if (!isPushSupported()) return false
    setError(null)
    setIsBusy(true)
    try {
      const endpoint = await unsubscribeFromPush()
      if (endpoint) {
        await deleteSubscription({ endpoint }).unwrap()
      }
      setState('unsubscribed')
      return true
    } catch (err) {
      setState(permissionToState(false))
      setError(classifyError(err))
      return false
    } finally {
      setIsBusy(false)
    }
  }, [deleteSubscription])

  return {
    state,
    isSupported: state !== 'unsupported',
    isSubscribed: state === 'subscribed',
    isBusy,
    error,
    enable,
    disable,
  }
}
