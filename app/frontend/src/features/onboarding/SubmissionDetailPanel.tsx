import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { DatePicker } from '@/components/ui/date-picker'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
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
import {
  CheckCircle2,
  XCircle,
  FileText,
  ExternalLink,
  Loader2,
  ChevronUp,
  ChevronDown,
  X,
  AlertCircle,
  MessageSquare,
  User,
  Shield,
  Send,
} from 'lucide-react'
import {
  useGetSubmissionDetailsQuery,
  useApproveSubmissionMutation,
  useRejectSubmissionMutation,
  useRequestChangeMutation,
  useGetReviewCommentsQuery,
  useAddReviewCommentMutation,
} from '@/store/api/onboardingApi'
import { useGetFileQuery, useLazyGetDownloadUrlQuery } from '@/features/files/filesApi'
import { FileImageWithPreview } from '@/components/FileImageWithPreview'
import { formatBytes } from '@/lib/utils'
import { useSelector } from 'react-redux'
import type { RootState } from '@/store'

/**
 * Convert a field key (snake_case or camelCase) to a readable label
 */
function formatFieldLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

/**
 * Format a field value for display
 */
function formatFieldValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">Not provided</span>
  }
  if (typeof value === 'boolean') {
    return value ? (
      <span className="inline-flex items-center gap-1 text-green-600">
        <CheckCircle2 className="h-4 w-4" /> Yes
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        <XCircle className="h-4 w-4" /> No
      </span>
    )
  }
  if (typeof value === 'object') {
    return <span className="text-sm">{JSON.stringify(value)}</span>
  }
  return String(value)
}

/**
 * Fields to hide from the review display (internal/system fields)
 */
const HIDDEN_FIELDS = ['auto_completed', 'verified']

/**
 * UUID regex pattern for detecting file IDs
 */
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/**
 * Check if a value looks like a UUID (likely a file ID)
 */
function isUUID(value: unknown): value is string {
  return typeof value === 'string' && UUID_REGEX.test(value)
}

/**
 * Component to display a file preview/download link
 * Shows image preview for image files, download link for other files
 */
function FilePreviewLink({ fileId }: { fileId: string }) {
  const { t } = useTranslation('admin')
  const { data: file, isLoading: isLoadingFile, error: fileError } = useGetFileQuery(fileId)
  const [triggerDownload] = useLazyGetDownloadUrlQuery()
  const [isDownloading, setIsDownloading] = useState(false)
  const token = useSelector((state: RootState) => state.auth.token)

  const isImage = file?.content_type?.startsWith('image/')

  const handleClick = async () => {
    setIsDownloading(true)
    try {
      const result = await triggerDownload(fileId).unwrap()

      // Fetch the file with authentication header
      const response = await fetch(result.download_url, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to fetch file')
      }

      // Create blob URL and open in new tab (SEC-F-008: add noopener,noreferrer)
      const blob = await response.blob()
      const blobUrl = URL.createObjectURL(blob)
      window.open(blobUrl, '_blank', 'noopener,noreferrer')

      // Clean up the blob URL after a delay to allow the new tab to load
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000)
    } catch {
      toast.error(t('onboardingReview.file.downloadError'))
    } finally {
      setIsDownloading(false)
    }
  }

  if (isLoadingFile) {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground text-sm">
        <Loader2 className="h-3 w-3 animate-spin" />
        {t('onboardingReview.file.loading')}
      </span>
    )
  }

  if (fileError || !file) {
    return (
      <span className="text-muted-foreground italic text-sm">
        {t('onboardingReview.file.notFound')}
      </span>
    )
  }

  // For image files, show inline preview with click-to-enlarge
  if (isImage) {
    return (
      <div className="mt-1">
        <FileImageWithPreview
          fileId={fileId}
          hasThumbnail={!!file.thumbnail_storage_key}
          alt={file.original_filename}
          className="w-24 h-24 rounded border"
          imageClassName="object-cover"
          mode="thumbnail"
          enablePreview={true}
        />
        <p className="text-xs text-muted-foreground mt-1">
          {file.original_filename} ({formatBytes(file.size_bytes)})
        </p>
      </div>
    )
  }

  // For non-image files, show download link
  return (
    <button
      onClick={handleClick}
      disabled={isDownloading}
      className="inline-flex items-center gap-2 text-primary hover:underline cursor-pointer text-sm font-medium disabled:opacity-50"
    >
      <FileText className="h-4 w-4 flex-shrink-0" />
      <span className="truncate max-w-[200px]" title={file.original_filename}>
        {file.original_filename}
      </span>
      <span className="text-muted-foreground text-xs">({formatBytes(file.size_bytes)})</span>
      {isDownloading ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <ExternalLink className="h-3 w-3" />
      )}
    </button>
  )
}

interface SubmissionDetailPanelProps {
  userUserTypeId: string
  onClose: () => void
  onNavigatePrev?: () => void
  onNavigateNext?: () => void
  canNavigatePrev?: boolean
  canNavigateNext?: boolean
}

export function SubmissionDetailPanel({
  userUserTypeId,
  onClose,
  onNavigatePrev,
  onNavigateNext,
  canNavigatePrev = false,
  canNavigateNext = false,
}: SubmissionDetailPanelProps) {
  const { t } = useTranslation('admin')
  const [rejectReason, setRejectReason] = useState('')
  const [changeRequestComment, setChangeRequestComment] = useState('')
  const [newComment, setNewComment] = useState('')
  const [showApproveDialog, setShowApproveDialog] = useState(false)
  const [showRejectDialog, setShowRejectDialog] = useState(false)
  const [showRequestChangeDialog, setShowRequestChangeDialog] = useState(false)
  const [hasExpiryDate, setHasExpiryDate] = useState(false)
  const [expiryDate, setExpiryDate] = useState<string | undefined>(undefined)

  const { data: submission, isLoading } = useGetSubmissionDetailsQuery(userUserTypeId)
  const { data: commentsData } = useGetReviewCommentsQuery(userUserTypeId)
  const [approveSubmission, { isLoading: isApproving }] = useApproveSubmissionMutation()
  const [rejectSubmission, { isLoading: isRejecting }] = useRejectSubmissionMutation()
  const [requestChange, { isLoading: isRequestingChange }] = useRequestChangeMutation()
  const [addComment, { isLoading: isAddingComment }] = useAddReviewCommentMutation()

  const handleApprove = async () => {
    try {
      // Convert YYYY-MM-DD to full ISO datetime at end of day in UTC
      const body = hasExpiryDate && expiryDate
        ? { expires_at: `${expiryDate}T23:59:59Z` }
        : undefined
      await approveSubmission({ userUserTypeId, body }).unwrap()
      toast.success(t('onboardingReview.toast.approveSuccess'))
      setShowApproveDialog(false)
      setHasExpiryDate(false)
      setExpiryDate(undefined)
      onClose()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string | object[] } }
      const errorMessage =
        typeof apiError.data?.detail === 'string'
          ? apiError.data.detail
          : t('onboardingReview.toast.approveError')
      toast.error(errorMessage)
    }
  }

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      toast.error(t('onboardingReview.validation.rejectReasonRequired'))
      return
    }

    try {
      await rejectSubmission({ user_user_type_id: userUserTypeId, reason: rejectReason }).unwrap()
      toast.success(t('onboardingReview.toast.rejectSuccess'))
      setShowRejectDialog(false)
      setRejectReason('')
      onClose()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string | object[] } }
      const errorMessage =
        typeof apiError.data?.detail === 'string'
          ? apiError.data.detail
          : t('onboardingReview.toast.rejectError')
      toast.error(errorMessage)
    }
  }

  const closeRejectDialog = () => {
    setShowRejectDialog(false)
    setRejectReason('')
  }

  const handleRequestChange = async () => {
    if (!changeRequestComment.trim()) {
      toast.error(t('onboardingReview.validation.changeCommentRequired'))
      return
    }

    try {
      await requestChange({
        user_user_type_id: userUserTypeId,
        comment: changeRequestComment,
      }).unwrap()
      toast.success(t('onboardingReview.toast.changeRequestSuccess'))
      setShowRequestChangeDialog(false)
      setChangeRequestComment('')
      onClose()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string | object[] } }
      const errorMessage =
        typeof apiError.data?.detail === 'string'
          ? apiError.data.detail
          : t('onboardingReview.toast.changeRequestError')
      toast.error(errorMessage)
    }
  }

  const closeRequestChangeDialog = () => {
    setShowRequestChangeDialog(false)
    setChangeRequestComment('')
  }

  const handleAddComment = async () => {
    if (!newComment.trim()) return

    try {
      await addComment({
        user_user_type_id: userUserTypeId,
        comment: newComment,
      }).unwrap()
      toast.success(t('onboardingReview.toast.commentAddedSuccess'))
      setNewComment('')
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string | object[] } }
      const errorMessage =
        typeof apiError.data?.detail === 'string'
          ? apiError.data.detail
          : t('onboardingReview.toast.commentAddedError')
      toast.error(errorMessage)
    }
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!submission) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-destructive text-sm">{t('onboardingReview.dialog.notFound')}</p>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col border rounded-lg bg-card">
      {/* Compact Header with User Info and Actions */}
      <div className="flex-shrink-0 px-4 py-3 border-b bg-card sticky top-0 z-10">
        <div className="flex items-center justify-between gap-4">
          {/* User Info - Compact */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold truncate">
                  {submission.user_first_name} {submission.user_last_name}
                </h3>
                <Badge variant="secondary" className="shrink-0">{submission.user_type_name}</Badge>
                {submission.requires_admin_attention && (
                  <Badge variant="destructive" className="shrink-0 gap-1">
                    <AlertCircle className="h-3 w-3" />
                    {t('onboardingReview.actionRequired')}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {submission.user_email} · {new Date(submission.submitted_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <Button
              variant="warning"
              size="sm"
              onClick={() => setShowRejectDialog(true)}
            >
              {t('onboardingReview.dialog.reject')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowRequestChangeDialog(true)}
            >
              {t('onboardingReview.dialog.requestChanges')}
            </Button>
            <Button size="sm" onClick={() => setShowApproveDialog(true)}>
              {t('onboardingReview.dialog.approve')}
            </Button>
            {/* Navigation */}
            <div className="flex items-center border-l pl-2 ml-1">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onNavigatePrev}
                disabled={!canNavigatePrev}
                title={t('onboardingReview.keyboard.previous')}
              >
                <ChevronUp className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onNavigateNext}
                disabled={!canNavigateNext}
                title={t('onboardingReview.keyboard.next')}
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={onClose}
                title={t('onboardingReview.dialog.close')}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>

      </div>

      {/* Approve Confirmation Dialog */}
      <AlertDialog open={showApproveDialog} onOpenChange={(open) => {
        setShowApproveDialog(open)
        if (!open) {
          setHasExpiryDate(false)
          setExpiryDate(undefined)
        }
      }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('onboardingReview.confirm.approveTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('onboardingReview.confirm.approveDescription', {
                name: `${submission.user_first_name} ${submission.user_last_name}`,
                userType: submission.user_type_name,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>

          {/* Expiry Date Option */}
          <div className="py-4 space-y-3">
            <div className="flex items-center space-x-2">
              <Checkbox
                id="hasExpiryDate"
                checked={hasExpiryDate}
                onCheckedChange={(checked) => {
                  setHasExpiryDate(checked === true)
                  if (!checked) {
                    setExpiryDate(undefined)
                  }
                }}
              />
              <Label htmlFor="hasExpiryDate" className="text-sm font-medium cursor-pointer">
                {t('onboardingReview.expiry.setExpiryDate')}
              </Label>
            </div>

            {hasExpiryDate && (
              <div className="pl-6 space-y-2">
                <p className="text-sm text-muted-foreground">
                  {t('onboardingReview.expiry.description')}
                </p>
                <div className="flex items-center gap-2">
                  <DatePicker
                    value={expiryDate}
                    onChange={setExpiryDate}
                    placeholder={t('onboardingReview.expiry.selectDate')}
                    minDate={new Date()}
                    dateFormat="PPP"
                  />
                </div>
              </div>
            )}
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel>{t('onboardingReview.dialog.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleApprove} disabled={isApproving}>
              {isApproving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                t('onboardingReview.dialog.approve')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reject Confirmation Dialog */}
      <AlertDialog open={showRejectDialog} onOpenChange={(open) => !open && closeRejectDialog()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('onboardingReview.confirm.rejectTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('onboardingReview.confirm.rejectDescription', {
                name: `${submission.user_first_name} ${submission.user_last_name}`,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-2">
            <Textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder={t('onboardingReview.dialog.rejectReasonPlaceholder')}
              rows={3}
              className="text-sm"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('onboardingReview.dialog.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleReject}
              disabled={isRejecting || !rejectReason.trim()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isRejecting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                t('onboardingReview.dialog.confirmReject')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Request Change Dialog */}
      <AlertDialog open={showRequestChangeDialog} onOpenChange={(open) => !open && closeRequestChangeDialog()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('onboardingReview.confirm.requestChangeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('onboardingReview.confirm.requestChangeDescription', {
                name: `${submission.user_first_name} ${submission.user_last_name}`,
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-2">
            <Textarea
              value={changeRequestComment}
              onChange={(e) => setChangeRequestComment(e.target.value)}
              placeholder={t('onboardingReview.dialog.changeCommentPlaceholder')}
              rows={4}
              className="text-sm"
            />
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('onboardingReview.dialog.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRequestChange}
              disabled={isRequestingChange || !changeRequestComment.trim()}
            >
              {isRequestingChange ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                t('onboardingReview.dialog.confirmRequestChange')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Scrollable Content */}
      <ScrollArea className="flex-1">
        <div className="px-4 pb-4">
          <Accordion
            type="multiple"
            defaultValue={submission.steps_data.map((s) => s.onboarding_step_id)}
            className="w-full"
          >
            {submission.steps_data.map((progress) => {
              const visibleFields = Object.entries(progress.submitted_data || {}).filter(
                ([key]) => !HIDDEN_FIELDS.includes(key)
              )

              return (
                <AccordionItem key={progress.onboarding_step_id} value={progress.onboarding_step_id}>
                  <AccordionTrigger className="py-2 text-sm font-medium hover:no-underline">
                    {progress.step_name}
                  </AccordionTrigger>
                  <AccordionContent className="pb-2">
                    {visibleFields.length > 0 ? (
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                        {visibleFields.map(([key, value]) => (
                          <div key={key} className="flex flex-col">
                            <dt className="text-xs text-muted-foreground">
                              {formatFieldLabel(key)}
                            </dt>
                            <dd className="font-medium truncate">
                              {isUUID(value) ? (
                                <FilePreviewLink fileId={value} />
                              ) : (
                                formatFieldValue(value)
                              )}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : (
                      <p className="text-xs text-muted-foreground italic">
                        {t('onboardingReview.dialog.noData')}
                      </p>
                    )}
                  </AccordionContent>
                </AccordionItem>
              )
            })}
          </Accordion>

          {/* Review Comments Section */}
          {commentsData && commentsData.comments.length > 0 && (
            <>
              <Separator className="my-4" />
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  <h4 className="font-medium text-sm">
                    {t('onboardingReview.comments.title')}
                  </h4>
                </div>
                <div className="space-y-3">
                  {commentsData.comments.map((comment) => (
                    <div
                      key={comment.id}
                      className={`p-3 rounded-lg text-sm ${
                        comment.author_type === 'admin'
                          ? 'bg-muted/50 border-l-2 border-l-primary'
                          : 'bg-info/10 border-l-2 border-l-info'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        {comment.author_type === 'admin' ? (
                          <Shield className="h-3 w-3 text-muted-foreground" />
                        ) : (
                          <User className="h-3 w-3 text-muted-foreground" />
                        )}
                        <span className="font-medium text-xs">
                          {comment.author_name}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {new Date(comment.created_time).toLocaleString(undefined, {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      </div>
                      <p className="whitespace-pre-wrap">{comment.comment}</p>
                    </div>
                  ))}
                </div>

                {/* Add comment form - only show for pending submissions */}
                {submission.onboarding_status !== 'approved' && submission.onboarding_status !== 'rejected' && (
                  <div className="flex gap-2 pt-2">
                    <Textarea
                      value={newComment}
                      onChange={(e) => setNewComment(e.target.value)}
                      placeholder={t('onboardingReview.comments.addPlaceholder')}
                      rows={2}
                      className="text-sm flex-1"
                    />
                    <Button
                      size="icon"
                      onClick={handleAddComment}
                      disabled={isAddingComment || !newComment.trim()}
                      className="shrink-0"
                    >
                      {isAddingComment ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  )
}

interface SubmissionDetailSheetProps {
  userUserTypeId: string | null
  onClose: () => void
  onNavigatePrev?: () => void
  onNavigateNext?: () => void
  canNavigatePrev?: boolean
  canNavigateNext?: boolean
}

export function SubmissionDetailSheet({
  userUserTypeId,
  onClose,
  onNavigatePrev,
  onNavigateNext,
  canNavigatePrev,
  canNavigateNext,
}: SubmissionDetailSheetProps) {
  const { t } = useTranslation('admin')

  return (
    <Sheet open={!!userUserTypeId} onOpenChange={() => onClose()}>
      <SheetContent side="right" className="w-full sm:max-w-lg p-0">
        <SheetHeader className="sr-only">
          <SheetTitle>{t('onboardingReview.dialog.title')}</SheetTitle>
          <SheetDescription>{t('onboardingReview.dialog.description')}</SheetDescription>
        </SheetHeader>
        {userUserTypeId && (
          <SubmissionDetailPanel
            userUserTypeId={userUserTypeId}
            onClose={onClose}
            onNavigatePrev={onNavigatePrev}
            onNavigateNext={onNavigateNext}
            canNavigatePrev={canNavigatePrev}
            canNavigateNext={canNavigateNext}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}
