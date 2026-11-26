import { useCallback, useMemo } from 'react'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  dismissAnnouncementLocally,
  resetAnnouncements,
} from '@/features/announcements/announcementsSlice'
import {
  useGetActiveAnnouncementsQuery,
  useDismissAnnouncementMutation,
} from '@/features/announcements/announcementsApi'
import type { Announcement } from '@/types/announcement'

export interface UseAnnouncementsReturn {
  /** Sorted announcements array */
  announcements: Announcement[]
  /** Whether announcements are loading */
  isLoading: boolean
  /** Function to dismiss an announcement */
  dismissAnnouncement: (announcementId: string) => Promise<void>
  /** The top announcement (first in sorted list) */
  topAnnouncement: Announcement | null
  /** Total count of announcements */
  announcementCount: number
}

/**
 * Hook to manage announcements and dismissal.
 *
 * This hook:
 * - Fetches active announcements from the API
 * - Manages announcements state from Redux
 * - Provides sorted announcements (non-dismissible first, by priority, platform-wide first, newest first)
 * - Handles optimistic dismissal with mutation
 * - Returns top announcement and count for UI
 *
 * @example
 * ```tsx
 * function AnnouncementBanner() {
 *   const { topAnnouncement, dismissAnnouncement, announcementCount } = useAnnouncements()
 *
 *   if (!topAnnouncement) return null
 *
 *   return (
 *     <div>
 *       <h3>{topAnnouncement.title}</h3>
 *       <p>{topAnnouncement.body}</p>
 *       {topAnnouncement.is_dismissible && (
 *         <button onClick={() => dismissAnnouncement(topAnnouncement.id)}>
 *           Dismiss
 *         </button>
 *       )}
 *       <span>{1} of {announcementCount}</span>
 *     </div>
 *   )
 * }
 * ```
 */
export function useAnnouncements(): UseAnnouncementsReturn {
  const dispatch = useAppDispatch()

  // Get announcements from Redux state
  const { announcements, isLoading: sliceLoading } = useAppSelector(
    (state) => state.announcements
  )

  // Fetch active announcements from API
  const { isFetching } = useGetActiveAnnouncementsQuery()

  // Dismissal mutation
  const [dismissMutation] = useDismissAnnouncementMutation()

  // Handle announcement dismissal with optimistic update
  const dismissAnnouncement = useCallback(
    async (announcementId: string) => {
      // Optimistically remove from UI immediately
      dispatch(dismissAnnouncementLocally(announcementId))

      // Call API to persist dismissal
      try {
        await dismissMutation(announcementId).unwrap()
      } catch {
        // If the API call fails, the announcement is already removed from local state
        // We could potentially add error handling here to re-add it, but for now
        // we'll let the next refetch restore the state
      }
    },
    [dispatch, dismissMutation]
  )

  // Compute derived values
  const topAnnouncement = useMemo(() => {
    return announcements.length > 0 ? announcements[0] : null
  }, [announcements])

  const announcementCount = announcements.length

  return {
    announcements,
    isLoading: sliceLoading || isFetching,
    dismissAnnouncement,
    topAnnouncement,
    announcementCount,
  }
}

/**
 * Hook to reset announcements state (useful for logout)
 */
export function useResetAnnouncements() {
  const dispatch = useAppDispatch()
  return useCallback(() => {
    dispatch(resetAnnouncements())
  }, [dispatch])
}
