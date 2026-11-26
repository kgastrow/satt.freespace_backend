import { useCallback, useEffect, useRef } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  setConnectionStatus,
  addMessage,
  setError,
  clearMessages,
} from '@/features/websocket/websocketSlice'
import { logout } from '@/features/auth/authSlice'
import type { WebSocketMessage, WebSocketConnectionStatus } from '@/types/websocket'

// WebSocket close codes
const WS_CLOSE_CODE_ACCESS_REVOKED = 4003

const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const WS_PATH = '/ws'

const RECONNECT_BASE_DELAY_MS = 1000
const RECONNECT_MAX_DELAY_MS = 30000
const RECONNECT_MULTIPLIER = 2

interface UseWebSocketReturn {
  connectionStatus: WebSocketConnectionStatus
  messages: WebSocketMessage[]
  lastError: string | null
  sendPing: () => void
  disconnect: () => void
  connect: () => void
  clearAllMessages: () => void
}

export function useWebSocket(): UseWebSocketReturn {
  const dispatch = useAppDispatch()
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isManualDisconnectRef = useRef(false)

  const { connectionStatus, messages, lastError } = useAppSelector(
    (state) => state.websocket
  )
  const { token, isAuthenticated } = useAppSelector((state) => state.auth)

  const connectRef = useRef<() => void>(() => {})

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  const getReconnectDelay = useCallback(() => {
    const delay =
      RECONNECT_BASE_DELAY_MS *
      Math.pow(RECONNECT_MULTIPLIER, reconnectAttemptRef.current)
    return Math.min(delay, RECONNECT_MAX_DELAY_MS)
  }, [])

  const connect = useCallback(() => {
    if (!token || !isAuthenticated) {
      return
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    if (wsRef.current?.readyState === WebSocket.CONNECTING) {
      return
    }

    isManualDisconnectRef.current = false
    dispatch(setConnectionStatus('connecting'))

    // Security: Don't pass token in URL (exposes in browser history, logs)
    // Instead, send token in first message after connection
    const wsUrl = `${WS_BASE_URL}${WS_PATH}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      // Send auth message with token (not in URL to prevent log exposure)
      ws.send(JSON.stringify({ type: 'auth', token }))
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WebSocketMessage

        // Handle auth success - now fully connected
        if (message.type === 'auth_success') {
          dispatch(setConnectionStatus('connected'))
          dispatch(setError(null))
          reconnectAttemptRef.current = 0
          return
        }

        dispatch(addMessage(message))
      } catch {
        // Ignore invalid JSON messages
      }
    }

    ws.onerror = () => {
      dispatch(setConnectionStatus('error'))
      dispatch(setError('WebSocket connection error'))
    }

    ws.onclose = (event) => {
      dispatch(setConnectionStatus('disconnected'))
      wsRef.current = null

      // Handle access revoked close code (user suspended or org inactive)
      if (event.code === WS_CLOSE_CODE_ACCESS_REVOKED) {
        dispatch(setError('websocket.access_revoked'))
        dispatch(logout())
        // Don't attempt to reconnect - access has been revoked
        return
      }

      // Only reconnect if not manually disconnected and still authenticated
      if (!isManualDisconnectRef.current && isAuthenticated && token) {
        const delay = getReconnectDelay()
        reconnectAttemptRef.current += 1

        reconnectTimeoutRef.current = setTimeout(() => {
          connectRef.current()
        }, delay)
      }
    }

    wsRef.current = ws
  }, [token, isAuthenticated, dispatch, getReconnectDelay])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  const disconnect = useCallback(() => {
    isManualDisconnectRef.current = true
    clearReconnectTimeout()

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    dispatch(setConnectionStatus('disconnected'))
  }, [clearReconnectTimeout, dispatch])

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }, [])

  const clearAllMessages = useCallback(() => {
    dispatch(clearMessages())
  }, [dispatch])

  // Auto-connect when authenticated
  useEffect(() => {
    if (isAuthenticated && token) {
      connect()
    }

    return () => {
      clearReconnectTimeout()
    }
  }, [isAuthenticated, token, connect, clearReconnectTimeout])

  // Handle token refresh - re-authenticate without reconnecting
  // Use a ref to track the previous token to detect actual changes
  const prevTokenRef = useRef<string | null>(null)
  useEffect(() => {
    // Only re-auth if token actually changed (not on initial mount)
    if (
      token &&
      isAuthenticated &&
      prevTokenRef.current !== null &&
      prevTokenRef.current !== token &&
      wsRef.current?.readyState === WebSocket.OPEN
    ) {
      // Token refreshed while connected - just send new auth message
      // No need to disconnect/reconnect which causes UI flicker
      wsRef.current.send(JSON.stringify({ type: 'auth', token }))
    }
    prevTokenRef.current = token
  }, [token, isAuthenticated])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearReconnectTimeout()
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [clearReconnectTimeout])

  // Disconnect when logged out
  useEffect(() => {
    if (!isAuthenticated) {
      disconnect()
    }
  }, [isAuthenticated, disconnect])

  return {
    connectionStatus,
    messages,
    lastError,
    sendPing,
    disconnect,
    connect,
    clearAllMessages,
  }
}
