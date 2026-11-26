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
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { CardSkeleton } from '@/components/skeletons'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { toast } from 'sonner'
import {
  useGetBackgroundJobsStatsQuery,
  useGetQueueHealthQuery,
  useToggleJobTypeMutation,
  type JobTypeStats,
} from '@/features/backgroundJobs/backgroundJobsApi'
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  Activity,
  Users,
  Server,
  Info,
} from 'lucide-react'

// `detail` is not always a string: create_http_exception sends
// { detail, detail_code }, which is what a 403 from the super-admin guard
// returns. Rendering that object directly would crash the error branch.
const apiErrorDetail = (error: unknown): string | undefined => {
  const detail = (error as { data?: { detail?: string | { detail?: string } } } | undefined)
    ?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail.detail === 'string') return detail.detail
  return undefined
}

export function BackgroundJobsPage() {
  const { t } = useTranslation('admin')
  const [autoRefresh, setAutoRefresh] = useState(false)

  const {
    data: statsData,
    isLoading: isStatsLoading,
    isFetching: isStatsFetching,
    isError: isStatsError,
    error: statsError,
    refetch: refetchStats,
  } = useGetBackgroundJobsStatsQuery(undefined, {
    pollingInterval: autoRefresh ? 10000 : 0,
  })

  const {
    data: healthData,
    isLoading: isHealthLoading,
    isFetching: isHealthFetching,
    isError: isHealthError,
    error: healthError,
    refetch: refetchHealth,
  } = useGetQueueHealthQuery(undefined, {
    pollingInterval: autoRefresh ? 10000 : 0,
  })

  const [toggleJobType] = useToggleJobTypeMutation()

  useEffect(() => {
    refetchStats()
    refetchHealth()
  }, [refetchStats, refetchHealth])

  const handleRefresh = () => {
    refetchStats()
    refetchHealth()
  }

  const handleToggle = async (jobType: string, currentEnabled: boolean) => {
    try {
      await toggleJobType({
        jobType,
        body: { enabled: !currentEnabled },
      }).unwrap()
      toast.success(
        !currentEnabled
          ? t('backgroundJobs.toast.enableSuccess')
          : t('backgroundJobs.toast.disableSuccess')
      )
    } catch {
      toast.error(t('backgroundJobs.toast.toggleError'))
    }
  }

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${Math.round(ms)}ms`
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
    return `${(ms / 60000).toFixed(1)}m`
  }

  const formatLastExecution = (isoString: string | null) => {
    if (!isoString) return t('backgroundJobs.status.never')
    const date = new Date(isoString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)

    if (diffMins < 1) return t('backgroundJobs.time.justNow')
    if (diffMins < 60) return t('backgroundJobs.time.minsAgo', { count: diffMins })
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24)
      return t('backgroundJobs.time.hoursAgo', { count: diffHours })
    return date.toLocaleDateString()
  }

  const getFailureRateColor = (rate: number) => {
    if (rate >= 10) return 'text-destructive'
    if (rate >= 5) return 'text-yellow-600 dark:text-yellow-400'
    return 'text-green-600 dark:text-green-400'
  }

  const getCategoryLabel = (category: string) => {
    return t(`backgroundJobs.categories.${category}`, { defaultValue: category })
  }

  const isLoading = isStatsLoading || isHealthLoading
  const isFetching = isStatsFetching || isHealthFetching

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('backgroundJobs.pageTitle')}
          description={t('backgroundJobs.pageDescription')}
        />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <CardSkeleton key={i} variant="stats" />
          ))}
        </div>
        <CardSkeleton />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('backgroundJobs.pageTitle')}
        description={t('backgroundJobs.pageDescription')}
      >
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Switch
              id="auto-refresh"
              checked={autoRefresh}
              onCheckedChange={setAutoRefresh}
            />
            <Label htmlFor="auto-refresh">{t('backgroundJobs.autoRefresh')}</Label>
          </div>
          <Button variant="outline" onClick={handleRefresh} disabled={isFetching}>
            {isFetching ? t('backgroundJobs.refreshing') : t('backgroundJobs.refresh')}
          </Button>
        </div>
      </PageHeader>

      {/* Queue Health Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            {t('backgroundJobs.queueHealth.title')}
          </CardTitle>
          <CardDescription>
            {t('backgroundJobs.queueHealth.description')}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isHealthError ? (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertTitle>{t('backgroundJobs.errors.queueHealthTitle')}</AlertTitle>
              <AlertDescription>
                {apiErrorDetail(healthError) ?? t('backgroundJobs.errors.unknown')}
              </AlertDescription>
            </Alert>
          ) : healthData ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <Badge
                  variant={healthData.is_healthy ? 'default' : 'destructive'}
                  className="text-sm"
                >
                  {healthData.is_healthy ? (
                    <>
                      <CheckCircle2 className="h-4 w-4 mr-1" />
                      {t('backgroundJobs.queueHealth.healthy')}
                    </>
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 mr-1" />
                      {t('backgroundJobs.queueHealth.unhealthy')}
                    </>
                  )}
                </Badge>
                {healthData.issues.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {healthData.issues.map((issue, idx) => (
                      <Badge key={idx} variant="outline" className="text-yellow-600">
                        <AlertTriangle className="h-3 w-3 mr-1" />
                        {issue}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid gap-4 md:grid-cols-4">
                <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                  <Server className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <p className="text-2xl font-bold">{healthData.workers_online}</p>
                    <p className="text-sm text-muted-foreground">
                      {t('backgroundJobs.queueHealth.workersOnline')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                  <Clock className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <p className="text-2xl font-bold">{healthData.queue_depth}</p>
                    <p className="text-sm text-muted-foreground">
                      {t('backgroundJobs.queueHealth.queueDepth')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                  <AlertTriangle className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <p
                      className={`text-2xl font-bold ${
                        healthData.stuck_jobs_count > 0
                          ? 'text-destructive'
                          : 'text-green-600 dark:text-green-400'
                      }`}
                    >
                      {healthData.stuck_jobs_count}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {t('backgroundJobs.queueHealth.stuckJobs')}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                  <Users className="h-8 w-8 text-muted-foreground" />
                  <div>
                    <p className="text-2xl font-bold">{healthData.total_workers}</p>
                    <p className="text-sm text-muted-foreground">
                      {t('backgroundJobs.queueHealth.totalWorkers')}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-muted-foreground">
              {t('backgroundJobs.queueHealth.unavailable')}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Summary Stats */}
      {statsData && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {t('backgroundJobs.summary.totalExecutions')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold">
                {statsData.total_executions_24h.toLocaleString()}
              </p>
              <p className="text-sm text-muted-foreground">
                {t('backgroundJobs.summary.last24Hours')}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">
                {t('backgroundJobs.summary.totalFailures')}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p
                className={`text-3xl font-bold ${
                  statsData.total_failures_24h > 0 ? 'text-destructive' : ''
                }`}
              >
                {statsData.total_failures_24h.toLocaleString()}
              </p>
              <p className="text-sm text-muted-foreground">
                {t('backgroundJobs.summary.last24Hours')}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Job Types Table */}
      <Card>
        <CardHeader>
          <CardTitle>{t('backgroundJobs.jobTypes.title')}</CardTitle>
          <CardDescription>{t('backgroundJobs.jobTypes.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          {isStatsError ? (
            <Alert variant="destructive">
              <XCircle className="h-4 w-4" />
              <AlertTitle>{t('backgroundJobs.errors.statsTitle')}</AlertTitle>
              <AlertDescription>
                {apiErrorDetail(statsError) ?? t('backgroundJobs.errors.unknown')}
              </AlertDescription>
            </Alert>
          ) : statsData && statsData.job_stats.length > 0 ? (
            <TooltipProvider>
              <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('backgroundJobs.table.jobType')}</TableHead>
                    <TableHead>{t('backgroundJobs.table.category')}</TableHead>
                    <TableHead className="text-right">
                      {t('backgroundJobs.table.executions')}
                    </TableHead>
                    <TableHead className="text-right">
                      {t('backgroundJobs.table.failures')}
                    </TableHead>
                    <TableHead className="text-right">
                      {t('backgroundJobs.table.failureRate')}
                    </TableHead>
                    <TableHead className="text-right">
                      {t('backgroundJobs.table.avgDuration')}
                    </TableHead>
                    <TableHead>{t('backgroundJobs.table.lastExecution')}</TableHead>
                    <TableHead>{t('backgroundJobs.table.status')}</TableHead>
                    <TableHead className="text-right">
                      {t('backgroundJobs.table.actions')}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {statsData.job_stats.map((job: JobTypeStats) => (
                    <TableRow key={job.job_type}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{job.name}</span>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                            </TooltipTrigger>
                            <TooltipContent>
                              <p className="max-w-xs">{job.description}</p>
                              <p className="text-xs text-muted-foreground mt-1">
                                {job.job_type}
                              </p>
                            </TooltipContent>
                          </Tooltip>
                          {job.is_cron && (
                            <Badge variant="outline" className="text-xs">
                              {t('backgroundJobs.badge.cron')}
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">
                          {getCategoryLabel(job.category)}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {job.executions_24h.toLocaleString()}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        <span
                          className={
                            job.failures_24h > 0 ? 'text-destructive' : ''
                          }
                        >
                          {job.failures_24h.toLocaleString()}
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        <span className={getFailureRateColor(job.failure_rate)}>
                          {job.failure_rate.toFixed(1)}%
                        </span>
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {formatDuration(job.avg_duration_ms)}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatLastExecution(job.last_execution)}
                      </TableCell>
                      <TableCell>
                        <Badge variant={job.enabled ? 'default' : 'secondary'}>
                          {job.enabled
                            ? t('backgroundJobs.status.enabled')
                            : t('backgroundJobs.status.disabled')}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Switch
                          checked={job.enabled}
                          onCheckedChange={() =>
                            handleToggle(job.job_type, job.enabled)
                          }
                        />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              </div>
            </TooltipProvider>
          ) : (
            <p className="text-center text-muted-foreground py-8">
              {t('backgroundJobs.emptyMessage')}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
