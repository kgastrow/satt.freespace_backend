import { useState, useEffect, useRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DatePicker } from '@/components/ui/date-picker'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { toast } from '@/lib/toast'
import { Trash2, Settings } from 'lucide-react'
import {
  useGetRequestLogsQuery,
  useTriggerLogCleanupMutation,
  useGetRequestLoggingConfigQuery,
  useUpdateRequestLoggingConfigMutation,
  type RequestLog,
} from '@/features/requestLogs/requestLogsApi'

export function RequestLogsPage() {
  const { t } = useTranslation('admin')
  const pageSize = 50

  // Cursor-based pagination: store history of cursors for back navigation
  const [cursorHistory, setCursorHistory] = useState<string[]>([])
  const [currentCursor, setCurrentCursor] = useState<string | undefined>(undefined)

  const [filters, setFilters] = useState({
    method: '',
    path: '',
    statusCodeMin: '',
    statusCodeMax: '',
    dateFrom: '',
    dateTo: '',
    userEmail: '',
  })

  const { data, isLoading } = useGetRequestLogsQuery({
    method: filters.method || undefined,
    path: filters.path || undefined,
    status_code_min: filters.statusCodeMin ? parseInt(filters.statusCodeMin, 10) : undefined,
    status_code_max: filters.statusCodeMax ? parseInt(filters.statusCodeMax, 10) : undefined,
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
    user_email: filters.userEmail || undefined,
    limit: pageSize,
    cursor: currentCursor,
  })

  // Navigation functions
  const goToNextPage = () => {
    if (data?.next_cursor) {
      setCursorHistory((prev) => [...prev, currentCursor || ''])
      setCurrentCursor(data.next_cursor)
    }
  }

  const goToPrevPage = () => {
    if (cursorHistory.length > 0) {
      const newHistory = [...cursorHistory]
      const prevCursor = newHistory.pop()
      setCursorHistory(newHistory)
      setCurrentCursor(prevCursor || undefined)
    }
  }

  const goToFirstPage = () => {
    setCursorHistory([])
    setCurrentCursor(undefined)
  }

  const [triggerCleanup, { isLoading: isCleaningUp }] = useTriggerLogCleanupMutation()

  // Config state and API
  const { data: configData, isLoading: isLoadingConfig } = useGetRequestLoggingConfigQuery()
  const [updateConfig, { isLoading: isUpdatingConfig }] = useUpdateRequestLoggingConfigMutation()

  // Initialize form state from config data using useMemo
  const initialConfigForm = useMemo(
    () => ({
      enabled: configData?.enabled ?? false,
      db_enabled: configData?.db_enabled ?? false,
      max_body_size: configData?.max_body_size ?? 10240,
      retention_days: configData?.retention_days ?? 30,
    }),
    [configData]
  )

  const [configForm, setConfigForm] = useState(initialConfigForm)

  // Update form when initial config changes (only on first load)
  const hasInitializedRef = useRef(false)
  useEffect(() => {
    if (configData && !hasInitializedRef.current) {
      // Schedule state update to avoid cascading renders
      const timer = setTimeout(() => {
        setConfigForm({
          enabled: configData.enabled,
          db_enabled: configData.db_enabled,
          max_body_size: configData.max_body_size,
          retention_days: configData.retention_days,
        })
        hasInitializedRef.current = true
      }, 0)
      return () => clearTimeout(timer)
    }
  }, [configData])

  const handleSaveConfig = async () => {
    try {
      await updateConfig(configForm).unwrap()
      toast.success(t('requestLogs.settings.saveSuccess'))
    } catch {
      toast.error(t('requestLogs.settings.saveError'))
    }
  }

  const [selectedLog, setSelectedLog] = useState<RequestLog | null>(null)

  const getStatusColor = (statusCode: number) => {
    if (statusCode >= 200 && statusCode < 300) return 'default'
    if (statusCode >= 300 && statusCode < 400) return 'secondary'
    if (statusCode >= 400 && statusCode < 500) return 'outline'
    return 'destructive'
  }

  const getMethodColor = (method: string) => {
    switch (method.toUpperCase()) {
      case 'GET':
        return 'default'
      case 'POST':
        return 'secondary'
      case 'PUT':
      case 'PATCH':
        return 'outline'
      case 'DELETE':
        return 'destructive'
      default:
        return 'outline'
    }
  }

  const columns: Column<RequestLog>[] = [
    {
      key: 'timestamp',
      header: t('requestLogs.table.timestamp'),
      cell: (log) => new Date(log.created_time).toLocaleString(),
    },
    {
      key: 'method',
      header: t('requestLogs.table.method'),
      cell: (log) => (
        <Badge
          variant={
            getMethodColor(log.method) as 'default' | 'secondary' | 'destructive' | 'outline'
          }
        >
          {log.method}
        </Badge>
      ),
    },
    {
      key: 'path',
      header: t('requestLogs.table.path'),
      cell: (log) => (
        <span className="font-mono text-sm truncate max-w-[300px] block" title={log.path}>
          {log.path}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('requestLogs.table.status'),
      cell: (log) => (
        <Badge
          variant={
            getStatusColor(log.status_code) as 'default' | 'secondary' | 'destructive' | 'outline'
          }
        >
          {log.status_code}
        </Badge>
      ),
    },
    {
      key: 'duration',
      header: t('requestLogs.table.duration'),
      cell: (log) => `${log.duration_ms}ms`,
    },
    {
      key: 'ip',
      header: t('requestLogs.table.ipAddress'),
      cell: (log) => (
        <span className="font-mono text-xs text-muted-foreground">{log.ip_address}</span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[100px]',
      cell: (log) => (
        <Button variant="ghost" size="sm" onClick={() => setSelectedLog(log)}>
          {t('requestLogs.table.viewDetails')}
        </Button>
      ),
    },
  ]

  const clearFilters = () => {
    setFilters({
      method: '',
      path: '',
      statusCodeMin: '',
      statusCodeMax: '',
      dateFrom: '',
      dateTo: '',
      userEmail: '',
    })
    // Reset cursor pagination
    setCursorHistory([])
    setCurrentCursor(undefined)
  }

  const handleCleanup = async () => {
    try {
      await triggerCleanup().unwrap()
      toast.success(t('requestLogs.toast.cleanupSuccess'))
    } catch {
      toast.error(t('requestLogs.toast.cleanupError'))
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('requestLogs.pageTitle')}
        description={t('requestLogs.pageDescription')}
      >
        <Button variant="outline" onClick={handleCleanup} disabled={isCleaningUp}>
          <Trash2 className="h-4 w-4 mr-2" />
          {isCleaningUp ? t('requestLogs.cleaningUp') : t('requestLogs.triggerCleanup')}
        </Button>
      </PageHeader>

      {/* Settings Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            {t('requestLogs.settings.title')}
          </CardTitle>
          <CardDescription>{t('requestLogs.settings.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoadingConfig ? (
            <div className="space-y-4">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="flex items-center justify-between space-x-4">
                  <div className="space-y-0.5">
                    <Label htmlFor="enabled">{t('requestLogs.settings.enabled.label')}</Label>
                    <p className="text-sm text-muted-foreground">
                      {t('requestLogs.settings.enabled.description')}
                    </p>
                  </div>
                  <Switch
                    id="enabled"
                    checked={configForm.enabled}
                    onCheckedChange={(checked) =>
                      setConfigForm((f) => ({ ...f, enabled: checked }))
                    }
                  />
                </div>

                <div className="flex items-center justify-between space-x-4">
                  <div className="space-y-0.5">
                    <Label htmlFor="db_enabled">{t('requestLogs.settings.dbEnabled.label')}</Label>
                    <p className="text-sm text-muted-foreground">
                      {t('requestLogs.settings.dbEnabled.description')}
                    </p>
                  </div>
                  <Switch
                    id="db_enabled"
                    checked={configForm.db_enabled}
                    onCheckedChange={(checked) =>
                      setConfigForm((f) => ({ ...f, db_enabled: checked }))
                    }
                    disabled={!configForm.enabled}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="max_body_size">
                    {t('requestLogs.settings.maxBodySize.label')}
                  </Label>
                  <Input
                    id="max_body_size"
                    type="number"
                    min={1024}
                    max={102400}
                    value={configForm.max_body_size}
                    onChange={(e) =>
                      setConfigForm((f) => ({
                        ...f,
                        max_body_size: parseInt(e.target.value, 10) || 10240,
                      }))
                    }
                    disabled={!configForm.enabled}
                  />
                  <p className="text-sm text-muted-foreground">
                    {t('requestLogs.settings.maxBodySize.description')}
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="retention_days">
                    {t('requestLogs.settings.retentionDays.label')}
                  </Label>
                  <Input
                    id="retention_days"
                    type="number"
                    min={1}
                    max={365}
                    value={configForm.retention_days}
                    onChange={(e) =>
                      setConfigForm((f) => ({
                        ...f,
                        retention_days: parseInt(e.target.value, 10) || 30,
                      }))
                    }
                  />
                  <p className="text-sm text-muted-foreground">
                    {t('requestLogs.settings.retentionDays.description')}
                  </p>
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={handleSaveConfig} disabled={isUpdatingConfig}>
                  {isUpdatingConfig
                    ? t('requestLogs.settings.saving')
                    : t('requestLogs.settings.saveButton')}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <Label>{t('requestLogs.filters.method')}</Label>
          <Select
            value={filters.method}
            onValueChange={(value) =>
              setFilters((f) => ({ ...f, method: value === 'all' ? '' : value }))
            }
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder={t('requestLogs.filters.all')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('requestLogs.filters.all')}</SelectItem>
              <SelectItem value="GET">GET</SelectItem>
              <SelectItem value="POST">POST</SelectItem>
              <SelectItem value="PUT">PUT</SelectItem>
              <SelectItem value="PATCH">PATCH</SelectItem>
              <SelectItem value="DELETE">DELETE</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label>{t('requestLogs.filters.path')}</Label>
          <Input
            type="text"
            value={filters.path}
            onChange={(e) => setFilters((f) => ({ ...f, path: e.target.value }))}
            placeholder={t('requestLogs.filters.pathPlaceholder')}
            className="w-[200px]"
          />
        </div>

        <div className="space-y-1">
          <Label>{t('requestLogs.filters.statusRange')}</Label>
          <div className="flex gap-2 items-center">
            <Input
              type="number"
              value={filters.statusCodeMin}
              onChange={(e) => setFilters((f) => ({ ...f, statusCodeMin: e.target.value }))}
              placeholder="200"
              className="w-[80px]"
              min={100}
              max={599}
            />
            <span className="text-muted-foreground">-</span>
            <Input
              type="number"
              value={filters.statusCodeMax}
              onChange={(e) => setFilters((f) => ({ ...f, statusCodeMax: e.target.value }))}
              placeholder="599"
              className="w-[80px]"
              min={100}
              max={599}
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label>{t('requestLogs.filters.fromDate')}</Label>
          <DatePicker
            value={filters.dateFrom || undefined}
            onChange={(value) => setFilters((f) => ({ ...f, dateFrom: value || '' }))}
            placeholder={t('requestLogs.filters.fromDate')}
            maxDate={filters.dateTo ? new Date(filters.dateTo) : undefined}
            className="w-[180px]"
          />
        </div>

        <div className="space-y-1">
          <Label>{t('requestLogs.filters.toDate')}</Label>
          <DatePicker
            value={filters.dateTo || undefined}
            onChange={(value) => setFilters((f) => ({ ...f, dateTo: value || '' }))}
            placeholder={t('requestLogs.filters.toDate')}
            minDate={filters.dateFrom ? new Date(filters.dateFrom) : undefined}
            className="w-[180px]"
          />
        </div>

        <div className="space-y-1">
          <Label>{t('requestLogs.filters.userEmail')}</Label>
          <Input
            type="email"
            value={filters.userEmail}
            onChange={(e) => setFilters((f) => ({ ...f, userEmail: e.target.value }))}
            placeholder={t('requestLogs.filters.userEmailPlaceholder')}
            className="w-[200px]"
          />
        </div>

        <Button variant="outline" onClick={clearFilters}>
          {t('requestLogs.filters.clearFilters')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('requestLogs.emptyMessage')}
      />

      {/* Cursor-based Pagination Controls */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          {t('requestLogs.pagination.showing', { count: data?.items?.length || 0 })}
          {cursorHistory.length > 0 && (
            <span className="ml-2">
              ({t('requestLogs.pagination.page', { page: cursorHistory.length + 1 })})
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={goToFirstPage}
            disabled={cursorHistory.length === 0}
          >
            {t('requestLogs.pagination.first')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={goToPrevPage}
            disabled={cursorHistory.length === 0}
          >
            {t('requestLogs.pagination.previous')}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={goToNextPage}
            disabled={!data?.has_more}
          >
            {t('requestLogs.pagination.next')}
          </Button>
        </div>
      </div>

      {/* Details Dialog */}
      <Dialog open={!!selectedLog} onOpenChange={() => setSelectedLog(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>{t('requestLogs.detailsDialog.title')}</DialogTitle>
            <DialogDescription>
              {selectedLog && new Date(selectedLog.created_time).toLocaleString()}
            </DialogDescription>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('requestLogs.detailsDialog.method')}
                  </p>
                  <Badge
                    variant={
                      getMethodColor(selectedLog.method) as
                        | 'default'
                        | 'secondary'
                        | 'destructive'
                        | 'outline'
                    }
                  >
                    {selectedLog.method}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('requestLogs.detailsDialog.statusCode')}
                  </p>
                  <Badge
                    variant={
                      getStatusColor(selectedLog.status_code) as
                        | 'default'
                        | 'secondary'
                        | 'destructive'
                        | 'outline'
                    }
                  >
                    {selectedLog.status_code}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('requestLogs.detailsDialog.duration')}
                  </p>
                  <p className="text-sm">{selectedLog.duration_ms}ms</p>
                </div>
                <div className="col-span-2 md:col-span-3">
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('requestLogs.detailsDialog.path')}
                  </p>
                  <p className="font-mono text-sm break-all">{selectedLog.path}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('requestLogs.detailsDialog.ipAddress')}
                  </p>
                  <p className="font-mono text-sm">{selectedLog.ip_address}</p>
                </div>
                {selectedLog.organization_id && (
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      {t('requestLogs.detailsDialog.organizationId')}
                    </p>
                    <p className="font-mono text-xs">{selectedLog.organization_id}</p>
                  </div>
                )}
                {selectedLog.user_id && (
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">
                      {t('requestLogs.detailsDialog.userId')}
                    </p>
                    <p className="font-mono text-xs">{selectedLog.user_id}</p>
                  </div>
                )}
              </div>

              <div>
                <p className="text-sm font-medium text-muted-foreground mb-2">
                  {t('requestLogs.detailsDialog.userAgent')}
                </p>
                <p className="text-xs text-muted-foreground break-all">{selectedLog.user_agent}</p>
              </div>

              {selectedLog.request_body && Object.keys(selectedLog.request_body).length > 0 && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">
                    {t('requestLogs.detailsDialog.requestBody')}
                  </p>
                  <div className="rounded-md border p-4 bg-muted/50">
                    <ScrollArea className="max-h-40">
                      <pre className="text-sm">
                        {JSON.stringify(selectedLog.request_body, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                </div>
              )}

              {selectedLog.response_body && Object.keys(selectedLog.response_body).length > 0 && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">
                    {t('requestLogs.detailsDialog.responseBody')}
                  </p>
                  <div className="rounded-md border p-4 bg-muted/50">
                    <ScrollArea className="max-h-40">
                      <pre className="text-sm">
                        {JSON.stringify(selectedLog.response_body, null, 2)}
                      </pre>
                    </ScrollArea>
                  </div>
                </div>
              )}

              {selectedLog.error_traceback && (
                <div>
                  <p className="text-sm font-medium text-destructive mb-2">
                    {t('requestLogs.detailsDialog.errorTraceback')}
                  </p>
                  <div className="rounded-md border border-destructive/50 p-4 bg-destructive/10">
                    <ScrollArea className="max-h-60">
                      <pre className="text-xs font-mono whitespace-pre-wrap text-destructive">
                        {selectedLog.error_traceback}
                      </pre>
                    </ScrollArea>
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
