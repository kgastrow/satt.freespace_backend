import { createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { Announcement, AnnouncementPriority } from '@/types/announcement'
import { announcementsApi } from './announcementsApi'

/**
 * State for announcements
 */
export interface AnnouncementsState {
  /** List of announcements loaded from API */
  announcements: Announcement[]
  /** Whether initial data is loading */
  isLoading: boolean
  /** Set of announcement IDs dismissed locally (optimistic updates) */
  locallyDismissedIds: Set<string>
}

const initialState: AnnouncementsState = {
  announcements: [],
  isLoading: false,
  locallyDismissedIds: new Set(),
}

/**
 * Priority order for sorting (critical > high > normal > low)
 */
const PRIORITY_ORDER: Record<AnnouncementPriority, number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
}

/**
 * Sort announcements according to requirements:
 * 1. Non-dismissible announcements first
 * 2. Then by priority (critical > high > normal > low)
 * 3. Then platform-wide before org-specific
 * 4. Then by created_time (newest first)
 */
function sortAnnouncements(announcements: Announcement[]): Announcement[] {
  return [...announcements].sort((a, b) => {
    // Non-dismissible announcements first
    if (a.is_dismissible !== b.is_dismissible) {
      return a.is_dismissible ? 1 : -1
    }

    // Then by priority
    const priorityDiff = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority]
    if (priorityDiff !== 0) {
      return priorityDiff
    }

    // Then platform-wide before org-specific
    if (a.is_platform_wide !== b.is_platform_wide) {
      return a.is_platform_wide ? -1 : 1
    }

    // Then by created_time (newest first)
    const aTime = a.created_time ? new Date(a.created_time).getTime() : 0
    const bTime = b.created_time ? new Date(b.created_time).getTime() : 0
    return bTime - aTime
  })
}

const announcementsSlice = createSlice({
  name: 'announcements',
  initialState,
  reducers: {
    /**
     * Set the announcements list
     */
    setAnnouncements: (state, action: PayloadAction<Announcement[]>) => {
      state.announcements = sortAnnouncements(action.payload)
    },

    /**
     * Dismiss an announcement locally (optimistic update)
     */
    dismissAnnouncementLocally: (state, action: PayloadAction<string>) => {
      state.locallyDismissedIds.add(action.payload)
      // Remove from announcements array
      state.announcements = state.announcements.filter(
        (a) => a.id !== action.payload
      )
    },

    /**
     * Add a new announcement from WebSocket (real-time)
     */
    addAnnouncementFromWebSocket: (
      state,
      action: PayloadAction<Announcement>
    ) => {
      const announcement = action.payload
      // Don't add if already exists or if locally dismissed
      if (
        state.announcements.some((a) => a.id === announcement.id) ||
        state.locallyDismissedIds.has(announcement.id)
      ) {
        return
      }
      state.announcements = sortAnnouncements([
        ...state.announcements,
        announcement,
      ])
    },

    /**
     * Update an existing announcement from WebSocket (real-time)
     */
    updateAnnouncementFromWebSocket: (
      state,
      action: PayloadAction<Announcement>
    ) => {
      const updated = action.payload
      const index = state.announcements.findIndex((a) => a.id === updated.id)
      if (index !== -1) {
        state.announcements[index] = updated
        state.announcements = sortAnnouncements(state.announcements)
      }
    },

    /**
     * Remove an announcement from WebSocket (real-time deletion)
     */
    removeAnnouncementFromWebSocket: (
      state,
      action: PayloadAction<string>
    ) => {
      state.announcements = state.announcements.filter(
        (a) => a.id !== action.payload
      )
    },

    /**
     * Reset state to initial values
     */
    resetAnnouncements: () => initialState,
  },
  extraReducers: (builder) => {
    // Handle successful fetch of active announcements
    builder.addMatcher(
      announcementsApi.endpoints.getActiveAnnouncements.matchFulfilled,
      (state, action) => {
        const announcements = action.payload.announcements
        // Filter out locally dismissed announcements
        const filtered = announcements.filter(
          (a) => !state.locallyDismissedIds.has(a.id)
        )
        state.announcements = sortAnnouncements(filtered)
        state.isLoading = false
      }
    )

    // Handle fetch announcements pending
    builder.addMatcher(
      announcementsApi.endpoints.getActiveAnnouncements.matchPending,
      (state) => {
        state.isLoading = true
      }
    )

    // Handle fetch announcements error
    builder.addMatcher(
      announcementsApi.endpoints.getActiveAnnouncements.matchRejected,
      (state) => {
        state.isLoading = false
      }
    )

    // Handle successful dismissal
    builder.addMatcher(
      announcementsApi.endpoints.dismissAnnouncement.matchFulfilled,
      (_state, action) => {
        // The optimistic update is done via dismissAnnouncementLocally
        // This just confirms it succeeded - nothing else needed
        void action
      }
    )
  },
})

export const {
  setAnnouncements,
  dismissAnnouncementLocally,
  addAnnouncementFromWebSocket,
  updateAnnouncementFromWebSocket,
  removeAnnouncementFromWebSocket,
  resetAnnouncements,
} = announcementsSlice.actions

export default announcementsSlice.reducer
