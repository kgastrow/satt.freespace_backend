import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { useGetDeletionStatusQuery, useCancelDeletionMutation } from '@/features/user/userApi'
import { useAppSelector } from '@/store/hooks'
import { getErrorMessage } from '@/types/api'

/**
 * DeletionPendingBanner - Banner shown at top of app when account deletion is pending
 * Displays scheduled deletion date and provides "Cancel Deletion" button
 * Uses destructive colors to indicate the account is scheduled for deletion
 */
export function DeletionPendingBanner() {
  const { t } = useTranslation('common')
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)

  // Skip query if not authenticated to avoid unnecessary API calls
  const { data: deletionStatus } = useGetDeletionStatusQuery(undefined, {
    skip: !isAuthenticated,
  })

  const [cancelDeletion, { isLoading: isCancelling }] = useCancelDeletionMutation()

  const handleCancelDeletion = async () => {
    try {
      await cancelDeletion().unwrap()
      toast.success(t('deletionPendingBanner.cancelSuccess'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  }

  // Only show banner if authenticated and has an active pending deletion request
  if (
    !isAuthenticated ||
    !deletionStatus?.has_active_request ||
    deletionStatus?.request?.status !== 'pending'
  ) {
    return null
  }

  const scheduledDate = deletionStatus.request.scheduled_hard_delete_at

  return (
    <div className="w-full bg-destructive text-destructive-foreground border-b-2 border-destructive/80 flex-shrink-0">
      <div className="container mx-auto px-4 py-2 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-1">
          <AlertTriangle className="h-5 w-5 flex-shrink-0" />
          <span className="font-medium">
            {scheduledDate
              ? t('deletionPendingBanner.message', { date: formatDate(scheduledDate) })
              : t('deletionPendingBanner.messagePending')}
          </span>
        </div>
        <Button
          onClick={handleCancelDeletion}
          disabled={isCancelling}
          variant="outline"
          size="sm"
          className="border-destructive-foreground/20 bg-destructive-foreground/10 text-destructive-foreground hover:bg-destructive-foreground/20"
        >
          {isCancelling
            ? t('deletionPendingBanner.cancelling')
            : t('deletionPendingBanner.cancelButton')}
        </Button>
      </div>
    </div>
  )
}
