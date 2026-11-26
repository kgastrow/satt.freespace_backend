import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CardSkeleton } from '@/components/skeletons'
import { useGetMetricsSummaryQuery } from '@/features/metrics/metricsApi'

export function MetricsPage() {
  const { t } = useTranslation('admin')
  const [autoRefresh, setAutoRefresh] = useState(false)
  const { data, isLoading, isFetching, refetch } = useGetMetricsSummaryQuery(undefined, {
    pollingInterval: autoRefresh ? 10000 : 0, // 10 seconds
  })

  useEffect(() => {
    // Refetch when component mounts
    refetch()
  }, [refetch])

  const formatUptime = (seconds: number) => {
    const days = Math.floor(seconds / 86400)
    const hours = Math.floor((seconds % 86400) / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    if (days > 0) return `${days}d ${hours}h`
    if (hours > 0) return `${hours}h ${minutes}m`
    return `${minutes}m`
  }

  const getStatusColor = (value: number, thresholds: { warn: number; error: number }) => {
    if (value >= thresholds.error) return 'text-destructive'
    if (value >= thresholds.warn) return 'text-yellow-600 dark:text-yellow-400'
    return 'text-green-600 dark:text-green-400'
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('metrics.pageTitle')}
          description={t('metrics.pageDescription')}
        />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} variant="stats" />
          ))}
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('metrics.pageTitle')}
          description={t('metrics.pageDescription')}
        />
        <Card>
          <CardContent className="py-8">
            <p className="text-center text-muted-foreground">
              {t('metrics.errorMessage')}
            </p>
            <div className="flex justify-center mt-4">
              <Button onClick={() => refetch()}>{t('metrics.retry')}</Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('metrics.pageTitle')}
        description={t('metrics.pageDescription')}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch
              id="auto-refresh"
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
            <Label htmlFor="auto-refresh">{t('metrics.autoRefresh')}</Label>
          </div>
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            {isFetching ? t('metrics.refreshing') : t('metrics.refresh')}
          </Button>
        </div>
      </PageHeader>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Request Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.requests.title')}</CardTitle>
            <CardDescription>{t('metrics.requests.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.requests.rate')}</span>
              <span className="font-mono">
                {data.requests.rate_per_minute.toFixed(1)}/min
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.requests.avgLatency')}</span>
              <span className="font-mono">{data.requests.avg_latency_ms.toFixed(0)}ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.requests.errorRate')}</span>
              <span
                className={`font-mono ${getStatusColor(data.requests.error_rate, { warn: 1, error: 5 })}`}
              >
                {data.requests.error_rate.toFixed(2)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.requests.total')}</span>
              <span className="font-mono">{data.requests.total.toLocaleString()}</span>
            </div>
          </CardContent>
        </Card>

        {/* Database Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.database.title')}</CardTitle>
            <CardDescription>{t('metrics.database.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.database.poolSize')}</span>
              <span className="font-mono">{data.database.pool_size}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.database.inUse')}</span>
              <span
                className={`font-mono ${getStatusColor(Math.min((data.database.connections_in_use / data.database.pool_size) * 100, 100), { warn: 70, error: 90 })}`}
              >
                {data.database.connections_in_use}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.database.available')}</span>
              <span className="font-mono">{data.database.connections_available}</span>
            </div>
          </CardContent>
        </Card>

        {/* Cache Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.cache.title')}</CardTitle>
            <CardDescription>{t('metrics.cache.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.cache.status')}</span>
              <Badge variant={data.cache.connected ? 'default' : 'destructive'}>
                {data.cache.connected ? t('metrics.cache.connected') : t('metrics.cache.disconnected')}
              </Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.cache.hitRate')}</span>
              <span
                className={`font-mono ${getStatusColor(100 - data.cache.hit_rate, { warn: 20, error: 50 })}`}
              >
                {data.cache.hit_rate.toFixed(1)}%
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Active Users */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.users.title')}</CardTitle>
            <CardDescription>{t('metrics.users.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-4xl font-bold">{data.users.active_count}</p>
            <p className="text-sm text-muted-foreground">{t('metrics.users.subtitle')}</p>
          </CardContent>
        </Card>

        {/* Background Jobs */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.jobs.title')}</CardTitle>
            <CardDescription>{t('metrics.jobs.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.pending')}</span>
              <span className="font-mono">{data.jobs.pending}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.inProgress')}</span>
              <span className="font-mono">{data.jobs.in_progress}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.failed')}</span>
              <span
                className={`font-mono ${getStatusColor(data.jobs.failed_total, { warn: 5, error: 20 })}`}
              >
                {data.jobs.failed_total}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.queueDepth')}</span>
              <span
                className={`font-mono ${getStatusColor(data.jobs.queue_depth, { warn: 50, error: 100 })}`}
              >
                {data.jobs.queue_depth}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.stuckJobs')}</span>
              <span
                className={`font-mono ${getStatusColor(data.jobs.stuck_jobs_count, { warn: 1, error: 5 })}`}
              >
                {data.jobs.stuck_jobs_count}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.jobs.workersOnline')}</span>
              <span className="font-mono">{data.jobs.workers_online}</span>
            </div>
          </CardContent>
        </Card>

        {/* System Resources */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.system.title')}</CardTitle>
            <CardDescription>{t('metrics.system.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.system.cpu')}</span>
              <span
                className={`font-mono ${getStatusColor(data.system.cpu_percent, { warn: 70, error: 90 })}`}
              >
                {data.system.cpu_percent.toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.system.memory')}</span>
              <span
                className={`font-mono ${getStatusColor(data.system.memory_percent, { warn: 80, error: 95 })}`}
              >
                {data.system.memory_percent.toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.system.uptime')}</span>
              <span className="font-mono">{formatUptime(data.system.uptime_seconds)}</span>
            </div>
          </CardContent>
        </Card>

        {/* Security Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.security.title')}</CardTitle>
            <CardDescription>{t('metrics.security.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.security.failedLogins')}</span>
              <span
                className={`font-mono ${getStatusColor(data.security.failed_logins_24h, { warn: 10, error: 50 })}`}
              >
                {data.security.failed_logins_24h}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.security.failed2fa')}</span>
              <span
                className={`font-mono ${getStatusColor(data.security.failed_2fa_24h, { warn: 5, error: 20 })}`}
              >
                {data.security.failed_2fa_24h}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.security.apiKeyFailures')}</span>
              <span
                className={`font-mono ${getStatusColor(data.security.api_key_failures_24h, { warn: 10, error: 50 })}`}
              >
                {data.security.api_key_failures_24h}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.security.bruteForceEvents')}</span>
              <span
                className={`font-mono ${getStatusColor(data.security.brute_force_events, { warn: 1, error: 5 })}`}
              >
                {data.security.brute_force_events}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Notification Metrics */}
        <Card>
          <CardHeader>
            <CardTitle>{t('metrics.notifications.title')}</CardTitle>
            <CardDescription>{t('metrics.notifications.description')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.notifications.emailSuccessRate')}</span>
              <span
                className={`font-mono ${getStatusColor(100 - data.notifications.email_success_rate, { warn: 10, error: 20 })}`}
              >
                {data.notifications.email_success_rate.toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.notifications.smsSuccessRate')}</span>
              <span
                className={`font-mono ${getStatusColor(100 - data.notifications.sms_success_rate, { warn: 10, error: 20 })}`}
              >
                {data.notifications.sms_success_rate.toFixed(1)}%
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.notifications.totalSent')}</span>
              <span className="font-mono">{data.notifications.total_sent_24h}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">{t('metrics.notifications.totalFailed')}</span>
              <span
                className={`font-mono ${getStatusColor(data.notifications.total_failed_24h, { warn: 5, error: 20 })}`}
              >
                {data.notifications.total_failed_24h}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Rate Limit Metrics */}
        {data.rate_limit && (
          <Card>
            <CardHeader>
              <CardTitle>{t('metrics.rateLimit.title')}</CardTitle>
              <CardDescription>{t('metrics.rateLimit.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-muted-foreground">{t('metrics.rateLimit.totalViolations')}</span>
                <span
                  className={`font-mono ${getStatusColor(data.rate_limit.total_violations, { warn: 10, error: 50 })}`}
                >
                  {data.rate_limit.total_violations}
                </span>
              </div>
              {Object.keys(data.rate_limit.top_endpoints).length > 0 && (
                <div className="space-y-1">
                  <span className="text-sm text-muted-foreground">{t('metrics.rateLimit.topEndpoints')}</span>
                  <div className="space-y-1 pl-2">
                    {Object.entries(data.rate_limit.top_endpoints)
                      .slice(0, 3)
                      .map(([endpoint, count]) => (
                        <div key={endpoint} className="flex justify-between text-sm">
                          <span className="font-mono text-muted-foreground truncate max-w-[150px]" title={endpoint}>
                            {endpoint}
                          </span>
                          <span className="font-mono">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
              {Object.keys(data.rate_limit.top_ips).length > 0 && (
                <div className="space-y-1">
                  <span className="text-sm text-muted-foreground">{t('metrics.rateLimit.topIPs')}</span>
                  <div className="space-y-1 pl-2">
                    {Object.entries(data.rate_limit.top_ips)
                      .slice(0, 3)
                      .map(([ip, count]) => (
                        <div key={ip} className="flex justify-between text-sm">
                          <span className="font-mono text-muted-foreground">{ip}</span>
                          <span className="font-mono">{count}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
