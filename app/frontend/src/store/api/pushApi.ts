/**
 * pushApi.ts — RTK Query endpoints for the Web Push notification channel.
 *
 * Endpoints:
 *  - GET    /notifications/push/vapid-key       — public VAPID key for the SW
 *  - POST   /notifications/push/subscriptions   — register a PushSubscription
 *  - DELETE /notifications/push/subscriptions    — unregister by endpoint
 */
import { api } from '@/store/api'

export interface VapidKeyResponse {
  public_key: string
}

/** Shape POSTed to the backend — a serialised browser `PushSubscription`. */
export interface PushSubscriptionPayload {
  endpoint: string
  keys: {
    p256dh: string
    auth: string
  }
  user_agent?: string
}

export interface PushSubscriptionResponse {
  id: string
  endpoint: string
}

export const pushApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /** GET /notifications/push/vapid-key */
    getVapidKey: builder.query<VapidKeyResponse, void>({
      query: () => '/notifications/push/vapid-key',
    }),

    /** POST /notifications/push/subscriptions — idempotent on the endpoint. */
    createPushSubscription: builder.mutation<
      PushSubscriptionResponse,
      PushSubscriptionPayload
    >({
      query: (body) => ({
        url: '/notifications/push/subscriptions',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'PushSubscription', id: 'LIST' }],
    }),

    /**
     * DELETE /notifications/push/subscriptions — unregister a device.
     *
     * The endpoint travels in the BODY, deliberately not in the query string.
     * A push endpoint is a per-device identifier, and a query string is written
     * to web-server and CDN access logs on every request and kept — so putting
     * it there leaks, permanently and silently, which browser belongs to which
     * user. (It is a correlatable identifier rather than a capability:
     * a VAPID-protected subscription cannot be sent to without the private key,
     * so this is a privacy concern, not an authentication one.)
     *
     * The countervailing risk — an intermediary dropping a DELETE body, which
     * has no defined semantics — is real but fails LOUDLY: unsubscribe visibly
     * stops working. A logging leak fails silently. If a proxy ever does strip
     * the body, add an `endpoint` query parameter to the server route and flip
     * this over.
     */
    deletePushSubscription: builder.mutation<void, { endpoint: string }>({
      query: (body) => ({
        url: '/notifications/push/subscriptions',
        method: 'DELETE',
        body,
      }),
      invalidatesTags: [{ type: 'PushSubscription', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetVapidKeyQuery,
  useLazyGetVapidKeyQuery,
  useCreatePushSubscriptionMutation,
  useDeletePushSubscriptionMutation,
} = pushApi
