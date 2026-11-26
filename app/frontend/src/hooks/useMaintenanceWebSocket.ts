import { useEffect, useRef } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { updateMaintenanceStatus } from '@/features/maintenance/maintenanceSlice'

const MAINTENANCE_MESSAGE_TYPE = 'maintenance'

interface MaintenancePayload {
  enabled: boolean
  message: string | null
}

/**
 * Type guard to check if payload is a valid MaintenancePayload
 */
function isMaintenancePayload(payload: unknown): payload is MaintenancePayload {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }
  const obj = payload as Record<string, unknown>
  return (
    typeof obj.enabled === 'boolean' &&
    (obj.message === null || typeof obj.message === 'string')
  )
}

/**
 * Hook to process WebSocket maintenance mode messages.
 *
 * This hook should be called ONCE at the app level (e.g., in AuthProvider)
 * to avoid duplicate processing.
 *
 * When a maintenance message is received via WebSocket, it immediately
 * updates the maintenance Redux state, which causes MaintenanceProvider
 * to show the maintenance page.
 */
export function useMaintenanceWebSocket(): void {
  const dispatch = useAppDispatch()
  // Track processed message timestamps to avoid reprocessing
  const processedTimestampsRef = useRef<Set<string>>(new Set())

  // Get WebSocket messages
  const { messages } = useAppSelector((state) => state.websocket)

  // Process WebSocket messages for maintenance
  useEffect(() => {
    if (messages.length === 0) {
      processedTimestampsRef.current.clear()
      return
    }

    // Process all unprocessed maintenance messages
    for (const message of messages) {
      // Skip already processed messages
      if (processedTimestampsRef.current.has(message.timestamp)) {
        continue
      }

      // Mark as processed
      processedTimestampsRef.current.add(message.timestamp)

      // Only process maintenance messages
      if (message.type !== MAINTENANCE_MESSAGE_TYPE) {
        continue
      }

      // Extract maintenance payload from message.payload
      if (isMaintenancePayload(message.payload)) {
        dispatch(
          updateMaintenanceStatus({
            enabled: message.payload.enabled,
            scheduledEnd: null,
            message: message.payload.message,
          })
        )
      }
    }

    // Limit set size to prevent memory growth
    if (processedTimestampsRef.current.size > 200) {
      const timestamps = Array.from(processedTimestampsRef.current)
      processedTimestampsRef.current = new Set(timestamps.slice(-100))
    }
  }, [messages, dispatch])
}
