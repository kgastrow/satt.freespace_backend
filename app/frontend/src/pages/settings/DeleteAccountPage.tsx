import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Loader2, Calendar, XCircle, CheckCircle } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  useGetDeletionStatusQuery,
  useRequestDeletionMutation,
  useCancelDeletionMutation,
} from '@/features/user/userApi'
import { toast } from 'sonner'
import { getErrorMessage } from '@/types/api'

export function DeleteAccountPage() {
  const { t } = useTranslation(['settings', 'backend'])
  const { data: deletionData, isLoading, error } = useGetDeletionStatusQuery()
  const [requestDeletion, { isLoading: isRequesting }] = useRequestDeletionMutation()
  const [cancelDeletion, { isLoading: isCancelling }] = useCancelDeletionMutation()

  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const [showCancelDialog, setShowCancelDialog] = useState(false)
  const [dismissedRecoveryPrompt, setDismissedRecoveryPrompt] = useState(false)
  const [confirmationText, setConfirmationText] = useState('')

  // Check if there's an active deletion request - use useMemo to avoid effect
  const showRecoveryPrompt = useMemo(() => {
    return !dismissedRecoveryPrompt &&
           deletionData?.has_active_request === true &&
           deletionData?.request?.status === 'pending'
  }, [deletionData, dismissedRecoveryPrompt])

  const handleRequestDeletion = async () => {
    if (confirmationText !== 'DELETE') {
      toast.error(t('settings:deleteAccount.messages.confirmationMismatch'))
      return
    }

    try {
      await requestDeletion().unwrap()
      toast.success(t('settings:deleteAccount.messages.deletionRequested'))
      setShowDeleteDialog(false)
      setConfirmationText('')
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  const handleCancelDeletion = async () => {
    try {
      await cancelDeletion().unwrap()
      toast.success(t('settings:deleteAccount.messages.deletionCancelled'))
      setShowCancelDialog(false)
      setDismissedRecoveryPrompt(true)
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('settings:deleteAccount.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:deleteAccount.error.description')}</AlertDescription>
      </Alert>
    )
  }

  const hasActiveRequest = deletionData?.has_active_request
  const deletionRequest = deletionData?.request

  return (
    <div className="space-y-6">
      {/* Recovery Prompt - shown when user logs in during 30-day window */}
      {showRecoveryPrompt && hasActiveRequest && deletionRequest?.status === 'pending' && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('settings:deleteAccount.recovery.title')}</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>{t('settings:deleteAccount.recovery.description')}</p>
            {deletionRequest.scheduled_hard_delete_at && (
              <p className="font-semibold">
                {t('settings:deleteAccount.recovery.scheduledDate')}:{' '}
                {formatDate(deletionRequest.scheduled_hard_delete_at)}
              </p>
            )}
            <div className="flex gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={() => setShowCancelDialog(true)}
              >
                {t('settings:deleteAccount.recovery.recoverButton')}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDismissedRecoveryPrompt(true)}
              >
                {t('settings:deleteAccount.recovery.dismissButton')}
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-destructive flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            {t('settings:deleteAccount.title')}
          </CardTitle>
          <CardDescription>{t('settings:deleteAccount.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Active Deletion Request Status */}
          {hasActiveRequest && deletionRequest && (
            <>
              <Alert variant={deletionRequest.status === 'pending' ? 'destructive' : 'default'}>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>{t('settings:deleteAccount.status.title')}</AlertTitle>
                <AlertDescription className="space-y-3">
                  <div className="flex items-center gap-2">
                    {deletionRequest.status === 'pending' && (
                      <>
                        <Badge variant="destructive" className="gap-1">
                          <Calendar className="h-3 w-3" />
                          {t('settings:deleteAccount.statusBadge.pending')}
                        </Badge>
                        <span className="text-sm">
                          {t('settings:deleteAccount.status.requestedOn')}{' '}
                          {formatDate(deletionRequest.created_time)}
                        </span>
                      </>
                    )}
                    {deletionRequest.status === 'cancelled' && (
                      <>
                        <Badge variant="outline" className="gap-1">
                          <XCircle className="h-3 w-3" />
                          {t('settings:deleteAccount.statusBadge.cancelled')}
                        </Badge>
                        {deletionRequest.cancelled_at && (
                          <span className="text-sm">
                            {t('settings:deleteAccount.status.cancelledOn')}{' '}
                            {formatDate(deletionRequest.cancelled_at)}
                          </span>
                        )}
                      </>
                    )}
                    {deletionRequest.status === 'completed' && (
                      <Badge variant="default" className="gap-1">
                        <CheckCircle className="h-3 w-3" />
                        {t('settings:deleteAccount.statusBadge.completed')}
                      </Badge>
                    )}
                  </div>

                  {deletionRequest.status === 'pending' &&
                    deletionRequest.scheduled_hard_delete_at && (
                      <div className="space-y-2">
                        <p className="text-sm font-semibold">
                          {t('settings:deleteAccount.status.hardDeleteScheduled')}:{' '}
                          {formatDate(deletionRequest.scheduled_hard_delete_at)}
                        </p>
                        <p className="text-sm">
                          {t('settings:deleteAccount.status.recoveryWindow')}
                        </p>
                      </div>
                    )}

                  {deletionRequest.status === 'cancelled' &&
                    deletionRequest.cancellation_reason && (
                      <p className="text-sm">
                        {t('settings:deleteAccount.status.cancellationReason')}:{' '}
                        {deletionRequest.cancellation_reason}
                      </p>
                    )}
                </AlertDescription>
              </Alert>

              {deletionRequest.status === 'pending' && (
                <div>
                  <Button
                    variant="outline"
                    onClick={() => setShowCancelDialog(true)}
                    disabled={isCancelling}
                    className="gap-2"
                  >
                    {isCancelling ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {t('settings:deleteAccount.buttons.cancelling')}
                      </>
                    ) : (
                      <>
                        <XCircle className="h-4 w-4" />
                        {t('settings:deleteAccount.buttons.cancelDeletion')}
                      </>
                    )}
                  </Button>
                </div>
              )}

              <Separator />
            </>
          )}

          {/* Information about account deletion */}
          {(!hasActiveRequest || deletionRequest?.status === 'cancelled') && (
            <>
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>{t('settings:deleteAccount.warning.title')}</AlertTitle>
                <AlertDescription className="space-y-2">
                  <p>{t('settings:deleteAccount.warning.description')}</p>
                  <ul className="list-disc list-inside space-y-1 text-sm">
                    <li>{t('settings:deleteAccount.warning.immediate')}</li>
                    <li>{t('settings:deleteAccount.warning.recoveryWindow')}</li>
                    <li>{t('settings:deleteAccount.warning.hardDelete')}</li>
                    <li>{t('settings:deleteAccount.warning.permanent')}</li>
                  </ul>
                </AlertDescription>
              </Alert>

              <div>
                <Button
                  variant="destructive"
                  onClick={() => setShowDeleteDialog(true)}
                  disabled={isRequesting}
                  className="gap-2"
                >
                  {isRequesting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {t('settings:deleteAccount.buttons.requesting')}
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="h-4 w-4" />
                      {t('settings:deleteAccount.buttons.deleteAccount')}
                    </>
                  )}
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Delete Account Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              {t('settings:deleteAccount.confirmDialog.title')}
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-4">
              <p>{t('settings:deleteAccount.confirmDialog.description')}</p>
              <div className="space-y-2">
                <Label htmlFor="confirm-text">
                  {t('settings:deleteAccount.confirmDialog.typePrompt')}
                </Label>
                <Input
                  id="confirm-text"
                  value={confirmationText}
                  onChange={(e) => setConfirmationText(e.target.value)}
                  placeholder="DELETE"
                  autoComplete="off"
                />
                <p className="text-xs text-muted-foreground">
                  {t('settings:deleteAccount.confirmDialog.typeHint')}
                </p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setConfirmationText('')}>
              {t('settings:deleteAccount.confirmDialog.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRequestDeletion}
              disabled={confirmationText !== 'DELETE' || isRequesting}
              className="bg-destructive hover:bg-destructive/90"
            >
              {isRequesting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('settings:deleteAccount.buttons.requesting')}
                </>
              ) : (
                t('settings:deleteAccount.confirmDialog.confirm')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Cancel Deletion Confirmation Dialog */}
      <AlertDialog open={showCancelDialog} onOpenChange={setShowCancelDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('settings:deleteAccount.cancelDialog.title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings:deleteAccount.cancelDialog.description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>
              {t('settings:deleteAccount.cancelDialog.cancel')}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleCancelDeletion}
              disabled={isCancelling}
            >
              {isCancelling ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  {t('settings:deleteAccount.buttons.cancelling')}
                </>
              ) : (
                t('settings:deleteAccount.cancelDialog.confirm')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
