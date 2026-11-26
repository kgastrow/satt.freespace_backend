import { useAppSelector } from '@/store/hooks'
import { useGetUnreadCountQuery } from '@/features/in-app-notifications/inAppNotificationsApi'

export interface UseInAppNotificationsReturn {
  /** Current unread notification count */
  unreadCount: number
  /** Whether the initial unread count is loading */
  isLoading: boolean
  /** Current WebSocket connection status */
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'error'
  /** Whether WebSocket is connected and ready to receive notifications */
  isConnected: boolean
}

/**
 * Hook to access in-app notification state for UI components.
 *
 * This hook provides read-only access to notification state. WebSocket message
 * processing and toast display are handled separately by useNotificationProcessor
 * (called once in AuthProvider) to avoid duplicate processing.
 *
 * @example
 * ```tsx
 * function NotificationBadge() {
 *   const { unreadCount, isConnected } = useInAppNotifications()
 *   return (
 *     <div>
 *       {unreadCount > 0 && <span>{unreadCount}</span>}
 *       {!isConnected && <span>Offline</span>}
 *     </div>
 *   )
 * }
 * ```
 */
export function useInAppNotifications(): UseInAppNotificationsReturn {
  // Get unread count from slice
  const { unreadCount, isLoading } = useAppSelector(
    (state) => state.inAppNotifications
  )

  // Get WebSocket connection status
  const { connectionStatus } = useAppSelector((state) => state.websocket)

  // Fetch initial unread count on mount
  const { isFetching: isUnreadCountFetching } = useGetUnreadCountQuery()

  const isConnected = connectionStatus === 'connected'

  return {
    unreadCount,
    isLoading: isLoading || isUnreadCountFetching,
    connectionStatus,
    isConnected,
  }
}
