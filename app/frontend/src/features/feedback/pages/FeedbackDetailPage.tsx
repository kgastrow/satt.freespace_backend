import { useParams, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useState } from 'react'
import {
  useGetFeedbackQuery,
  useDeleteFeedbackMutation,
} from '../feedbackApi'
import type { FeedbackStatus, FeedbackType } from '../types'
import { FeedbackResponsePanel } from '../components/FeedbackResponsePanel'
import { Trash2, Calendar, User, Globe, Monitor, ArrowLeft } from 'lucide-react'
import { AttachmentDisplay } from '../components/AttachmentDisplay'
import { usePermission } from '@/hooks/usePermission'
import { format } from 'date-fns'

export function FeedbackDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { t } = useTranslation('feedback')
  const navigate = useNavigate()
  const { canDelete } = usePermission('feedback')
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

  const { data: feedback, isLoading } = useGetFeedbackQuery(id!)
  const [deleteFeedback, { isLoading: isDeleting }] = useDeleteFeedbackMutation()

  const handleDelete = async () => {
    if (!id) return
    try {
      await deleteFeedback(id).unwrap()
      toast.success(t('admin.toast.deleteSuccess'))
      navigate('/admin/feedback')
    } catch {
      toast.error(t('admin.toast.deleteError'))
    }
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

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('admin.detail.loading')}
        />
        <div className="flex items-center justify-center h-64">
          <p className="text-muted-foreground">{t('admin.detail.loading')}</p>
        </div>
      </div>
    )
  }

  if (!feedback) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('admin.detail.notFound')}
        />
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground text-center">{t('admin.detail.notFound')}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate('/admin/feedback')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('admin.detail.backToList')}
        </Button>
      </div>

      <PageHeader title={feedback.subject}>
        {canDelete && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => setIsDeleteDialogOpen(true)}
            disabled={isDeleting}
          >
            <Trash2 className="mr-2 h-4 w-4" />
            {t('admin.actions.delete')}
          </Button>
        )}
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Feedback details */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>{t('admin.detail.feedbackDetails')}</CardTitle>
                <div className="flex items-center gap-2">
                  <Badge variant={getTypeBadgeVariant(feedback.type)}>
                    {t(`form.fields.type.options.${feedback.type}`)}
                  </Badge>
                  <Badge variant={getStatusBadgeVariant(feedback.status)}>
                    {t(`admin.status.${feedback.status}`)}
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="text-sm font-medium mb-1">{t('form.fields.subject.label')}</h4>
                <p className="text-sm">{feedback.subject}</p>
              </div>
              <Separator />
              <div>
                <h4 className="text-sm font-medium mb-1">{t('form.fields.message.label')}</h4>
                <p className="text-sm whitespace-pre-wrap">{feedback.message}</p>
              </div>
              {feedback.rating && (
                <>
                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-1">{t('form.fields.rating.label')}</h4>
                    <div className="flex items-center gap-1">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <span
                          key={i}
                          className={i < feedback.rating! ? 'text-yellow-500 text-lg' : 'text-gray-300 text-lg'}
                        >
                          ★
                        </span>
                      ))}
                    </div>
                  </div>
                </>
              )}
              {feedback.attachments && feedback.attachments.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <h4 className="text-sm font-medium mb-2">{t('admin.detail.attachments')}</h4>
                    <div className="space-y-3">
                      {feedback.attachments.map((attachment) => (
                        <AttachmentDisplay key={attachment.id} attachment={attachment} />
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* Context information */}
          <Card>
            <CardHeader>
              <CardTitle>{t('admin.detail.contextInfo')}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {feedback.page_url && (
                <div className="flex items-start gap-3">
                  <Globe className="h-4 w-4 mt-0.5 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{t('admin.detail.pageUrl')}</p>
                    <p className="text-sm text-muted-foreground truncate">{feedback.page_url}</p>
                  </div>
                </div>
              )}
              {feedback.user_agent && (
                <div className="flex items-start gap-3">
                  <Monitor className="h-4 w-4 mt-0.5 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{t('admin.detail.userAgent')}</p>
                    <p className="text-sm text-muted-foreground break-all">{feedback.user_agent}</p>
                  </div>
                </div>
              )}
              {feedback.screen_resolution && (
                <div className="flex items-start gap-3">
                  <Monitor className="h-4 w-4 mt-0.5 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium">{t('admin.detail.screenResolution')}</p>
                    <p className="text-sm text-muted-foreground">{feedback.screen_resolution}</p>
                  </div>
                </div>
              )}
              <div className="flex items-start gap-3">
                <Calendar className="h-4 w-4 mt-0.5 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{t('admin.detail.submittedAt')}</p>
                  <p className="text-sm text-muted-foreground">
                    {feedback.created_time ? format(new Date(feedback.created_time), 'PPpp') : '—'}
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <User className="h-4 w-4 mt-0.5 text-muted-foreground" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">{t('admin.detail.submittedBy')}</p>
                  <p className="text-sm text-muted-foreground">
                    {feedback.user_email || feedback.user_id}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Response panel */}
        <div className="lg:col-span-1">
          <FeedbackResponsePanel feedback={feedback} />
        </div>
      </div>

      <ConfirmDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
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
