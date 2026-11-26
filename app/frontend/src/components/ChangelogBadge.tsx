import { useTranslation } from 'react-i18next'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import { useGetUnreadChangelogCountQuery } from '@/features/changelog/changelogApi'

/**
 * Badge showing unread changelog count.
 * Gated behind changelog_enabled feature flag.
 */
export function ChangelogBadge() {
  const { t } = useTranslation('common')
  const isEnabled = useFeatureFlag('changelog_enabled')
  const { data } = useGetUnreadChangelogCountQuery(undefined, {
    skip: !isEnabled,
    pollingInterval: 60000,
  })

  if (!isEnabled || !data || data.count === 0) return null

  const displayCount = data.count > 99 ? '99+' : data.count.toString()

  return (
    <span
      className="ml-auto inline-flex min-w-[18px] h-[18px] items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium text-destructive-foreground"
      aria-label={t('changelog.unreadCount', { count: data.count })}
    >
      {displayCount}
    </span>
  )
}
