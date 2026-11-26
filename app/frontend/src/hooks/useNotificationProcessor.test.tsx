/**
 * useNotificationProcessor Hook Unit Tests
 *
 * Tests the WebSocket notification processing hook, including:
 * - WebSocket message processing for notifications
 * - Toast display for new notifications
 * - Reset behavior on logout
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { Provider } from 'react-redux'
import { configureStore, type EnhancedStore } from '@reduxjs/toolkit'
import type { ReactNode } from 'react'
import { enableMapSet } from 'immer'

import { useNotificationProcessor } from './useNotificationProcessor'
import authReducer from '@/features/auth/authSlice'
import impersonationReducer from '@/features/impersonation/impersonationSlice'
import websocketReducer, { addMessage } from '@/features/websocket/websocketSlice'
import inAppNotificationsReducer from '@/features/in-app-notifications/inAppNotificationsSlice'
import announcementsReducer from '@/features/announcements/announcementsSlice'
import featureFlagsReducer from '@/features/featureFlags/featureFlagsSlice'
import maintenanceReducer from '@/features/maintenance/maintenanceSlice'
import preferencesReducer from '@/features/preferences/preferencesSlice'
import changelogReducer from '@/features/changelog/changelogSlice'
import { api } from '@/store/api'
import { authMiddleware } from '@/store/authMiddleware'
import type { RootState } from '@/store'
import type { InAppNotification } from '@/types/in-app-notification'
import type { WebSocketMessage } from '@/types/websocket'

// Enable Immer support for Map and Set objects in Redux state
enableMapSet()

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    info: vi.fn(),
  },
}))

// Mock the API
vi.mock('@/features/in-app-notifications/inAppNotificationsApi', () => ({
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

describe('useNotificationProcessor', () => {
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

  describe('WebSocket message processing', () => {
    const mockNotification: InAppNotification = {
      id: 'notif-1',
      title: 'Test Notification',
      body: 'This is a test notification',
      link: '/test',
      category_id: 'cat-1',
      read_time: null,
      created_time: '2024-01-01T00:00:00Z',
    }

    it('should process notification messages from WebSocket', async () => {
      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const notificationMessage: WebSocketMessage = {
        type: 'notification',
        payload: { notification: mockNotification },
        timestamp: '2024-01-01T00:00:00Z',
      }

      act(() => {
        store.dispatch(addMessage(notificationMessage))
      })

      await waitFor(() => {
        const state = store.getState() as RootState
        expect(state.inAppNotifications.notifications).toHaveLength(1)
        expect(state.inAppNotifications.notifications[0].id).toBe('notif-1')
        expect(state.inAppNotifications.unreadCount).toBe(1)
      })
    })

    it('should display toast for notification with title', async () => {
      const { toast } = await import('sonner')

      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const notificationMessage: WebSocketMessage = {
        type: 'notification',
        payload: { notification: mockNotification },
        timestamp: '2024-01-01T00:00:00Z',
      }

      act(() => {
        store.dispatch(addMessage(notificationMessage))
      })

      await waitFor(() => {
        expect(toast.info).toHaveBeenCalledWith(
          'Test Notification',
          expect.objectContaining({
            id: 'notif-1',
            description: 'This is a test notification',
          })
        )
      })
    })

    it('should truncate long body text in toast', async () => {
      const { toast } = await import('sonner')
      const longBody = 'A'.repeat(150)
      const notificationWithLongBody: InAppNotification = {
        ...mockNotification,
        body: longBody,
      }

      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const notificationMessage: WebSocketMessage = {
        type: 'notification',
        payload: { notification: notificationWithLongBody },
        timestamp: '2024-01-01T00:00:00Z',
      }

      act(() => {
        store.dispatch(addMessage(notificationMessage))
      })

      await waitFor(() => {
        expect(toast.info).toHaveBeenCalledWith(
          'Test Notification',
          expect.objectContaining({
            id: 'notif-1',
            description: 'A'.repeat(100) + '...',
          })
        )
      })
    })

    it('should ignore non-notification messages', async () => {
      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const otherMessage: WebSocketMessage = {
        type: 'ping',
        payload: {},
        timestamp: '2024-01-01T00:00:00Z',
      }

      act(() => {
        store.dispatch(addMessage(otherMessage))
      })

      // Give time for any potential processing
      await new Promise((resolve) => setTimeout(resolve, 50))

      const state = store.getState() as RootState
      expect(state.inAppNotifications.notifications).toHaveLength(0)
      expect(state.inAppNotifications.unreadCount).toBe(0)
    })

    it('should not process the same message twice', async () => {
      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const notificationMessage: WebSocketMessage = {
        type: 'notification',
        payload: { notification: mockNotification },
        timestamp: '2024-01-01T00:00:00Z',
      }

      // Dispatch the same message twice in quick succession
      act(() => {
        store.dispatch(addMessage(notificationMessage))
      })

      await waitFor(() => {
        const state = store.getState() as RootState
        expect(state.inAppNotifications.notifications).toHaveLength(1)
      })

      // Verify the message was processed only once
      const state = store.getState() as RootState
      expect(state.inAppNotifications.notifications).toHaveLength(1)
      expect(state.inAppNotifications.unreadCount).toBe(1)
    })

    it('should process multiple different notification messages', async () => {
      renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      const notification1: InAppNotification = {
        ...mockNotification,
        id: 'notif-1',
      }

      const notification2: InAppNotification = {
        ...mockNotification,
        id: 'notif-2',
        title: 'Second Notification',
      }

      const message1: WebSocketMessage = {
        type: 'notification',
        payload: { notification: notification1 },
        timestamp: '2024-01-01T00:00:00Z',
      }

      const message2: WebSocketMessage = {
        type: 'notification',
        payload: { notification: notification2 },
        timestamp: '2024-01-01T00:01:00Z',
      }

      act(() => {
        store.dispatch(addMessage(message1))
      })

      await waitFor(() => {
        const state = store.getState() as RootState
        expect(state.inAppNotifications.notifications).toHaveLength(1)
      })

      act(() => {
        store.dispatch(addMessage(message2))
      })

      await waitFor(() => {
        const state = store.getState() as RootState
        expect(state.inAppNotifications.notifications).toHaveLength(2)
        expect(state.inAppNotifications.unreadCount).toBe(2)
      })
    })
  })

  describe('logout handling', () => {
    it('should reset notifications state when user logs out', async () => {
      // Start with some notifications
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
          notifications: [
            {
              id: 'notif-1',
              title: 'Test',
              body: null,
              link: null,
              category_id: null,
              read_time: null,
              created_time: '2024-01-01T00:00:00Z',
            },
          ],
          unreadCount: 5,
          isLoading: false,
          hasMore: true,
          panelOpen: false,
          pendingWebSocketCount: 0,
        },
      })

      const { rerender } = renderHook(() => useNotificationProcessor(), {
        wrapper: createWrapper(store),
      })

      // Simulate logout by changing isAuthenticated to false
      act(() => {
        store.dispatch({
          type: 'auth/logout',
        })
      })

      // Rerender to trigger the effect
      rerender()

      await waitFor(() => {
        const state = store.getState() as RootState
        expect(state.inAppNotifications.notifications).toHaveLength(0)
        expect(state.inAppNotifications.unreadCount).toBe(0)
      })
    })
  })
})
