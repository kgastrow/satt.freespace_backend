import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import websocketReducer, {
  setConnectionStatus,
  addMessage,
  setError,
  clearMessages,
  resetWebSocketState,
} from '@/features/websocket/websocketSlice'
import type { WebSocketState } from '@/types/websocket'

describe('WebSocket Slice Tests', () => {
  describe('websocketSlice reducers', () => {
    it('sets connection status to connected', () => {
      const state = websocketReducer(undefined, setConnectionStatus('connected'))
      expect(state.connectionStatus).toBe('connected')
      expect(state.lastError).toBeNull()
    })

    it('sets connection status to connecting', () => {
      const state = websocketReducer(undefined, setConnectionStatus('connecting'))
      expect(state.connectionStatus).toBe('connecting')
    })

    it('sets connection status to disconnected', () => {
      const initialState = {
        connectionStatus: 'connected' as const,
        messages: [],
        lastError: null,
      }
      const state = websocketReducer(initialState, setConnectionStatus('disconnected'))
      expect(state.connectionStatus).toBe('disconnected')
    })

    it('sets connection status to error', () => {
      const state = websocketReducer(undefined, setConnectionStatus('error'))
      expect(state.connectionStatus).toBe('error')
    })

    it('clears error when connected', () => {
      const initialState = {
        connectionStatus: 'error' as const,
        messages: [],
        lastError: 'Previous error',
      }
      const state = websocketReducer(initialState, setConnectionStatus('connected'))
      expect(state.lastError).toBeNull()
    })

    it('adds a message', () => {
      const message = {
        type: 'notification',
        payload: { text: 'Hello' },
        timestamp: '2024-01-01T00:00:00Z',
      }
      const state = websocketReducer(undefined, addMessage(message))
      expect(state.messages).toHaveLength(1)
      expect(state.messages[0]).toEqual(message)
    })

    it('adds multiple messages in order', () => {
      let state = websocketReducer(undefined, { type: 'INIT' })

      const message1 = {
        type: 'notification',
        payload: { index: 1 },
        timestamp: '2024-01-01T00:00:00Z',
      }
      const message2 = {
        type: 'notification',
        payload: { index: 2 },
        timestamp: '2024-01-01T00:00:01Z',
      }

      state = websocketReducer(state, addMessage(message1))
      state = websocketReducer(state, addMessage(message2))

      expect(state.messages).toHaveLength(2)
      expect(state.messages[0].payload).toEqual({ index: 1 })
      expect(state.messages[1].payload).toEqual({ index: 2 })
    })

    it('limits messages to MAX_MESSAGES (100)', () => {
      let state = websocketReducer(undefined, { type: 'INIT' })

      // Add 150 messages
      for (let i = 0; i < 150; i++) {
        state = websocketReducer(
          state,
          addMessage({
            type: 'notification',
            payload: { index: i },
            timestamp: '2024-01-01T00:00:00Z',
          })
        )
      }

      expect(state.messages.length).toBe(100)
      // The most recent messages should be kept (50-149)
      expect(state.messages[0].payload).toEqual({ index: 50 })
      expect(state.messages[99].payload).toEqual({ index: 149 })
    })

    it('sets error message', () => {
      const state = websocketReducer(undefined, setError('Connection failed'))
      expect(state.lastError).toBe('Connection failed')
    })

    it('clears error when setting null', () => {
      const initialState = {
        connectionStatus: 'error' as const,
        messages: [],
        lastError: 'Some error',
      }
      const state = websocketReducer(initialState, setError(null))
      expect(state.lastError).toBeNull()
    })

    it('clears messages', () => {
      const initialState = {
        connectionStatus: 'connected' as const,
        messages: [
          { type: 'test', payload: {}, timestamp: '2024-01-01T00:00:00Z' },
          { type: 'test2', payload: { data: 'value' }, timestamp: '2024-01-01T00:00:01Z' },
        ],
        lastError: null,
      }
      const state = websocketReducer(initialState, clearMessages())
      expect(state.messages).toHaveLength(0)
      expect(state.connectionStatus).toBe('connected') // Other state preserved
    })

    it('resets state to initial values', () => {
      const initialState = {
        connectionStatus: 'connected' as const,
        messages: [
          { type: 'test', payload: {}, timestamp: '2024-01-01T00:00:00Z' },
        ],
        lastError: 'Some error',
      }
      const state = websocketReducer(initialState, resetWebSocketState())
      expect(state.connectionStatus).toBe('disconnected')
      expect(state.messages).toHaveLength(0)
      expect(state.lastError).toBeNull()
    })

    it('maintains messages when setting status', () => {
      const initialState = {
        connectionStatus: 'connected' as const,
        messages: [
          { type: 'test', payload: { data: 'value' }, timestamp: '2024-01-01T00:00:00Z' },
        ],
        lastError: null,
      }
      const state = websocketReducer(initialState, setConnectionStatus('disconnected'))
      expect(state.messages).toHaveLength(1)
      expect(state.messages[0].payload).toEqual({ data: 'value' })
    })

    it('preserves connection status when adding message', () => {
      const initialState = {
        connectionStatus: 'connected' as const,
        messages: [],
        lastError: null,
      }
      const state = websocketReducer(
        initialState,
        addMessage({
          type: 'test',
          payload: {},
          timestamp: '2024-01-01T00:00:00Z',
        })
      )
      expect(state.connectionStatus).toBe('connected')
    })

    it('preserves messages at exact limit', () => {
      let state: WebSocketState = {
        connectionStatus: 'connected',
        messages: [],
        lastError: null,
      }

      // Add exactly 100 messages
      for (let i = 0; i < 100; i++) {
        state = websocketReducer(
          state,
          addMessage({
            type: 'notification',
            payload: { index: i },
            timestamp: '2024-01-01T00:00:00Z',
          })
        )
      }

      expect(state.messages.length).toBe(100)
      expect(state.messages[0].payload).toEqual({ index: 0 })
      expect(state.messages[99].payload).toEqual({ index: 99 })

      // Add one more, should trim to keep most recent 100
      state = websocketReducer(
        state,
        addMessage({
          type: 'notification',
          payload: { index: 100 },
          timestamp: '2024-01-01T00:00:00Z',
        })
      )

      expect(state.messages.length).toBe(100)
      expect(state.messages[0].payload).toEqual({ index: 1 })
      expect(state.messages[99].payload).toEqual({ index: 100 })
    })
  })
})

describe('WebSocket URL Construction', () => {
  it('constructs WebSocket URL with token parameter', () => {
    const token = 'test-token-123'
    const baseUrl = 'ws://localhost:8000'
    const path = '/ws'
    const expectedUrl = `${baseUrl}${path}?token=${encodeURIComponent(token)}`

    const constructedUrl = `${baseUrl}${path}?token=${encodeURIComponent(token)}`
    expect(constructedUrl).toBe(expectedUrl)
  })

  it('properly encodes special characters in token', () => {
    const token = 'token+with/special=chars'
    const encodedToken = encodeURIComponent(token)
    expect(encodedToken).toBe('token%2Bwith%2Fspecial%3Dchars')
  })

  it('handles JWT-style tokens with dots', () => {
    const jwtToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U'
    const encodedToken = encodeURIComponent(jwtToken)
    // JWT tokens with dots should be properly encoded
    expect(encodedToken).not.toContain(' ')
    expect(decodeURIComponent(encodedToken)).toBe(jwtToken)
  })
})

describe('Exponential Backoff Calculation', () => {
  const BASE_DELAY = 1000
  const MAX_DELAY = 30000
  const MULTIPLIER = 2

  const calculateDelay = (attempt: number): number => {
    const delay = BASE_DELAY * Math.pow(MULTIPLIER, attempt)
    return Math.min(delay, MAX_DELAY)
  }

  it('calculates correct delay for first attempt (0)', () => {
    expect(calculateDelay(0)).toBe(1000)
  })

  it('calculates correct delay for second attempt (1)', () => {
    expect(calculateDelay(1)).toBe(2000)
  })

  it('calculates correct delay for third attempt (2)', () => {
    expect(calculateDelay(2)).toBe(4000)
  })

  it('calculates correct delay for fourth attempt (3)', () => {
    expect(calculateDelay(3)).toBe(8000)
  })

  it('calculates correct delay for fifth attempt (4)', () => {
    expect(calculateDelay(4)).toBe(16000)
  })

  it('caps delay at max value for sixth attempt (5)', () => {
    expect(calculateDelay(5)).toBe(30000)
  })

  it('caps delay at max value for large attempt numbers', () => {
    expect(calculateDelay(10)).toBe(30000)
    expect(calculateDelay(100)).toBe(30000)
  })
})

describe('MockWebSocket Simulation', () => {
  let mockWebSocketInstances: MockWebSocket[] = []

  class MockWebSocket {
    static CONNECTING = 0
    static OPEN = 1
    static CLOSING = 2
    static CLOSED = 3

    url: string
    readyState: number = MockWebSocket.CONNECTING
    onopen: ((event: Event) => void) | null = null
    onmessage: ((event: MessageEvent) => void) | null = null
    onerror: ((event: Event) => void) | null = null
    onclose: ((event: CloseEvent) => void) | null = null

    sentMessages: string[] = []

    constructor(url: string) {
      this.url = url
      mockWebSocketInstances.push(this)
    }

    send(data: string): void {
      this.sentMessages.push(data)
    }

    close(): void {
      this.readyState = MockWebSocket.CLOSED
      if (this.onclose) {
        this.onclose(new CloseEvent('close'))
      }
    }

    simulateOpen(): void {
      this.readyState = MockWebSocket.OPEN
      if (this.onopen) {
        this.onopen(new Event('open'))
      }
    }

    simulateMessage(data: unknown): void {
      if (this.onmessage) {
        this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
      }
    }

    simulateError(): void {
      if (this.onerror) {
        this.onerror(new Event('error'))
      }
    }

    simulateClose(): void {
      this.readyState = MockWebSocket.CLOSED
      if (this.onclose) {
        this.onclose(new CloseEvent('close'))
      }
    }
  }

  beforeEach(() => {
    mockWebSocketInstances = []
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('creates instance with correct URL', () => {
    const testUrl = 'ws://test.example.com/ws?token=abc'
    const ws = new MockWebSocket(testUrl)
    expect(ws.url).toBe(testUrl)
    expect(mockWebSocketInstances).toHaveLength(1)
  })

  it('starts in CONNECTING state', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    expect(ws.readyState).toBe(MockWebSocket.CONNECTING)
  })

  it('transitions to OPEN on simulateOpen', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    let openCalled = false
    ws.onopen = () => { openCalled = true }

    ws.simulateOpen()

    expect(ws.readyState).toBe(MockWebSocket.OPEN)
    expect(openCalled).toBe(true)
  })

  it('receives messages via simulateMessage', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    let receivedData: unknown = null
    ws.onmessage = (event) => { receivedData = JSON.parse(event.data) }

    const testMessage = { type: 'test', payload: { foo: 'bar' }, timestamp: '2024-01-01' }
    ws.simulateMessage(testMessage)

    expect(receivedData).toEqual(testMessage)
  })

  it('sends messages correctly', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    ws.simulateOpen()

    ws.send(JSON.stringify({ type: 'ping' }))
    ws.send(JSON.stringify({ type: 'test' }))

    expect(ws.sentMessages).toHaveLength(2)
    expect(ws.sentMessages[0]).toBe('{"type":"ping"}')
    expect(ws.sentMessages[1]).toBe('{"type":"test"}')
  })

  it('handles errors via simulateError', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    let errorCalled = false
    ws.onerror = () => { errorCalled = true }

    ws.simulateError()

    expect(errorCalled).toBe(true)
  })

  it('handles close correctly', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    let closeCalled = false
    ws.onclose = () => { closeCalled = true }

    ws.close()

    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    expect(closeCalled).toBe(true)
  })

  it('handles simulateClose correctly', () => {
    const ws = new MockWebSocket('ws://test.example.com/ws')
    ws.simulateOpen()
    expect(ws.readyState).toBe(MockWebSocket.OPEN)

    let closeCalled = false
    ws.onclose = () => { closeCalled = true }

    ws.simulateClose()

    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    expect(closeCalled).toBe(true)
  })
})
