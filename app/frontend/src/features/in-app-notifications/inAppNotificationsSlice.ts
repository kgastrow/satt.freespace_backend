import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { InAppNotification } from '@/types/in-app-notification'
import { inAppNotificationsApi } from './inAppNotificationsApi'

/**
 * State for in-app notifications
 */
export interface InAppNotificationsState {
  /** List of notifications loaded from API */
  notifications: InAppNotification[]
  /** Count of unread notifications */
  unreadCount: number
  /** Whether initial data is loading */
  isLoading: boolean
  /** Whether there are more notifications to load */
  hasMore: boolean
  /** Whether the notification panel is open */
  panelOpen: boolean
  /** Count of notifications added via WebSocket since last API sync */
  pendingWebSocketCount: number
}

const initialState: InAppNotificationsState = {
  notifications: [],
  unreadCount: 0,
  isLoading: false,
  hasMore: true,
  panelOpen: false,
  pendingWebSocketCount: 0,
}

const inAppNotificationsSlice = createSlice({
  name: 'inAppNotifications',
  initialState,
  reducers: {
    /**
     * Set the panel open state
     */
    setPanelOpen: (state, action: PayloadAction<boolean>) => {
      state.panelOpen = action.payload
    },

    /**
     * Toggle the panel open state
     */
    togglePanel: (state) => {
      state.panelOpen = !state.panelOpen
    },

    /**
     * Handle incoming WebSocket notification - prepend to list and increment count
     */
    addNotificationFromWebSocket: (
      state,
      action: PayloadAction<InAppNotification>
    ) => {
      // Check for duplicate notification (same ID already exists)
      const exists = state.notifications.some((n) => n.id === action.payload.id)
      if (exists) {
        return
      }
      // Prepend new notification to the list
      state.notifications = [action.payload, ...state.notifications]
      // Increment unread count since WebSocket notifications are always new/unread
      state.unreadCount += 1
      // Track WebSocket additions to handle race conditions with API fetch
      state.pendingWebSocketCount += 1
    },

    /**
     * Update a notification's read status locally
     */
    markNotificationReadLocally: (state, action: PayloadAction<string>) => {
      const notification = state.notifications.find(
        (n) => n.id === action.payload
      )
      if (notification && !notification.read_time) {
        notification.read_time = new Date().toISOString()
        state.unreadCount = Math.max(0, state.unreadCount - 1)
      }
    },

    /**
     * Mark all notifications as read locally
     */
    markAllNotificationsReadLocally: (state) => {
      const now = new Date().toISOString()
      state.notifications.forEach((n) => {
        if (!n.read_time) {
          n.read_time = now
        }
      })
      state.unreadCount = 0
    },

    /**
     * Remove dismissed notifications from local state
     */
    removeNotificationsLocally: (state, action: PayloadAction<string[]>) => {
      const idsToRemove = new Set(action.payload)
      const removedUnread = state.notifications.filter(
        (n) => idsToRemove.has(n.id) && !n.read_time
      ).length
      state.notifications = state.notifications.filter(
        (n) => !idsToRemove.has(n.id)
      )
      state.unreadCount = Math.max(0, state.unreadCount - removedUnread)
    },

    /**
     * Set loading state
     */
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.isLoading = action.payload
    },

    /**
     * Reset state to initial values
     */
    resetInAppNotifications: () => initialState,
  },
  extraReducers: (builder) => {
    // Handle successful fetch of notifications list
    builder.addMatcher(
      inAppNotificationsApi.endpoints.getInAppNotifications.matchFulfilled,
      (state, action) => {
        const { items, total, offset } = action.payload
        if (offset === 0) {
          // First page - replace notifications
          state.notifications = items
        } else {
          // Subsequent pages - append notifications
          // Deduplicate by ID in case of race conditions
          const existingIds = new Set(state.notifications.map((n) => n.id))
          const newItems = items.filter((n) => !existingIds.has(n.id))
          state.notifications = [...state.notifications, ...newItems]
        }
        state.hasMore = state.notifications.length < total
        state.isLoading = false
      }
    )

    // Handle fetch notifications pending
    builder.addMatcher(
      inAppNotificationsApi.endpoints.getInAppNotifications.matchPending,
      (state) => {
        state.isLoading = true
      }
    )

    // Handle fetch notifications error
    builder.addMatcher(
      inAppNotificationsApi.endpoints.getInAppNotifications.matchRejected,
      (state) => {
        state.isLoading = false
      }
    )

    // Handle successful fetch of unread count
    builder.addMatcher(
      inAppNotificationsApi.endpoints.getUnreadCount.matchFulfilled,
      (state, action) => {
        // Add pendingWebSocketCount to handle notifications that arrived via WS
        // after the API request was made but before it completed
        state.unreadCount = action.payload.unread_count + state.pendingWebSocketCount
        // Reset pending count since we've now synced with server
        state.pendingWebSocketCount = 0
      }
    )

    // Handle successful mark as read
    builder.addMatcher(
      inAppNotificationsApi.endpoints.markAsRead.matchFulfilled,
      (_state, action) => {
        // The optimistic update is done via markNotificationReadLocally
        // This just confirms it succeeded - nothing else needed
        void action
      }
    )

    // Handle successful mark all as read
    builder.addMatcher(
      inAppNotificationsApi.endpoints.markAllAsRead.matchFulfilled,
      (state) => {
        // Mark all notifications in local state as read
        const now = new Date().toISOString()
        state.notifications.forEach((n) => {
          if (!n.read_time) {
            n.read_time = now
          }
        })
        state.unreadCount = 0
      }
    )

    // Handle successful dismiss
    builder.addMatcher(
      inAppNotificationsApi.endpoints.dismissNotifications.matchFulfilled,
      (_state, action) => {
        // The optimistic update is done via removeNotificationsLocally
        // This just confirms it succeeded - nothing else needed
        void action
      }
    )
  },
})

export const {
  setPanelOpen,
  togglePanel,
  addNotificationFromWebSocket,
  markNotificationReadLocally,
  markAllNotificationsReadLocally,
  removeNotificationsLocally,
  setLoading,
  resetInAppNotifications,
} = inAppNotificationsSlice.actions

export default inAppNotificationsSlice.reducer
