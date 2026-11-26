import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Search } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
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
import { Label } from '@/components/ui/label'
import { DatePicker } from '@/components/ui/date-picker'
import {
  useGetAuditLogsQuery,
  type AuditLog,
} from '@/features/auditLogs/auditLogsApi'

export function AuditLogsPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const [filters, setFilters] = useState({
    resourceType: '',
    action: '',
    dateFrom: '',
    dateTo: '',
    search: '',
  })

  const { data, isLoading } = useGetAuditLogsQuery({
    resource_type: filters.resourceType || undefined,
    action: filters.action || undefined,
    created_time_gte: filters.dateFrom || undefined,
    created_time_lte: filters.dateTo || undefined,
    q: filters.search || undefined,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [selectedLog, setSelectedLog] = useState<AuditLog | null>(null)

  const getActionColor = (action: string) => {
    switch (action.toUpperCase()) {
      case 'CREATE':
        return 'default'
      case 'UPDATE':
        return 'secondary'
      case 'DELETE':
        return 'destructive'
      default:
        return 'outline'
    }
  }

  const columns: Column<AuditLog>[] = [
    {
      key: 'timestamp',
      header: t('auditLogs.table.timestamp'),
      cell: (log) => new Date(log.created_time).toLocaleString(),
    },
    {
      key: 'actor',
      header: t('auditLogs.table.actor'),
      cell: (log) => log.actor_email || (log.actor_id ? log.actor_id.slice(0, 8) + '...' : 'System'),
    },
    {
      key: 'action',
      header: t('auditLogs.table.action'),
      cell: (log) => (
        <Badge variant={getActionColor(log.action) as 'default' | 'secondary' | 'destructive' | 'outline'}>
          {log.action}
        </Badge>
      ),
    },
    {
      key: 'resource',
      header: t('auditLogs.table.resource'),
      cell: (log) => (
        <span>
          {log.resource_type}
          <span className="text-muted-foreground text-xs ml-1">
            ({log.resource_name || log.resource_id.slice(0, 8) + '...'})
          </span>
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[100px]',
      cell: (log) => (
        <Button variant="ghost" size="sm" onClick={() => setSelectedLog(log)}>
          {t('auditLogs.table.viewDetails')}
        </Button>
      ),
    },
  ]

  const clearFilters = () => {
    setFilters({
      resourceType: '',
      action: '',
      dateFrom: '',
      dateTo: '',
      search: '',
    })
    setPage(1)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('auditLogs.pageTitle')}
        description={t('auditLogs.pageDescription')}
      />

      {/* Filters */}
      <div className="flex flex-wrap gap-4 items-end">
        <div className="space-y-1">
          <Label>{t('auditLogs.filters.search')}</Label>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('auditLogs.filters.searchPlaceholder')}
              value={filters.search}
              onChange={(e) => {
                setFilters((f) => ({ ...f, search: e.target.value }))
                setPage(1)
              }}
              className="pl-8 w-full sm:w-[200px]"
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label>{t('auditLogs.filters.resourceType')}</Label>
          <Select
            value={filters.resourceType}
            onValueChange={(value) =>
              setFilters((f) => ({ ...f, resourceType: value === 'all' ? '' : value }))
            }
          >
            <SelectTrigger className="w-full sm:w-[150px]">
              <SelectValue placeholder={t('auditLogs.filters.all')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('auditLogs.filters.all')}</SelectItem>
              <SelectItem value="User">{t('auditLogs.filters.user')}</SelectItem>
              <SelectItem value="Role">{t('auditLogs.filters.role')}</SelectItem>
              <SelectItem value="Organization">{t('auditLogs.filters.organization')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label>{t('auditLogs.filters.action')}</Label>
          <Select
            value={filters.action}
            onValueChange={(value) =>
              setFilters((f) => ({ ...f, action: value === 'all' ? '' : value }))
            }
          >
            <SelectTrigger className="w-full sm:w-[120px]">
              <SelectValue placeholder={t('auditLogs.filters.all')} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t('auditLogs.filters.all')}</SelectItem>
              <SelectItem value="CREATE">{t('auditLogs.filters.create')}</SelectItem>
              <SelectItem value="UPDATE">{t('auditLogs.filters.update')}</SelectItem>
              <SelectItem value="DELETE">{t('auditLogs.filters.delete')}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label>{t('auditLogs.filters.fromDate')}</Label>
          <DatePicker
            value={filters.dateFrom || undefined}
            onChange={(value) => setFilters((f) => ({ ...f, dateFrom: value || '' }))}
            placeholder={t('auditLogs.filters.fromDate')}
            maxDate={filters.dateTo ? new Date(filters.dateTo) : undefined}
            className="w-full sm:w-[180px]"
          />
        </div>

        <div className="space-y-1">
          <Label>{t('auditLogs.filters.toDate')}</Label>
          <DatePicker
            value={filters.dateTo || undefined}
            onChange={(value) => setFilters((f) => ({ ...f, dateTo: value || '' }))}
            placeholder={t('auditLogs.filters.toDate')}
            minDate={filters.dateFrom ? new Date(filters.dateFrom) : undefined}
            className="w-full sm:w-[180px]"
          />
        </div>

        <Button variant="outline" onClick={clearFilters}>
          {t('auditLogs.filters.clearFilters')}
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('auditLogs.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Details Dialog */}
      <Dialog open={!!selectedLog} onOpenChange={() => setSelectedLog(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('auditLogs.detailsDialog.title')}</DialogTitle>
            <DialogDescription>
              {selectedLog && new Date(selectedLog.created_time).toLocaleString()}
            </DialogDescription>
          </DialogHeader>

          {selectedLog && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('auditLogs.detailsDialog.actor')}
                  </p>
                  <p className="text-sm">{selectedLog.actor_email || 'System'}</p>
                  {selectedLog.actor_id && (
                    <p className="font-mono text-xs text-muted-foreground">{selectedLog.actor_id}</p>
                  )}
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('auditLogs.detailsDialog.action')}
                  </p>
                  <Badge variant={getActionColor(selectedLog.action) as 'default' | 'secondary' | 'destructive' | 'outline'}>
                    {selectedLog.action}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('auditLogs.detailsDialog.resourceType')}
                  </p>
                  <p>{selectedLog.resource_type}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">
                    {t('auditLogs.detailsDialog.resourceId')}
                  </p>
                  <p className="text-sm">{selectedLog.resource_name || selectedLog.resource_id}</p>
                  {selectedLog.resource_name && (
                    <p className="font-mono text-xs text-muted-foreground">{selectedLog.resource_id}</p>
                  )}
                </div>
              </div>

              {selectedLog.changes && Object.keys(selectedLog.changes).length > 0 && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">
                    {t('auditLogs.detailsDialog.changes')}
                  </p>
                  <div className="rounded-md border p-4 bg-muted/50">
                    <ScrollArea className="max-h-60">
                      <pre className="text-sm">
                        {JSON.stringify(selectedLog.changes, null, 2)}
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
