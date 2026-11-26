/**
 * In-app notification types - TypeScript types matching backend serializers
 */

/**
 * Single in-app notification response
 */
export interface InAppNotification {
  id: string
  title: string
  body: string | null
  link: string | null
  category_id: string | null
  read_time: string | null
  created_time: string | null
}

/**
 * Paginated list response for in-app notifications
 */
export interface InAppNotificationListResponse {
  items: InAppNotification[]
  total: number
  limit: number
  offset: number
}

/**
 * Unread count response
 */
export interface UnreadCountResponse {
  unread_count: number
}

/**
 * Request to dismiss notifications
 */
export interface DismissNotificationsRequest {
  notification_ids: string[]
}

/**
 * Response after marking notifications as read
 */
export interface MarkReadResponse {
  message: string
  count: number
}

/**
 * Response after dismissing notifications
 */
export interface DismissResponse {
  message: string
  count: number
}

/**
 * Query parameters for listing in-app notifications
 */
export interface InAppNotificationListParams {
  unread_only?: boolean
  limit?: number
  offset?: number
}

/**
 * WebSocket notification payload format
 */
export interface InAppNotificationWebSocketPayload {
  notification: InAppNotification
}
