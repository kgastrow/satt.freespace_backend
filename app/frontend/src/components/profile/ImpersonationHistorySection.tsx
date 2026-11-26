import { useTranslation } from 'react-i18next'
import { useGetMyImpersonationHistoryQuery } from '@/features/impersonation/impersonationApi'
import { useImpersonation } from '@/hooks/useImpersonation'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { DataTable, type Column } from '@/components/DataTable'
import type { MyImpersonationHistoryItem } from '@/types/impersonation'

/**
 * Format a duration from start and end timestamps
 */
function formatDuration(startTime: string, endTime: string): string {
  const start = new Date(startTime)
  const end = new Date(endTime)
  const durationMs = end.getTime() - start.getTime()
  const durationSeconds = Math.floor(durationMs / 1000)

  if (durationSeconds < 60) {
    return `${durationSeconds}s`
  }

  const minutes = Math.floor(durationSeconds / 60)
  const seconds = durationSeconds % 60

  if (minutes < 60) {
    return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60

  if (remainingMinutes > 0) {
    return `${hours}h ${remainingMinutes}m`
  }
  return `${hours}h`
}

/**
 * Format impersonator name with fallback to email
 */
function formatImpersonatorName(impersonator: MyImpersonationHistoryItem['impersonator']): string {
  if (impersonator.first_name && impersonator.last_name) {
    return `${impersonator.first_name} ${impersonator.last_name}`
  }
  if (impersonator.first_name) {
    return impersonator.first_name
  }
  return impersonator.email
}

/**
 * Section in the user's profile showing their impersonation history.
 * Only renders if the user has been impersonated before.
 */
export function ImpersonationHistorySection() {
  const { t } = useTranslation('settings')
  const { isImpersonating } = useImpersonation()

  // Skip the query entirely if we're impersonating (endpoint returns 403)
  const { data, isLoading, error } = useGetMyImpersonationHistoryQuery(undefined, {
    skip: isImpersonating,
  })

  // Don't render while impersonating (blocked by backend)
  if (isImpersonating) {
    return null
  }

  // Handle 403 error gracefully (in case impersonation state isn't synced yet)
  if (error && 'status' in error && error.status === 403) {
    return null
  }

  // Don't render if no history and not loading
  if (!isLoading && (!data?.items || data.items.length === 0)) {
    return null
  }

  const columns: Column<MyImpersonationHistoryItem>[] = [
    {
      key: 'impersonator',
      header: t('profile.impersonationHistory.columns.impersonator'),
      cell: (item) => (
        <div>
          <div className="font-medium">{formatImpersonatorName(item.impersonator)}</div>
          <div className="text-sm text-muted-foreground">{item.impersonator.email}</div>
        </div>
      ),
    },
    {
      key: 'startTime',
      header: t('profile.impersonationHistory.columns.startTime'),
      cell: (item) => (
        <span>
          {new Date(item.created_time).toLocaleString()}
        </span>
      ),
    },
    {
      key: 'endTime',
      header: t('profile.impersonationHistory.columns.endTime'),
      cell: (item) => (
        <span>
          {new Date(item.ended_time).toLocaleString()}
        </span>
      ),
    },
    {
      key: 'duration',
      header: t('profile.impersonationHistory.columns.duration'),
      cell: (item) => (
        <span>{formatDuration(item.created_time, item.ended_time)}</span>
      ),
    },
  ]

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <CardTitle>{t('profile.impersonationHistory.title')}</CardTitle>
        <CardDescription>{t('profile.impersonationHistory.description')}</CardDescription>
      </CardHeader>
      <CardContent>
        <DataTable
          columns={columns}
          data={data?.items || []}
          isLoading={isLoading}
          emptyMessage={t('profile.impersonationHistory.empty')}
        />
      </CardContent>
    </Card>
  )
}
