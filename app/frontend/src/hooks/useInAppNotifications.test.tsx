/**
 * useInAppNotifications Hook Unit Tests
 *
 * Tests the notification state access hook, including:
 * - Initial unread count fetching
 * - Connection status reporting
 * - Loading state
 *
 * Note: WebSocket message processing and logout handling are tested
 * in useNotificationProcessor.test.tsx
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore, type EnhancedStore } from '@reduxjs/toolkit'
import type { ReactNode } from 'react'
import { enableMapSet } from 'immer'

import { useInAppNotifications } from './useInAppNotifications'

import authReducer from '@/features/auth/authSlice'
import impersonationReducer from '@/features/impersonation/impersonationSlice'
import websocketReducer from '@/features/websocket/websocketSlice'
import inAppNotificationsReducer from '@/features/in-app-notifications/inAppNotificationsSlice'
import announcementsReducer from '@/features/announcements/announcementsSlice'
import featureFlagsReducer from '@/features/featureFlags/featureFlagsSlice'
import maintenanceReducer from '@/features/maintenance/maintenanceSlice'
import preferencesReducer from '@/features/preferences/preferencesSlice'
import changelogReducer from '@/features/changelog/changelogSlice'
import { api } from '@/store/api'
import { authMiddleware } from '@/store/authMiddleware'
import type { RootState } from '@/store'

// Enable Immer support for Map and Set objects in Redux state
enableMapSet()

// Mock the API hooks
vi.mock('@/features/in-app-notifications/inAppNotificationsApi', () => ({
  useGetUnreadCountQuery: vi.fn(() => ({
    isFetching: false,
    data: { unread_count: 5 },
  })),
  inAppNotificationsApi: {
    endpoints: {
      getInAppNotifications: {
        matchFulfilled: () => false,
        matchPending: () => false,
        matchRejected: () => false,
      },
      getUnreadCount: {
        matchFulfilled: () => false,
      },
      markAsRead: {
        matchFulfilled: () => false,
      },
      markAllAsRead: {
        matchFulfilled: () => false,
      },
      dismissNotifications: {
        matchFulfilled: () => false,
      },
    },
  },
}))

function createTestStore(preloadedState?: Partial<RootState>): EnhancedStore {
  return configureStore({
    reducer: {
      [api.reducerPath]: api.reducer,
      auth: authReducer,
      impersonation: impersonationReducer,
      websocket: websocketReducer,
      inAppNotifications: inAppNotificationsReducer,
      announcements: announcementsReducer,
      featureFlags: featureFlagsReducer,
      maintenance: maintenanceReducer,
      preferences: preferencesReducer,
      changelog: changelogReducer,
    },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware({
        serializableCheck: {
          // Ignore Set objects in announcements state - Immer's enableMapSet() handles these
          ignoredPaths: ['announcements.locallyDismissedIds'],
          ignoredActions: [],
        },
      }).concat(api.middleware, authMiddleware),
    preloadedState: preloadedState as RootState,
  })
}

function createWrapper(store: EnhancedStore) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>
  }
}

describe('useInAppNotifications', () => {
  let store: EnhancedStore

  beforeEach(() => {
    store = createTestStore({
      auth: {
        user: null,
        token: 'test-token',
        isAuthenticated: true,
        isLoading: false,
        sso: {
          isLoading: false,
          error: null,
          selectedProvider: null,
        },
      twoFactor: { required: false, token: null },
      twoFactorSetupRequired: false,
      enforcementActive: false,
      },
      websocket: {
        connectionStatus: 'connected',
        messages: [],
        lastError: null,
      },
      inAppNotifications: {
        notifications: [],
        unreadCount: 0,
        isLoading: false,
        hasMore: true,
        panelOpen: false,
        pendingWebSocketCount: 0,
      },
    })
    vi.clearAllMocks()
  })

  describe('initial state', () => {
    it('should return connection status', () => {
      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.connectionStatus).toBe('connected')
      expect(result.current.isConnected).toBe(true)
    })

    it('should return unread count from state', () => {
      store = createTestStore({
        auth: {
          user: null,
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
            sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        websocket: {
          connectionStatus: 'connected',
          messages: [],
          lastError: null,
        },
        inAppNotifications: {
          notifications: [],
          unreadCount: 5,
          isLoading: false,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.unreadCount).toBe(5)
    })

    it('should return loading state', () => {
      store = createTestStore({
        auth: {
          user: null,
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
            sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        websocket: {
          connectionStatus: 'connected',
          messages: [],
          lastError: null,
        },
        inAppNotifications: {
          notifications: [],
          unreadCount: 0,
          isLoading: true,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.isLoading).toBe(true)
    })
  })

  describe('connection status', () => {
    it('should return disconnected when not connected', () => {
      store = createTestStore({
        auth: {
          user: null,
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
            sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        websocket: {
          connectionStatus: 'disconnected',
          messages: [],
          lastError: null,
        },
        inAppNotifications: {
          notifications: [],
          unreadCount: 0,
          isLoading: false,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.connectionStatus).toBe('disconnected')
      expect(result.current.isConnected).toBe(false)
    })

    it('should return connecting when connecting', () => {
      store = createTestStore({
        auth: {
          user: null,
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
            sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        websocket: {
          connectionStatus: 'connecting',
          messages: [],
          lastError: null,
        },
        inAppNotifications: {
          notifications: [],
          unreadCount: 0,
          isLoading: false,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.connectionStatus).toBe('connecting')
      expect(result.current.isConnected).toBe(false)
    })

    it('should return error when there is an error', () => {
      store = createTestStore({
        auth: {
          user: null,
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
            sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        websocket: {
          connectionStatus: 'error',
          messages: [],
          lastError: 'Connection failed',
        },
        inAppNotifications: {
          notifications: [],
          unreadCount: 0,
          isLoading: false,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { result } = renderHook(() => useInAppNotifications(), {
        wrapper: createWrapper(store),
      })

      expect(result.current.connectionStatus).toBe('error')
      expect(result.current.isConnected).toBe(false)
    })
  })
})
