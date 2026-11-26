import { useState, useCallback, memo } from 'react'
import { useTranslation } from 'react-i18next'
import { Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { NotificationPanel } from '@/components/NotificationPanel'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import {
  markNotificationReadLocally,
  markAllNotificationsReadLocally,
  removeNotificationsLocally,
} from '@/features/in-app-notifications/inAppNotificationsSlice'
import {
  useGetInAppNotificationsQuery,
  useMarkAsReadMutation,
  useMarkAllAsReadMutation,
  useDismissNotificationsMutation,
} from '@/features/in-app-notifications/inAppNotificationsApi'
import { useInAppNotifications } from '@/hooks/useInAppNotifications'

const NOTIFICATIONS_PAGE_SIZE = 10

function NotificationBellComponent() {
  const { t } = useTranslation()
  const dispatch = useAppDispatch()
  const [offset, setOffset] = useState(0)
  const [panelOpen, setPanelOpen] = useState(false)

  const { notifications, isLoading, hasMore } = useAppSelector(
    (state) => state.inAppNotifications
  )

  // Use the hook for WebSocket integration and unread count fetching
  const { unreadCount } = useInAppNotifications()

  // Fetch notifications when panel opens
  const { isFetching } = useGetInAppNotificationsQuery(
    { limit: NOTIFICATIONS_PAGE_SIZE, offset },
    { skip: !panelOpen && offset === 0 }
  )

  // Mutations
  const [markAsRead] = useMarkAsReadMutation()
  const [markAllAsRead] = useMarkAllAsReadMutation()
  const [dismissNotifications] = useDismissNotificationsMutation()

  const handleOpenChange = useCallback(
    (open: boolean) => {
      setPanelOpen(open)
      // Reset offset when opening panel to fetch fresh data
      if (open && offset !== 0) {
        setOffset(0)
      }
    },
    [offset]
  )

  const handleMarkAsRead = useCallback(
    async (id: string) => {
      // Optimistic update
      dispatch(markNotificationReadLocally(id))
      try {
        await markAsRead(id).unwrap()
      } catch {
        // On error, the API invalidation will refetch and correct the state
      }
    },
    [dispatch, markAsRead]
  )

  const handleMarkAllAsRead = useCallback(async () => {
    // Optimistic update
    dispatch(markAllNotificationsReadLocally())
    try {
      await markAllAsRead().unwrap()
    } catch {
      // On error, the API invalidation will refetch and correct the state
    }
  }, [dispatch, markAllAsRead])

  const handleDismiss = useCallback(
    async (id: string) => {
      // Optimistic update
      dispatch(removeNotificationsLocally([id]))
      try {
        await dismissNotifications([id]).unwrap()
      } catch {
        // On error, the API invalidation will refetch and correct the state
      }
    },
    [dispatch, dismissNotifications]
  )

  const handleLoadMore = useCallback(() => {
    if (!isFetching && hasMore) {
      setOffset((prev) => prev + NOTIFICATIONS_PAGE_SIZE)
    }
  }, [isFetching, hasMore])

  const handleClose = useCallback(() => {
    setPanelOpen(false)
  }, [])

  return (
    <DropdownMenu open={panelOpen} onOpenChange={handleOpenChange}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={t('common:notifications.openPanel')}
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span
              className={cn(
                'absolute -top-0.5 -right-0.5 flex items-center justify-center',
                'min-w-[18px] h-[18px] px-1 text-[10px] font-medium',
                'rounded-full bg-destructive text-destructive-foreground'
              )}
              aria-label={t('common:notifications.unreadCount', { count: unreadCount })}
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="p-0" sideOffset={8}>
        <NotificationPanel
          notifications={notifications}
          isLoading={isLoading || isFetching}
          hasMore={hasMore}
          unreadCount={unreadCount}
          onMarkAsRead={handleMarkAsRead}
          onMarkAllAsRead={handleMarkAllAsRead}
          onDismiss={handleDismiss}
          onLoadMore={handleLoadMore}
          onClose={handleClose}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

// Memoize to prevent re-renders when parent state changes
export const NotificationBell = memo(NotificationBellComponent)
