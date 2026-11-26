/**
 * WebSocket types - TypeScript types matching backend WebSocket message format
 */

/**
 * Connection status for WebSocket
 */
export type WebSocketConnectionStatus =
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'error'

/**
 * WebSocket message format matching backend WebSocketMessage model
 */
export interface WebSocketMessage {
  type: string
  payload: Record<string, unknown>
  timestamp: string // ISO8601 format
}

/**
 * WebSocket state for Redux store
 */
export interface WebSocketState {
  connectionStatus: WebSocketConnectionStatus
  messages: WebSocketMessage[]
  lastError: string | null
}
