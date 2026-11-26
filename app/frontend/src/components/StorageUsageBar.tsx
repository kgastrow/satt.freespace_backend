import { Progress } from '@/components/ui/progress'
import { cn, formatBytes } from '@/lib/utils'
import { useTranslation } from 'react-i18next'

interface StorageUsageBarProps {
  usedBytes: number
  quotaBytes: number | null
  className?: string
  showLabel?: boolean
}

export function StorageUsageBar({
  usedBytes,
  quotaBytes,
  className,
  showLabel = true,
}: StorageUsageBarProps) {
  const { t } = useTranslation()
  const percentage = quotaBytes ? Math.min((usedBytes / quotaBytes) * 100, 100) : 0
  const hasQuota = quotaBytes !== null && quotaBytes > 0

  // Color based on usage - uses theme-aware status colors
  const getColorClass = () => {
    if (!hasQuota) return 'bg-info'
    if (percentage >= 90) return 'bg-destructive'
    if (percentage >= 75) return 'bg-warning'
    return 'bg-success'
  }

  return (
    <div className={cn('space-y-2', className)}>
      {showLabel && (
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">{t('storage.used')}</span>
          <span className="font-medium">
            {formatBytes(usedBytes)}
            {hasQuota && ` / ${formatBytes(quotaBytes)}`}
          </span>
        </div>
      )}
      {hasQuota ? (
        <div className="relative">
          <Progress
            value={percentage}
            className="h-2"
          />
          <div
            className={cn('absolute inset-0 h-2 rounded-full', getColorClass())}
            style={{ width: `${percentage}%` }}
          />
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">{t('storage.noQuota')}</div>
      )}
      {hasQuota && showLabel && (
        <div className="text-xs text-muted-foreground text-right">
          {t('storage.percentUsed', { percent: percentage.toFixed(1) })}
        </div>
      )}
    </div>
  )
}
