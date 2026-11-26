import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { CheckCheck, Bell } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Skeleton } from '@/components/ui/skeleton'
import { Separator } from '@/components/ui/separator'
import { NotificationItem } from '@/components/NotificationItem'
import type { InAppNotification } from '@/types/in-app-notification'

interface NotificationPanelProps {
  notifications: InAppNotification[]
  isLoading: boolean
  hasMore: boolean
  unreadCount: number
  onMarkAsRead: (id: string) => void
  onMarkAllAsRead: () => void
  onDismiss: (id: string) => void
  onLoadMore: () => void
  onClose?: () => void
}

function NotificationSkeleton() {
  return (
    <div className="flex flex-col gap-1 p-3">
      <div className="flex items-start gap-2 pl-3">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-1/4" />
        </div>
      </div>
    </div>
  )
}

function EmptyState() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <Bell className="h-12 w-12 text-muted-foreground/50 mb-4" />
      <p className="text-sm font-medium text-muted-foreground">
        {t('common:notifications.empty')}
      </p>
      <p className="text-xs text-muted-foreground/70 mt-1">
        {t('common:notifications.emptyDescription')}
      </p>
    </div>
  )
}

function NotificationPanelFooter({ onClose }: { onClose?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const handleViewAll = () => {
    onClose?.()
    navigate('/notifications')
  }

  return (
    <>
      <Separator />
      <div className="px-4 py-2 text-center">
        <Button
          variant="link"
          size="sm"
          className="h-auto py-1 text-xs text-muted-foreground"
          onClick={handleViewAll}
        >
          {t('common:notifications.viewAll')}
        </Button>
      </div>
    </>
  )
}

export function NotificationPanel({
  notifications,
  isLoading,
  hasMore,
  unreadCount,
  onMarkAsRead,
  onMarkAllAsRead,
  onDismiss,
  onLoadMore,
  onClose,
}: NotificationPanelProps) {
  const { t } = useTranslation()

  const showLoadingState = isLoading && notifications.length === 0
  const showEmptyState = !isLoading && notifications.length === 0

  return (
    <div className="flex flex-col w-full max-w-80 max-h-[480px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h2 className="text-sm font-semibold">
          {t('common:notifications.title')}
        </h2>
        {unreadCount > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-auto py-1 px-2 text-xs"
            onClick={onMarkAllAsRead}
          >
            <CheckCheck className="h-3.5 w-3.5 mr-1" />
            {t('common:notifications.markAllRead')}
          </Button>
        )}
      </div>

      {/* Notification list */}
      <ScrollArea className="flex-1">
        <div className={cn('divide-y', showEmptyState && 'min-h-[200px]')}>
          {showLoadingState && (
            <>
              <NotificationSkeleton />
              <NotificationSkeleton />
              <NotificationSkeleton />
            </>
          )}

          {showEmptyState && <EmptyState />}

          {!showLoadingState &&
            notifications.map((notification) => (
              <NotificationItem
                key={notification.id}
                notification={notification}
                onMarkAsRead={onMarkAsRead}
                onDismiss={onDismiss}
                onClose={onClose}
              />
            ))}

          {/* Load more button */}
          {hasMore && notifications.length > 0 && (
            <div className="p-3">
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={onLoadMore}
                disabled={isLoading}
              >
                {isLoading
                  ? t('common:common.loading')
                  : t('common:notifications.loadMore')}
              </Button>
            </div>
          )}

          {/* Loading indicator for load more */}
          {isLoading && notifications.length > 0 && (
            <div className="p-3">
              <div className="flex items-center justify-center">
                <Skeleton className="h-8 w-full rounded-md" />
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Footer - View All link */}
      {notifications.length > 0 && (
        <NotificationPanelFooter onClose={onClose} />
      )}
    </div>
  )
}
