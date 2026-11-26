import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCheck, Bell } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { NotificationItem } from '@/components/NotificationItem'
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

const PAGE_SIZE = 20

export function NotificationsPage() {
  const { t } = useTranslation()
  const dispatch = useAppDispatch()
  const [offset, setOffset] = useState(0)
  const [filterUnread, setFilterUnread] = useState(false)

  const { unreadCount } = useInAppNotifications()
  const { notifications, hasMore } = useAppSelector(
    (state) => state.inAppNotifications,
  )

  const { isFetching } = useGetInAppNotificationsQuery({
    limit: PAGE_SIZE,
    offset,
    unread_only: filterUnread || undefined,
  })

  const [markAsRead] = useMarkAsReadMutation()
  const [markAllAsRead] = useMarkAllAsReadMutation()
  const [dismissNotifications] = useDismissNotificationsMutation()

  const handleMarkAsRead = useCallback(
    async (id: string) => {
      dispatch(markNotificationReadLocally(id))
      try {
        await markAsRead(id).unwrap()
      } catch {
        // API invalidation will refetch
      }
    },
    [dispatch, markAsRead],
  )

  const handleMarkAllAsRead = useCallback(async () => {
    dispatch(markAllNotificationsReadLocally())
    try {
      await markAllAsRead().unwrap()
    } catch {
      // API invalidation will refetch
    }
  }, [dispatch, markAllAsRead])

  const handleDismiss = useCallback(
    async (id: string) => {
      dispatch(removeNotificationsLocally([id]))
      try {
        await dismissNotifications([id]).unwrap()
      } catch {
        // API invalidation will refetch
      }
    },
    [dispatch, dismissNotifications],
  )

  const handleLoadMore = useCallback(() => {
    if (!isFetching && hasMore) {
      setOffset((prev) => prev + PAGE_SIZE)
    }
  }, [isFetching, hasMore])

  const handleFilterChange = useCallback((unreadOnly: boolean) => {
    setFilterUnread(unreadOnly)
    setOffset(0)
  }, [])

  const showEmpty = !isFetching && notifications.length === 0

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('common:notifications.pageTitle')}
        description={t('common:notifications.pageDescription')}
      >
        {unreadCount > 0 && (
          <Button variant="outline" onClick={handleMarkAllAsRead}>
            <CheckCheck className="mr-2 h-4 w-4" />
            {t('common:notifications.markAllRead')}
          </Button>
        )}
      </PageHeader>

      {/* Filter tabs */}
      <div className="flex gap-2">
        <Button
          variant={!filterUnread ? 'default' : 'outline'}
          size="sm"
          onClick={() => handleFilterChange(false)}
        >
          {t('common:notifications.filterAll')}
        </Button>
        <Button
          variant={filterUnread ? 'default' : 'outline'}
          size="sm"
          onClick={() => handleFilterChange(true)}
        >
          {t('common:notifications.filterUnread')}
          {unreadCount > 0 && (
            <span className="ml-1.5 rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-medium text-destructive-foreground">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </Button>
      </div>

      {/* Notification list */}
      <div className="rounded-md border divide-y">
        {isFetching && notifications.length === 0 && (
          <>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1 p-3">
                <div className="flex items-start gap-2 pl-3">
                  <div className="flex-1 space-y-2">
                    <Skeleton className="h-4 w-3/4" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                </div>
              </div>
            ))}
          </>
        )}

        {showEmpty && (
          <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
            <Bell className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-sm font-medium text-muted-foreground">
              {t('common:notifications.empty')}
            </p>
            <p className="text-xs text-muted-foreground/70 mt-1">
              {t('common:notifications.emptyDescription')}
            </p>
          </div>
        )}

        {notifications.map((notification) => (
          <NotificationItem
            key={notification.id}
            notification={notification}
            onMarkAsRead={handleMarkAsRead}
            onDismiss={handleDismiss}
          />
        ))}
      </div>

      {/* Load more */}
      {hasMore && notifications.length > 0 && (
        <div className="flex justify-center">
          <Button
            variant="outline"
            onClick={handleLoadMore}
            disabled={isFetching}
          >
            {isFetching
              ? t('common:common.loading')
              : t('common:notifications.loadMore')}
          </Button>
        </div>
      )}

      {!hasMore && notifications.length > 0 && (
        <p className="text-center text-sm text-muted-foreground">
          {t('common:notifications.noMore')}
        </p>
      )}
    </div>
  )
}
