import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { api } from '@/store/api'
import { toast } from '@/lib/toast'
import type { WebSocketMessage } from '@/types/websocket'

/**
 * WebSocket message type for data export status updates
 */
const DATA_EXPORT_STATUS_TYPE = 'data_export_status'

/**
 * Payload structure for data export status messages
 */
interface DataExportStatusPayload {
  export_id: string
  status: 'completed' | 'failed'
  file_size_bytes?: number
  expires_at?: string
}

/**
 * Type guard to check if payload is a valid DataExportStatusPayload
 */
function isDataExportPayload(
  payload: unknown
): payload is DataExportStatusPayload {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }
  const obj = payload as Record<string, unknown>
  return (
    typeof obj.export_id === 'string' &&
    (obj.status === 'completed' || obj.status === 'failed')
  )
}

/**
 * Check if a message is a data export status message
 */
function isDataExportMessage(message: WebSocketMessage): boolean {
  return message.type === DATA_EXPORT_STATUS_TYPE
}

/**
 * Hook that listens for data export status WebSocket messages
 * and updates the UI accordingly.
 *
 * When an export completes or fails, this hook:
 * 1. Invalidates the RTK Query cache to refresh the export list
 * 2. Shows a toast notification to the user
 *
 * This hook should be used in the AuthProvider component.
 */
export function useDataExportWebSocket(): void {
  const dispatch = useAppDispatch()
  const { t } = useTranslation(['settings'])
  const { messages, connectionStatus } = useAppSelector(
    (state) => state.websocket
  )

  // Track processed message timestamps to handle duplicates
  const processedTimestampsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    // Only process messages when connected
    if (connectionStatus !== 'connected') {
      return
    }

    const processedSet = processedTimestampsRef.current

    for (const message of messages) {
      // Skip non-export messages
      if (!isDataExportMessage(message)) {
        continue
      }

      // Skip if we've already processed this exact message
      const messageKey = `${message.timestamp}-${message.type}`
      if (processedSet.has(messageKey)) {
        continue
      }

      // Validate payload
      if (!isDataExportPayload(message.payload)) {
        continue
      }

      // Mark as processed
      processedSet.add(messageKey)

      // Invalidate RTK Query cache to refresh export list
      dispatch(api.util.invalidateTags(['User']))

      // Show toast notification
      if (message.payload.status === 'completed') {
        toast.success(t('settings:dataExport.notifications.exportReady'))
      } else {
        toast.error(t('settings:dataExport.notifications.exportFailed'))
      }

      // Keep the processed set from growing too large
      if (processedSet.size > 200) {
        const entries = Array.from(processedSet)
        processedSet.clear()
        // Keep the most recent 100 entries
        entries.slice(-100).forEach((key) => processedSet.add(key))
      }
    }
  }, [messages, connectionStatus, dispatch, t])

  // Reset tracking when disconnected or messages cleared
  useEffect(() => {
    if (connectionStatus === 'disconnected' || messages.length === 0) {
      processedTimestampsRef.current.clear()
    }
  }, [connectionStatus, messages.length])
}
