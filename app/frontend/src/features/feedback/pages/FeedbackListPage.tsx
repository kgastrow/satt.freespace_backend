import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  useGetFeedbackListQuery,
  useDeleteFeedbackMutation,
  useUpdateFeedbackMutation,
} from '../feedbackApi'
import type { Feedback, FeedbackStatus, FeedbackType } from '../types'
import { FeedbackFilters } from '../components/FeedbackFilters'
import { FeedbackStatsCard } from '../components/FeedbackStatsCard'
import { MoreVertical, Trash2, Eye, CheckCircle, XCircle, Download, X, AlertCircle } from 'lucide-react'
import { usePermission } from '@/hooks/usePermission'
import { format } from 'date-fns'
import { useAppSelector } from '@/store/hooks'
import { useGetOrganizationsQuery } from '@/features/organizations/organizationsApi'

export function FeedbackListPage() {
  const { t } = useTranslation('feedback')
  const navigate = useNavigate()
  const { canDelete } = usePermission('feedback')
  const user = useAppSelector(state => state.auth.user)
  const [page, setPage] = useState(1)
  const pageSize = 20

  // Filter states
  const [typeFilter, setTypeFilter] = useState<FeedbackType | undefined>(undefined)
  const [statusFilter, setStatusFilter] = useState<FeedbackStatus | undefined>(undefined)
  const [ratingFilter, setRatingFilter] = useState<number | undefined>(undefined)
  const [dateFrom, setDateFrom] = useState<string | undefined>(undefined)
  const [dateTo, setDateTo] = useState<string | undefined>(undefined)
  const [organizationFilter, setOrganizationFilter] = useState<string | undefined>(undefined)

  // Fetch organizations only if user is super admin
  const { data: orgsData } = useGetOrganizationsQuery(
    { limit: 1000, offset: 0 },
    { skip: !user?.is_admin }
  )

  // Selection state
  const [selectedFeedback, setSelectedFeedback] = useState<Feedback[]>([])

  const { data, isLoading } = useGetFeedbackListQuery({
    'filter[type]': typeFilter,
    'filter[status]': statusFilter,
    'filter[rating][gte]': ratingFilter,
    'filter[created_time][gte]': dateFrom,
    'filter[created_time][lte]': dateTo,
    organization_id: organizationFilter,
    sort: 'created_time:desc',
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [deleteFeedback, { isLoading: isDeleting }] = useDeleteFeedbackMutation()
  const [updateFeedback] = useUpdateFeedbackMutation()
  const [deletingFeedback, setDeletingFeedback] = useState<Feedback | null>(null)

  const handleDelete = async () => {
    if (!deletingFeedback) return
    try {
      await deleteFeedback(deletingFeedback.id).unwrap()
      toast.success(t('admin.toast.deleteSuccess'))
      setDeletingFeedback(null)
    } catch {
      toast.error(t('admin.toast.deleteError'))
    }
  }

  const handleStatusChange = async (feedbackId: string, status: FeedbackStatus) => {
    try {
      await updateFeedback({ id: feedbackId, data: { status } }).unwrap()
      toast.success(t('admin.toast.statusUpdateSuccess'))
    } catch {
      toast.error(t('admin.toast.statusUpdateError'))
    }
  }

  // Bulk action handlers
  const handleBulkMarkResolved = async () => {
    if (selectedFeedback.length === 0) {
      toast.error(t('admin.bulkActions.noSelectionWarning'))
      return
    }

    try {
      await Promise.all(
        selectedFeedback.map(feedback =>
          updateFeedback({ id: feedback.id, data: { status: 'resolved' } }).unwrap()
        )
      )
      toast.success(t('admin.bulkActions.bulkResolvedSuccess', { count: selectedFeedback.length }))
      setSelectedFeedback([])
    } catch {
      toast.error(t('admin.bulkActions.bulkActionError'))
    }
  }

  const handleBulkDismiss = async () => {
    if (selectedFeedback.length === 0) {
      toast.error(t('admin.bulkActions.noSelectionWarning'))
      return
    }

    try {
      await Promise.all(
        selectedFeedback.map(feedback =>
          updateFeedback({ id: feedback.id, data: { status: 'dismissed' } }).unwrap()
        )
      )
      toast.success(t('admin.bulkActions.bulkDismissedSuccess', { count: selectedFeedback.length }))
      setSelectedFeedback([])
    } catch {
      toast.error(t('admin.bulkActions.bulkActionError'))
    }
  }

  const exportFeedbackToCSV = (feedbacks: Feedback[]) => {
    const headers = ['Type', 'Subject', 'Message', 'Rating', 'Status', 'Submitted Date']
    const rows = feedbacks.map(f => [
      f.type,
      `"${(f.subject || '').replace(/"/g, '""')}"`,
      `"${(f.message || '').replace(/"/g, '""')}"`,
      f.rating?.toString() || '',
      f.status,
      f.created_time ? format(new Date(f.created_time), 'yyyy-MM-dd HH:mm:ss') : '',
    ])

    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `feedback-export-${format(new Date(), 'yyyyMMdd-HHmmss')}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  const exportFeedbackToJSON = (feedbacks: Feedback[]) => {
    const json = JSON.stringify(feedbacks, null, 2)
    const blob = new Blob([json], { type: 'application/json;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `feedback-export-${format(new Date(), 'yyyyMMdd-HHmmss')}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  const handleExportCSV = () => {
    if (selectedFeedback.length === 0) {
      toast.error(t('admin.bulkActions.noSelectionWarning'))
      return
    }
    exportFeedbackToCSV(selectedFeedback)
    toast.success(t('admin.bulkActions.exportSuccess', { count: selectedFeedback.length }))
  }

  const handleExportJSON = () => {
    if (selectedFeedback.length === 0) {
      toast.error(t('admin.bulkActions.noSelectionWarning'))
      return
    }
    exportFeedbackToJSON(selectedFeedback)
    toast.success(t('admin.bulkActions.exportSuccess', { count: selectedFeedback.length }))
  }

  const getStatusBadgeVariant = (status: FeedbackStatus) => {
    switch (status) {
      case 'new':
        return 'default'
      case 'in_review':
        return 'secondary'
      case 'resolved':
        return 'outline'
      case 'dismissed':
        return 'destructive'
      default:
        return 'default'
    }
  }

  const getTypeBadgeVariant = (type: FeedbackType) => {
    switch (type) {
      case 'bug':
        return 'destructive'
      case 'suggestion':
        return 'default'
      case 'complaint':
        return 'secondary'
      case 'praise':
        return 'outline'
      case 'other':
        return 'outline'
      default:
        return 'default'
    }
  }

  const columns: Column<Feedback>[] = [
    {
      key: 'type',
      header: t('admin.table.columns.type'),
      cell: (feedback) => (
        <Badge variant={getTypeBadgeVariant(feedback.type)}>
          {t(`form.fields.type.options.${feedback.type}`)}
        </Badge>
      ),
    },
    {
      key: 'subject',
      header: t('admin.table.columns.subject'),
      cell: (feedback) => (
        <div className="flex items-center gap-2">
          {feedback.requires_attention && (
            <span
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-orange-100 dark:bg-orange-900"
              title={t('admin.requiresAttention.tooltip')}
            >
              <AlertCircle className="h-3 w-3 text-orange-600 dark:text-orange-400" />
            </span>
          )}
          <span className="max-w-[280px] truncate font-medium">{feedback.subject}</span>
        </div>
      ),
    },
    {
      key: 'rating',
      header: t('admin.table.columns.rating'),
      cell: (feedback) =>
        feedback.rating ? (
          <div className="flex items-center gap-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <span key={i} className={i < feedback.rating! ? 'text-yellow-500' : 'text-gray-300'}>
                ★
              </span>
            ))}
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: 'status',
      header: t('admin.table.columns.status'),
      cell: (feedback) => (
        <Badge variant={getStatusBadgeVariant(feedback.status)}>
          {t(`admin.status.${feedback.status}`)}
        </Badge>
      ),
    },
    {
      key: 'created_time',
      header: t('admin.table.columns.submitted'),
      cell: (feedback) =>
        feedback.created_time ? format(new Date(feedback.created_time), 'PPp') : '—',
    },
    {
      key: 'actions',
      header: '',
      cell: (feedback) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreVertical className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => navigate(`/admin/feedback/${feedback.id}`)}>
              <Eye className="mr-2 h-4 w-4" />
              {t('admin.actions.view')}
            </DropdownMenuItem>
            {feedback.status !== 'resolved' && (
              <DropdownMenuItem onClick={() => handleStatusChange(feedback.id, 'resolved')}>
                <CheckCircle className="mr-2 h-4 w-4" />
                {t('admin.actions.markResolved')}
              </DropdownMenuItem>
            )}
            {feedback.status !== 'dismissed' && (
              <DropdownMenuItem onClick={() => handleStatusChange(feedback.id, 'dismissed')}>
                <XCircle className="mr-2 h-4 w-4" />
                {t('admin.actions.dismiss')}
              </DropdownMenuItem>
            )}
            {canDelete && (
              <DropdownMenuItem
                onClick={() => setDeletingFeedback(feedback)}
                className="text-destructive"
              >
                <Trash2 className="mr-2 h-4 w-4" />
                {t('admin.actions.delete')}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('admin.title')}
        description={t('admin.description')}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <FeedbackStatsCard feedbacks={data?.items || []} />
      </div>

      <Card>
        <CardContent className="pt-6">
          <FeedbackFilters
            typeFilter={typeFilter}
            statusFilter={statusFilter}
            ratingFilter={ratingFilter}
            dateFrom={dateFrom}
            dateTo={dateTo}
            organizationFilter={organizationFilter}
            onTypeChange={setTypeFilter}
            onStatusChange={setStatusFilter}
            onRatingChange={setRatingFilter}
            onDateFromChange={setDateFrom}
            onDateToChange={setDateTo}
            onOrganizationChange={setOrganizationFilter}
            onClearFilters={() => {
              setTypeFilter(undefined)
              setStatusFilter(undefined)
              setRatingFilter(undefined)
              setDateFrom(undefined)
              setDateTo(undefined)
              setOrganizationFilter(undefined)
            }}
            organizations={orgsData?.items}
            isSuperAdmin={user?.is_admin || false}
          />

          {selectedFeedback.length > 0 && (
            <div className="mt-6 flex items-center gap-4 rounded-md border bg-muted/50 px-4 py-3">
              <span className="text-sm font-medium">
                {t('admin.bulkActions.selectedCount', { count: selectedFeedback.length })}
              </span>
              <div className="flex flex-1 items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleBulkMarkResolved}
                >
                  <CheckCircle className="mr-2 h-4 w-4" />
                  {t('admin.bulkActions.markResolvedButton')}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleBulkDismiss}
                >
                  <XCircle className="mr-2 h-4 w-4" />
                  {t('admin.bulkActions.dismissButton')}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm">
                      <Download className="mr-2 h-4 w-4" />
                      {t('admin.bulkActions.exportButton')}
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem onClick={handleExportCSV}>
                      {t('admin.bulkActions.exportCSV')}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={handleExportJSON}>
                      {t('admin.bulkActions.exportJSON')}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedFeedback([])}
                  className="ml-auto"
                >
                  <X className="mr-2 h-4 w-4" />
                  {t('admin.bulkActions.clearSelection')}
                </Button>
              </div>
            </div>
          )}

          <div className="mt-6">
            <DataTable
              columns={columns}
              data={data?.items || []}
              isLoading={isLoading}
              pagination={{
                page: page,
                pageSize: pageSize,
                total: data?.total || 0,
                onPageChange: setPage,
              }}
              selectedRows={selectedFeedback}
              onSelectionChange={setSelectedFeedback}
              getRowId={(feedback) => feedback.id}
            />
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={!!deletingFeedback}
        onOpenChange={(open) => !open && setDeletingFeedback(null)}
        onConfirm={handleDelete}
        title={t('admin.deleteDialog.title')}
        description={t('admin.deleteDialog.description')}
        confirmLabel={t('admin.deleteDialog.confirm')}
        cancelLabel={t('admin.deleteDialog.cancel')}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
