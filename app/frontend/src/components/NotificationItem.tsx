import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import type { InAppNotification } from '@/types/in-app-notification'

/**
 * Format a date as a relative time string (e.g., "2 hours ago")
 */
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffSeconds < 60) {
    return 'just now'
  } else if (diffMinutes < 60) {
    return `${diffMinutes} minute${diffMinutes !== 1 ? 's' : ''} ago`
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
  } else {
    return date.toLocaleDateString()
  }
}

interface NotificationItemProps {
  notification: InAppNotification
  onMarkAsRead: (id: string) => void
  onDismiss: (id: string) => void
  onClose?: () => void
}

export function NotificationItem({
  notification,
  onMarkAsRead,
  onDismiss,
  onClose,
}: NotificationItemProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const isUnread = !notification.read_time
  const timeAgo = notification.created_time
    ? formatRelativeTime(notification.created_time)
    : ''

  const handleClick = () => {
    if (isUnread) {
      onMarkAsRead(notification.id)
    }
    if (notification.link) {
      onClose?.()
      navigate(notification.link)
    }
  }

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDismiss(notification.id)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          handleClick()
        }
      }}
      className={cn(
        'group relative flex flex-col gap-1 p-3 text-left transition-colors',
        notification.link && 'cursor-pointer hover:bg-accent',
        isUnread && 'bg-accent/50'
      )}
    >
      {isUnread && (
        <span
          className="absolute left-1 top-1/2 h-2 w-2 -translate-y-1/2 rounded-full bg-primary"
          aria-label={t('common:notifications.unread')}
        />
      )}
      <div className="flex items-start justify-between gap-2 pl-3">
        <div className="flex-1 min-w-0">
          <p className={cn('text-sm font-medium truncate', isUnread && 'font-semibold')}>
            {notification.title}
          </p>
          {notification.body && (
            <p className="text-sm text-muted-foreground line-clamp-2 mt-0.5">
              {notification.body}
            </p>
          )}
          {timeAgo && (
            <p className="text-xs text-muted-foreground mt-1">{timeAgo}</p>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={handleDismiss}
          aria-label={t('common:notifications.dismiss')}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
