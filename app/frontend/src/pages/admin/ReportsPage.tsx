import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, Plus, Trash2, Calendar, Clock, RefreshCw, AlertCircle, CheckCircle2 } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from '@/lib/toast'
import { safeOpenDownloadUrl } from '@/lib/url-validation'
import {
  useGetReportTypesQuery,
  useGetReportsQuery,
  useCreateReportMutation,
  useDeleteReportMutation,
  useGetReportSchedulesQuery,
  useCreateReportScheduleMutation,
  useUpdateReportScheduleMutation,
  useDeleteReportScheduleMutation,
  type Report,
  type ReportSchedule,
} from '@/features/reports/reportsApi'

export function ReportsPage() {
  const { t } = useTranslation('admin')

  // State
  const [reportsPage, setReportsPage] = useState(1)
  const [schedulesPage, setSchedulesPage] = useState(1)
  const pageSize = 20

  const [createReportOpen, setCreateReportOpen] = useState(false)
  const [createScheduleOpen, setCreateScheduleOpen] = useState(false)
  const [deleteReportId, setDeleteReportId] = useState<string | null>(null)
  const [deleteScheduleId, setDeleteScheduleId] = useState<string | null>(null)

  // Form state
  const [reportForm, setReportForm] = useState({
    report_type: '',
    name: '',
    description: '',
  })
  const [scheduleForm, setScheduleForm] = useState({
    report_type: '',
    name: '',
    description: '',
    schedule_expression: '',
    recipients: '',
  })

  // Queries
  const { data: reportTypes } = useGetReportTypesQuery()
  const { data: reportsData, isLoading: reportsLoading, refetch: refetchReports } = useGetReportsQuery({
    limit: pageSize,
    offset: (reportsPage - 1) * pageSize,
    sort: 'created_time:desc',
  })
  const { data: schedulesData, isLoading: schedulesLoading } = useGetReportSchedulesQuery({
    limit: pageSize,
    offset: (schedulesPage - 1) * pageSize,
    sort: 'created_time:desc',
  })

  // Mutations
  const [createReport, { isLoading: creating }] = useCreateReportMutation()
  const [deleteReport] = useDeleteReportMutation()
  const [createSchedule, { isLoading: creatingSchedule }] = useCreateReportScheduleMutation()
  const [updateSchedule] = useUpdateReportScheduleMutation()
  const [deleteSchedule] = useDeleteReportScheduleMutation()

  // Handlers
  const handleCreateReport = async () => {
    try {
      await createReport({
        report_type: reportForm.report_type,
        name: reportForm.name,
        description: reportForm.description || undefined,
      }).unwrap()
      toast.success(t('reports.toast.generateSuccess'))
      setCreateReportOpen(false)
      setReportForm({ report_type: '', name: '', description: '' })
    } catch {
      toast.error(t('reports.toast.generateError'))
    }
  }

  const handleDeleteReport = async () => {
    if (!deleteReportId) return
    try {
      await deleteReport(deleteReportId).unwrap()
      toast.success(t('reports.toast.deleteSuccess'))
      setDeleteReportId(null)
    } catch {
      toast.error(t('reports.toast.deleteError'))
    }
  }

  const handleCreateSchedule = async () => {
    const recipients = scheduleForm.recipients.split(',').map(e => e.trim()).filter(Boolean)
    if (recipients.length === 0) {
      toast.error(t('reports.validation.recipientsRequired'))
      return
    }
    try {
      await createSchedule({
        report_type: scheduleForm.report_type,
        name: scheduleForm.name,
        description: scheduleForm.description || undefined,
        schedule_expression: scheduleForm.schedule_expression,
        recipients,
      }).unwrap()
      toast.success(t('reports.toast.scheduleCreateSuccess'))
      setCreateScheduleOpen(false)
      setScheduleForm({ report_type: '', name: '', description: '', schedule_expression: '', recipients: '' })
    } catch {
      toast.error(t('reports.toast.scheduleCreateError'))
    }
  }

  const handleToggleSchedule = async (schedule: ReportSchedule) => {
    try {
      await updateSchedule({
        id: schedule.id,
        data: { is_active: !schedule.is_active },
      }).unwrap()
      toast.success(schedule.is_active ? t('reports.toast.scheduleDeactivateSuccess') : t('reports.toast.scheduleActivateSuccess'))
    } catch {
      toast.error(t('reports.toast.scheduleToggleError'))
    }
  }

  const handleDeleteSchedule = async () => {
    if (!deleteScheduleId) return
    try {
      await deleteSchedule(deleteScheduleId).unwrap()
      toast.success(t('reports.toast.scheduleDeleteSuccess'))
      setDeleteScheduleId(null)
    } catch {
      toast.error(t('reports.toast.scheduleDeleteError'))
    }
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="default" className="bg-green-500"><CheckCircle2 className="w-3 h-3 mr-1" />{t('reports.status.completed')}</Badge>
      case 'processing':
        return <Badge variant="secondary"><RefreshCw className="w-3 h-3 mr-1 animate-spin" />{t('reports.status.processing')}</Badge>
      case 'pending':
        return <Badge variant="outline"><Clock className="w-3 h-3 mr-1" />{t('reports.status.pending')}</Badge>
      case 'failed':
        return <Badge variant="destructive"><AlertCircle className="w-3 h-3 mr-1" />{t('reports.status.failed')}</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  const reportColumns: Column<Report>[] = [
    {
      key: 'name',
      header: t('reports.table.name'),
      cell: (report) => (
        <div>
          <div className="font-medium">{report.name}</div>
          <div className="text-sm text-muted-foreground">{report.report_type}</div>
        </div>
      ),
    },
    {
      key: 'status',
      header: t('reports.table.status'),
      cell: (report) => getStatusBadge(report.status),
    },
    {
      key: 'rows',
      header: t('reports.table.rows'),
      cell: (report) => report.row_count?.toLocaleString() ?? '-',
    },
    {
      key: 'created',
      header: t('reports.table.created'),
      cell: (report) => new Date(report.created_time).toLocaleString(),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[120px]',
      cell: (report) => (
        <div className="flex gap-2">
          {report.status === 'completed' && report.download_url && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => {
                // SEC-F-011: Validate URL before opening
                if (!safeOpenDownloadUrl(report.download_url!)) {
                  toast.error('Invalid download URL')
                }
              }}
            >
              <Download className="h-4 w-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" onClick={() => setDeleteReportId(report.id)}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ]

  const scheduleColumns: Column<ReportSchedule>[] = [
    {
      key: 'name',
      header: t('reports.table.name'),
      cell: (schedule) => (
        <div>
          <div className="font-medium">{schedule.name}</div>
          <div className="text-sm text-muted-foreground">{schedule.report_type}</div>
        </div>
      ),
    },
    {
      key: 'schedule',
      header: t('reports.table.schedule'),
      cell: (schedule) => (
        <code className="text-sm bg-muted px-2 py-1 rounded">{schedule.schedule_expression}</code>
      ),
    },
    {
      key: 'status',
      header: t('reports.table.status'),
      cell: (schedule) => (
        <Badge variant={schedule.is_active ? 'default' : 'secondary'}>
          {schedule.is_active ? t('reports.table.active') : t('reports.status.pending')}
        </Badge>
      ),
    },
    {
      key: 'nextRun',
      header: t('reports.table.nextRun'),
      cell: (schedule) => schedule.next_run_time ? new Date(schedule.next_run_time).toLocaleString() : '-',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[150px]',
      cell: (schedule) => (
        <div className="flex gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleToggleSchedule(schedule)}
          >
            {schedule.is_active ? t('reports.actions.deactivate') : t('reports.actions.activate')}
          </Button>
          <Button variant="ghost" size="icon" onClick={() => setDeleteScheduleId(schedule.id)}>
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('reports.pageTitle')}
        description={t('reports.pageDescription')}
      />

      <Tabs defaultValue="reports">
        <TabsList>
          <TabsTrigger value="reports">{t('reports.tabs.reports')}</TabsTrigger>
          <TabsTrigger value="schedules">{t('reports.tabs.schedules')}</TabsTrigger>
        </TabsList>

        <TabsContent value="reports" className="space-y-4">
          <div className="flex justify-between items-center">
            <Button variant="outline" size="sm" onClick={() => refetchReports()}>
              <RefreshCw className="h-4 w-4 mr-2" />
              {t('common.refresh', { defaultValue: 'Refresh' })}
            </Button>
            <Button onClick={() => setCreateReportOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              {t('reports.generateButton')}
            </Button>
          </div>

          <DataTable
            columns={reportColumns}
            data={reportsData?.items || []}
            isLoading={reportsLoading}
            pagination={{
              page: reportsPage,
              pageSize: pageSize,
              total: reportsData?.total || 0,
              onPageChange: setReportsPage,
            }}
            emptyMessage={t('reports.emptyMessage')}
          />
        </TabsContent>

        <TabsContent value="schedules" className="space-y-4">
          <div className="flex justify-end">
            <Button onClick={() => setCreateScheduleOpen(true)}>
              <Calendar className="h-4 w-4 mr-2" />
              {t('reports.createScheduleButton')}
            </Button>
          </div>

          <DataTable
            columns={scheduleColumns}
            data={schedulesData?.items || []}
            isLoading={schedulesLoading}
            pagination={{
              page: schedulesPage,
              pageSize: pageSize,
              total: schedulesData?.total || 0,
              onPageChange: setSchedulesPage,
            }}
            emptyMessage={t('reports.emptyScheduleMessage')}
          />
        </TabsContent>
      </Tabs>

      {/* Create Report Dialog */}
      <Dialog open={createReportOpen} onOpenChange={setCreateReportOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('reports.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('reports.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="report-type">{t('reports.createDialog.reportType')}</Label>
              <Select
                value={reportForm.report_type}
                onValueChange={(v) => setReportForm(f => ({ ...f, report_type: v }))}
              >
                <SelectTrigger id="report-type">
                  <SelectValue placeholder={t('reports.createDialog.reportTypePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {reportTypes?.items.map(type => (
                    <SelectItem key={type.code} value={type.code}>
                      {type.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="report-name">{t('reports.createDialog.name')}</Label>
              <Input
                id="report-name"
                value={reportForm.name}
                onChange={(e) => setReportForm(f => ({ ...f, name: e.target.value }))}
                placeholder={t('reports.createDialog.namePlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="report-description">{t('reports.createDialog.descriptionLabel')}</Label>
              <Textarea
                id="report-description"
                value={reportForm.description}
                onChange={(e) => setReportForm(f => ({ ...f, description: e.target.value }))}
                placeholder={t('reports.createDialog.descriptionPlaceholder')}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateReportOpen(false)}>
              {t('reports.createDialog.cancel')}
            </Button>
            <Button
              onClick={handleCreateReport}
              disabled={creating || !reportForm.report_type || !reportForm.name}
            >
              {creating ? t('reports.createDialog.generating') : t('reports.createDialog.generate')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Schedule Dialog */}
      <Dialog open={createScheduleOpen} onOpenChange={setCreateScheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('reports.createScheduleDialog.title')}</DialogTitle>
            <DialogDescription>{t('reports.createScheduleDialog.description')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="schedule-report-type">{t('reports.createScheduleDialog.reportType')}</Label>
              <Select
                value={scheduleForm.report_type}
                onValueChange={(v) => setScheduleForm(f => ({ ...f, report_type: v }))}
              >
                <SelectTrigger id="schedule-report-type">
                  <SelectValue placeholder={t('reports.createScheduleDialog.reportTypePlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  {reportTypes?.items.map(type => (
                    <SelectItem key={type.code} value={type.code}>
                      {type.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-name">{t('reports.createScheduleDialog.name')}</Label>
              <Input
                id="schedule-name"
                value={scheduleForm.name}
                onChange={(e) => setScheduleForm(f => ({ ...f, name: e.target.value }))}
                placeholder={t('reports.createScheduleDialog.namePlaceholder')}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-expression">{t('reports.createScheduleDialog.scheduleExpression')}</Label>
              <Input
                id="schedule-expression"
                value={scheduleForm.schedule_expression}
                onChange={(e) => setScheduleForm(f => ({ ...f, schedule_expression: e.target.value }))}
                placeholder={t('reports.createScheduleDialog.scheduleExpressionPlaceholder')}
              />
              <p className="text-sm text-muted-foreground">{t('reports.createScheduleDialog.scheduleExpressionDescription')}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="schedule-recipients">{t('reports.createScheduleDialog.recipients')}</Label>
              <Textarea
                id="schedule-recipients"
                value={scheduleForm.recipients}
                onChange={(e) => setScheduleForm(f => ({ ...f, recipients: e.target.value }))}
                placeholder={t('reports.createScheduleDialog.recipientsPlaceholder')}
              />
              <p className="text-sm text-muted-foreground">{t('reports.createScheduleDialog.recipientsDescription')}</p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateScheduleOpen(false)}>
              {t('reports.createScheduleDialog.cancel')}
            </Button>
            <Button
              onClick={handleCreateSchedule}
              disabled={creatingSchedule || !scheduleForm.report_type || !scheduleForm.name || !scheduleForm.schedule_expression || !scheduleForm.recipients}
            >
              {creatingSchedule ? t('reports.createScheduleDialog.creating') : t('reports.createScheduleDialog.create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Report Confirmation */}
      <AlertDialog open={!!deleteReportId} onOpenChange={() => setDeleteReportId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('reports.deleteDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('reports.deleteDialog.description', {
                name: reportsData?.items.find(r => r.id === deleteReportId)?.name ?? ''
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteReport}>{t('reports.deleteDialog.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Schedule Confirmation */}
      <AlertDialog open={!!deleteScheduleId} onOpenChange={() => setDeleteScheduleId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('reports.deleteScheduleDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('reports.deleteScheduleDialog.description', {
                name: schedulesData?.items.find(s => s.id === deleteScheduleId)?.name ?? ''
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteSchedule}>{t('reports.deleteScheduleDialog.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
