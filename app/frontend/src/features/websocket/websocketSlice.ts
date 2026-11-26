import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type {
  WebSocketState,
  WebSocketMessage,
  WebSocketConnectionStatus,
} from '@/types/websocket'

const MAX_MESSAGES = 100

/** Message type for in-app notifications */
export const NOTIFICATION_MESSAGE_TYPE = 'notification'

const initialState: WebSocketState = {
  connectionStatus: 'disconnected',
  messages: [],
  lastError: null,
}

const websocketSlice = createSlice({
  name: 'websocket',
  initialState,
  reducers: {
    setConnectionStatus: (
      state,
      action: PayloadAction<WebSocketConnectionStatus>
    ) => {
      state.connectionStatus = action.payload
      if (action.payload === 'connected') {
        state.lastError = null
      }
    },

    addMessage: (state, action: PayloadAction<WebSocketMessage>) => {
      state.messages.push(action.payload)
      // Keep only the most recent messages - use splice for in-place mutation
      // to avoid GC pressure from creating new arrays on every cleanup
      if (state.messages.length > MAX_MESSAGES) {
        state.messages.splice(0, state.messages.length - MAX_MESSAGES)
      }
    },

    setError: (state, action: PayloadAction<string | null>) => {
      state.lastError = action.payload
    },

    clearMessages: (state) => {
      state.messages = []
    },

    resetWebSocketState: () => initialState,
  },
})

export const {
  setConnectionStatus,
  addMessage,
  setError,
  clearMessages,
  resetWebSocketState,
} = websocketSlice.actions

export default websocketSlice.reducer
