/**
 * In-App Notifications Slice Unit Tests
 *
 * Tests the Redux slice reducers and state management for in-app notifications
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { configureStore } from '@reduxjs/toolkit'
import inAppNotificationsReducer, {
  setPanelOpen,
  togglePanel,
  addNotificationFromWebSocket,
  markNotificationReadLocally,
  markAllNotificationsReadLocally,
  removeNotificationsLocally,
  setLoading,
  resetInAppNotifications,
  type InAppNotificationsState,
} from './inAppNotificationsSlice'
import type { InAppNotification } from '@/types/in-app-notification'

describe('inAppNotificationsSlice', () => {
  let store: ReturnType<typeof createTestStore>

  function createTestStore(preloadedState?: Partial<InAppNotificationsState>) {
    return configureStore({
      reducer: {
        inAppNotifications: inAppNotificationsReducer,
      },
      preloadedState: preloadedState
        ? { inAppNotifications: { ...initialState, ...preloadedState } }
        : undefined,
    })
  }

  const initialState: InAppNotificationsState = {
    notifications: [],
    unreadCount: 0,
    isLoading: false,
    hasMore: true,
    panelOpen: false,
    pendingWebSocketCount: 0,
  }

  const mockNotification: InAppNotification = {
    id: 'notif-1',
    title: 'Test Notification',
    body: 'This is a test notification',
    link: '/test',
    category_id: 'cat-1',
    read_time: null,
    created_time: '2024-01-01T00:00:00Z',
  }

  const mockReadNotification: InAppNotification = {
    id: 'notif-2',
    title: 'Read Notification',
    body: 'This notification has been read',
    link: '/test2',
    category_id: 'cat-1',
    read_time: '2024-01-01T01:00:00Z',
    created_time: '2024-01-01T00:30:00Z',
  }

  beforeEach(() => {
    store = createTestStore()
  })

  describe('initial state', () => {
    it('should have correct initial state', () => {
      const state = store.getState().inAppNotifications
      expect(state.notifications).toEqual([])
      expect(state.unreadCount).toBe(0)
      expect(state.isLoading).toBe(false)
      expect(state.hasMore).toBe(true)
      expect(state.panelOpen).toBe(false)
    })
  })

  describe('setPanelOpen', () => {
    it('should set panel open to true', () => {
      store.dispatch(setPanelOpen(true))
      expect(store.getState().inAppNotifications.panelOpen).toBe(true)
    })

    it('should set panel open to false', () => {
      store = createTestStore({ panelOpen: true })
      store.dispatch(setPanelOpen(false))
      expect(store.getState().inAppNotifications.panelOpen).toBe(false)
    })
  })

  describe('togglePanel', () => {
    it('should toggle panel from closed to open', () => {
      store.dispatch(togglePanel())
      expect(store.getState().inAppNotifications.panelOpen).toBe(true)
    })

    it('should toggle panel from open to closed', () => {
      store = createTestStore({ panelOpen: true })
      store.dispatch(togglePanel())
      expect(store.getState().inAppNotifications.panelOpen).toBe(false)
    })
  })

  describe('addNotificationFromWebSocket', () => {
    it('should prepend new notification to list', () => {
      store = createTestStore({ notifications: [mockReadNotification] })
      store.dispatch(addNotificationFromWebSocket(mockNotification))

      const state = store.getState().inAppNotifications
      expect(state.notifications).toHaveLength(2)
      expect(state.notifications[0]).toEqual(mockNotification)
      expect(state.notifications[1]).toEqual(mockReadNotification)
    })

    it('should increment unread count', () => {
      store = createTestStore({ unreadCount: 2 })
      store.dispatch(addNotificationFromWebSocket(mockNotification))

      expect(store.getState().inAppNotifications.unreadCount).toBe(3)
    })

    it('should work with empty notification list', () => {
      store.dispatch(addNotificationFromWebSocket(mockNotification))

      const state = store.getState().inAppNotifications
      expect(state.notifications).toHaveLength(1)
      expect(state.notifications[0]).toEqual(mockNotification)
      expect(state.unreadCount).toBe(1)
    })
  })

  describe('markNotificationReadLocally', () => {
    it('should mark unread notification as read', () => {
      store = createTestStore({
        notifications: [mockNotification],
        unreadCount: 1,
      })
      store.dispatch(markNotificationReadLocally('notif-1'))

      const state = store.getState().inAppNotifications
      expect(state.notifications[0].read_time).not.toBeNull()
      expect(state.unreadCount).toBe(0)
    })

    it('should not change already read notification', () => {
      const readTime = '2024-01-01T01:00:00Z'
      const notification = { ...mockNotification, read_time: readTime }
      store = createTestStore({
        notifications: [notification],
        unreadCount: 0,
      })
      store.dispatch(markNotificationReadLocally('notif-1'))

      const state = store.getState().inAppNotifications
      expect(state.notifications[0].read_time).toBe(readTime)
      expect(state.unreadCount).toBe(0)
    })

    it('should do nothing if notification not found', () => {
      store = createTestStore({
        notifications: [mockNotification],
        unreadCount: 1,
      })
      store.dispatch(markNotificationReadLocally('non-existent'))

      const state = store.getState().inAppNotifications
      expect(state.notifications[0].read_time).toBeNull()
      expect(state.unreadCount).toBe(1)
    })

    it('should not let unread count go below 0', () => {
      store = createTestStore({
        notifications: [mockNotification],
        unreadCount: 0,
      })
      store.dispatch(markNotificationReadLocally('notif-1'))

      expect(store.getState().inAppNotifications.unreadCount).toBe(0)
    })
  })

  describe('markAllNotificationsReadLocally', () => {
    it('should mark all notifications as read', () => {
      const unreadNotification2: InAppNotification = {
        ...mockNotification,
        id: 'notif-3',
      }
      store = createTestStore({
        notifications: [mockNotification, unreadNotification2, mockReadNotification],
        unreadCount: 2,
      })
      store.dispatch(markAllNotificationsReadLocally())

      const state = store.getState().inAppNotifications
      expect(state.notifications.every((n) => n.read_time !== null)).toBe(true)
      expect(state.unreadCount).toBe(0)
    })

    it('should handle empty notification list', () => {
      store.dispatch(markAllNotificationsReadLocally())

      const state = store.getState().inAppNotifications
      expect(state.notifications).toHaveLength(0)
      expect(state.unreadCount).toBe(0)
    })
  })

  describe('removeNotificationsLocally', () => {
    it('should remove specified notifications', () => {
      const notification2: InAppNotification = { ...mockNotification, id: 'notif-3' }
      store = createTestStore({
        notifications: [mockNotification, notification2, mockReadNotification],
        unreadCount: 2,
      })
      store.dispatch(removeNotificationsLocally(['notif-1', 'notif-2']))

      const state = store.getState().inAppNotifications
      expect(state.notifications).toHaveLength(1)
      expect(state.notifications[0].id).toBe('notif-3')
    })

    it('should decrement unread count for removed unread notifications', () => {
      store = createTestStore({
        notifications: [mockNotification, mockReadNotification],
        unreadCount: 1,
      })
      store.dispatch(removeNotificationsLocally(['notif-1']))

      expect(store.getState().inAppNotifications.unreadCount).toBe(0)
    })

    it('should not decrement unread count for removed read notifications', () => {
      store = createTestStore({
        notifications: [mockNotification, mockReadNotification],
        unreadCount: 1,
      })
      store.dispatch(removeNotificationsLocally(['notif-2']))

      expect(store.getState().inAppNotifications.unreadCount).toBe(1)
    })

    it('should handle removing non-existent notifications', () => {
      store = createTestStore({
        notifications: [mockNotification],
        unreadCount: 1,
      })
      store.dispatch(removeNotificationsLocally(['non-existent']))

      const state = store.getState().inAppNotifications
      expect(state.notifications).toHaveLength(1)
      expect(state.unreadCount).toBe(1)
    })
  })

  describe('setLoading', () => {
    it('should set loading to true', () => {
      store.dispatch(setLoading(true))
      expect(store.getState().inAppNotifications.isLoading).toBe(true)
    })

    it('should set loading to false', () => {
      store = createTestStore({ isLoading: true })
      store.dispatch(setLoading(false))
      expect(store.getState().inAppNotifications.isLoading).toBe(false)
    })
  })

  describe('resetInAppNotifications', () => {
    it('should reset to initial state', () => {
      store = createTestStore({
        notifications: [mockNotification, mockReadNotification],
        unreadCount: 5,
        isLoading: true,
        hasMore: false,
        panelOpen: true,
      })
      store.dispatch(resetInAppNotifications())

      const state = store.getState().inAppNotifications
      expect(state).toEqual(initialState)
    })
  })
})
