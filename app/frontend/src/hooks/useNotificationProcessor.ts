import { useEffect, useRef } from 'react'
import { toast } from '@/lib/toast'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  addNotificationFromWebSocket,
  resetInAppNotifications,
} from '@/features/in-app-notifications/inAppNotificationsSlice'
import type { InAppNotificationWebSocketPayload } from '@/types/in-app-notification'

const NOTIFICATION_MESSAGE_TYPE = 'notification'

/**
 * Truncates text to a maximum length, appending "..." if truncated.
 * @param text - The text to truncate (or null)
 * @param maxLength - Maximum length before truncation
 * @returns Truncated text, original text, or undefined if input is null
 */
function truncateText(text: string | null, maxLength: number): string | undefined {
  if (text === null || text === undefined) {
    return undefined
  }
  if (text.length <= maxLength) {
    return text
  }
  return text.slice(0, maxLength) + '...'
}

/**
 * Hook to process WebSocket notification messages and display toasts.
 *
 * This hook should be called ONCE at the app level (e.g., in AuthProvider)
 * to avoid duplicate processing when multiple components subscribe to
 * notification state.
 *
 * Responsibilities:
 * - Listens for WebSocket messages of type "notification"
 * - Dispatches notifications to Redux store
 * - Displays toast notifications for new messages
 * - Resets notification state on logout
 */
export function useNotificationProcessor(): void {
  const dispatch = useAppDispatch()
  // Track processed message timestamps to avoid reprocessing
  const processedTimestampsRef = useRef<Set<string>>(new Set())

  // Get WebSocket messages
  const { messages } = useAppSelector((state) => state.websocket)

  // Get auth state for logout detection
  const { isAuthenticated } = useAppSelector((state) => state.auth)
  const wasAuthenticatedRef = useRef(isAuthenticated)

  // Process WebSocket messages for notifications
  useEffect(() => {
    if (messages.length === 0) {
      processedTimestampsRef.current.clear()
      return
    }

    // Process all unprocessed notification messages
    for (const message of messages) {
      // Skip already processed messages
      if (processedTimestampsRef.current.has(message.timestamp)) {
        continue
      }

      // Mark as processed
      processedTimestampsRef.current.add(message.timestamp)

      // Only dispatch for notification messages
      if (message.type !== NOTIFICATION_MESSAGE_TYPE) {
        continue
      }

      // Extract notification from payload
      const payload = message.payload as unknown as InAppNotificationWebSocketPayload
      if (payload?.notification) {
        dispatch(addNotificationFromWebSocket(payload.notification))

        // Display toast notification
        const notification = payload.notification
        if (notification.title) {
          const truncatedBody = truncateText(notification.body, 100)
          toast.info(notification.title, {
            id: notification.id,
            description: truncatedBody,
            category: 'notification',
          })
        }
      }
    }

    // Limit set size to prevent memory growth
    if (processedTimestampsRef.current.size > 200) {
      const timestamps = Array.from(processedTimestampsRef.current)
      processedTimestampsRef.current = new Set(timestamps.slice(-100))
    }
  }, [messages, dispatch])

  // Reset notifications state when user logs out
  useEffect(() => {
    // Detect logout (was authenticated, now not)
    if (wasAuthenticatedRef.current && !isAuthenticated) {
      dispatch(resetInAppNotifications())
    }
    wasAuthenticatedRef.current = isAuthenticated
  }, [isAuthenticated, dispatch])
}
