import { useEffect, useRef } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  addAnnouncementFromWebSocket,
  updateAnnouncementFromWebSocket,
  removeAnnouncementFromWebSocket,
} from '@/features/announcements/announcementsSlice'
import type { Announcement } from '@/types/announcement'
import type { WebSocketMessage } from '@/types/websocket'

/**
 * WebSocket message types for announcements
 */
const ANNOUNCEMENT_MESSAGE_TYPES = {
  CREATED: 'announcement_created',
  UPDATED: 'announcement_updated',
  DELETED: 'announcement_deleted',
} as const

/**
 * Type guard to check if payload is a valid Announcement object
 */
function isAnnouncementPayload(payload: unknown): payload is Announcement {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }
  const obj = payload as Record<string, unknown>
  return (
    typeof obj.id === 'string' &&
    typeof obj.title === 'string' &&
    typeof obj.body === 'string' &&
    typeof obj.priority === 'string' &&
    typeof obj.is_dismissible === 'boolean'
  )
}

/**
 * Type guard to check if payload is a valid deletion payload
 */
function isDeletionPayload(payload: unknown): payload is { id: string } {
  if (typeof payload !== 'object' || payload === null) {
    return false
  }
  const obj = payload as Record<string, unknown>
  return typeof obj.id === 'string'
}

/**
 * Check if a message is an announcement-related message
 */
function isAnnouncementMessage(message: WebSocketMessage): boolean {
  return (
    message.type === ANNOUNCEMENT_MESSAGE_TYPES.CREATED ||
    message.type === ANNOUNCEMENT_MESSAGE_TYPES.UPDATED ||
    message.type === ANNOUNCEMENT_MESSAGE_TYPES.DELETED
  )
}

/**
 * Hook that listens for announcement-related WebSocket messages
 * and updates the Redux store accordingly.
 *
 * This hook should be used in a component that is mounted when the user
 * is authenticated (e.g., a layout component).
 */
export function useAnnouncementWebSocket(): void {
  const dispatch = useAppDispatch()
  const { messages, connectionStatus } = useAppSelector(
    (state) => state.websocket
  )

  // Track the timestamp of the last processed message to avoid reprocessing
  // Using timestamp instead of index because the messages array can be truncated
  const lastProcessedTimestampRef = useRef<string | null>(null)

  // Track processed message timestamps to handle duplicates within same timestamp
  const processedTimestampsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    // Only process messages when connected
    if (connectionStatus !== 'connected') {
      return
    }

    // Filter to only announcement messages that haven't been processed
    const lastTimestamp = lastProcessedTimestampRef.current
    const processedSet = processedTimestampsRef.current

    for (const message of messages) {
      // Skip non-announcement messages
      if (!isAnnouncementMessage(message)) {
        continue
      }

      // Skip if we've already processed this exact message
      // Use timestamp + type as a simple deduplication key
      const messageKey = `${message.timestamp}-${message.type}`
      if (processedSet.has(messageKey)) {
        continue
      }

      // Skip messages older than our last processed timestamp
      if (lastTimestamp && message.timestamp <= lastTimestamp) {
        continue
      }

      // Process the message with type guards for safety
      switch (message.type) {
        case ANNOUNCEMENT_MESSAGE_TYPES.CREATED: {
          if (isAnnouncementPayload(message.payload)) {
            dispatch(addAnnouncementFromWebSocket(message.payload))
          }
          break
        }

        case ANNOUNCEMENT_MESSAGE_TYPES.UPDATED: {
          if (isAnnouncementPayload(message.payload)) {
            dispatch(updateAnnouncementFromWebSocket(message.payload))
          }
          break
        }

        case ANNOUNCEMENT_MESSAGE_TYPES.DELETED: {
          if (isDeletionPayload(message.payload)) {
            dispatch(removeAnnouncementFromWebSocket(message.payload.id))
          }
          break
        }
      }

      // Mark as processed
      processedSet.add(messageKey)
      lastProcessedTimestampRef.current = message.timestamp

      // Keep the processed set from growing too large
      if (processedSet.size > 200) {
        const entries = Array.from(processedSet)
        processedSet.clear()
        // Keep the most recent 100 entries
        entries.slice(-100).forEach((key) => processedSet.add(key))
      }
    }
  }, [messages, connectionStatus, dispatch])

  // Reset tracking when disconnected or messages cleared
  useEffect(() => {
    if (connectionStatus === 'disconnected' || messages.length === 0) {
      lastProcessedTimestampRef.current = null
      processedTimestampsRef.current.clear()
    }
  }, [connectionStatus, messages.length])
}
