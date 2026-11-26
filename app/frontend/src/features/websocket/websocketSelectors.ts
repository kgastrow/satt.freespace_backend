import { createSelector } from '@reduxjs/toolkit'
import type { RootState } from '@/store'
import { NOTIFICATION_MESSAGE_TYPE } from './websocketSlice'

// Base selector
const selectWebSocketState = (state: RootState) => state.websocket

// Memoized websocket selectors
export const selectConnectionStatus = createSelector(
  selectWebSocketState,
  (ws) => ws.connectionStatus
)

export const selectMessages = createSelector(
  selectWebSocketState,
  (ws) => ws.messages
)

export const selectLastError = createSelector(
  selectWebSocketState,
  (ws) => ws.lastError
)

// Derived selectors
export const selectIsConnected = createSelector(
  selectConnectionStatus,
  (status) => status === 'connected'
)

export const selectIsConnecting = createSelector(
  selectConnectionStatus,
  (status) => status === 'connecting'
)

export const selectIsDisconnected = createSelector(
  selectConnectionStatus,
  (status) => status === 'disconnected'
)

export const selectHasError = createSelector(
  selectConnectionStatus,
  (status) => status === 'error'
)

// Message type selectors
export const selectNotificationMessages = createSelector(
  selectMessages,
  (messages) => messages.filter((m) => m.type === NOTIFICATION_MESSAGE_TYPE)
)

export const selectMessageCount = createSelector(
  selectMessages,
  (messages) => messages.length
)

// Parameterized selector for filtering messages by type
export const selectMessagesByType = createSelector(
  [selectMessages, (_state: RootState, type: string) => type],
  (messages, type) => messages.filter((m) => m.type === type)
)

// Get latest message of a specific type
export const selectLatestMessageByType = createSelector(
  [selectMessages, (_state: RootState, type: string) => type],
  (messages, type) => {
    const filtered = messages.filter((m) => m.type === type)
    return filtered.length > 0 ? filtered[filtered.length - 1] : null
  }
)
