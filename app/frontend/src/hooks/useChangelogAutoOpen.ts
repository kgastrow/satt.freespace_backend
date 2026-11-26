import { useCallback, useState } from 'react'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import { useAppSelector, useAppDispatch } from '@/store/hooks'
import { setHasCheckedSinceLogin } from '@/features/changelog/changelogSlice'
import { useGetUnreadChangelogCountQuery } from '@/features/changelog/changelogApi'

/**
 * Hook to manage changelog modal open state with auto-open on login.
 */
export function useChangelogAutoOpen() {
  const isEnabled = useFeatureFlag('changelog_enabled')
  const hasChecked = useAppSelector(
    (state) => state.changelog.hasCheckedSinceLogin
  )
  const unreadCount = useAppSelector((state) => state.changelog.unreadCount)
  const dispatch = useAppDispatch()

  // Fetch unread count when enabled
  useGetUnreadChangelogCountQuery(undefined, {
    skip: !isEnabled,
  })

  // Determine if modal should auto-open
  const shouldAutoOpen = isEnabled && !hasChecked && unreadCount > 0

  const [open, setOpenState] = useState(false)

  const setOpen = useCallback(
    (value: boolean) => {
      setOpenState(value)
      if (!value && !hasChecked) {
        dispatch(setHasCheckedSinceLogin(true))
      }
    },
    [dispatch, hasChecked]
  )

  // The consumer (AppSidebar) can check shouldAutoOpen to trigger opening
  return { open: open || shouldAutoOpen, setOpen }
}
