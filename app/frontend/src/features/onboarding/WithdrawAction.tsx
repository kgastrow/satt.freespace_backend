import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useWithdrawOnboardingMutation } from '@/store/api/onboardingApi'

export type WithdrawableStatus = 'in_progress' | 'pending_review' | 'change_requested'

interface WithdrawActionProps {
  userUserTypeId: string
  status: WithdrawableStatus
  userTypeName: string
  className?: string
}

export function WithdrawAction({
  userUserTypeId,
  status,
  userTypeName,
  className,
}: WithdrawActionProps) {
  const { t } = useTranslation('onboarding')
  const [withdraw, { isLoading }] = useWithdrawOnboardingMutation()

  const descriptionKey =
    status === 'pending_review'
      ? 'wizard.withdraw.descriptionPendingReview'
      : status === 'change_requested'
        ? 'wizard.withdraw.descriptionChangeRequested'
        : 'wizard.withdraw.descriptionInProgress'

  const handleConfirm = async () => {
    try {
      await withdraw(userUserTypeId).unwrap()
      toast.success(t('wizard.withdraw.success'))
    } catch (error) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('wizard.withdraw.error'))
    }
  }

  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          variant="link"
          size="sm"
          className={
            className ?? 'h-auto p-0 text-muted-foreground hover:text-foreground'
          }
        >
          {t('wizard.withdraw.trigger')}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('wizard.withdraw.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            {t(descriptionKey, { userType: userTypeName })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>
            {t('wizard.withdraw.cancel')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} disabled={isLoading}>
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {t('wizard.withdraw.submitting')}
              </>
            ) : (
              t('wizard.withdraw.confirm')
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
