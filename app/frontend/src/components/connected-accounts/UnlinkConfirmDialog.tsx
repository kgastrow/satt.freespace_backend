import { useTranslation } from 'react-i18next'
import { AlertTriangle } from 'lucide-react'
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
import { Alert, AlertDescription } from '@/components/ui/alert'

interface UnlinkConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: string
  onConfirm: () => void
  isLoading?: boolean
}

export function UnlinkConfirmDialog({
  open,
  onOpenChange,
  provider,
  onConfirm,
  isLoading = false,
}: UnlinkConfirmDialogProps) {
  const { t } = useTranslation(['settings', 'common'])

  const providerName = t(`settings:connectedAccounts.providers.${provider}`, {
    defaultValue: provider.charAt(0).toUpperCase() + provider.slice(1),
  })

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t('settings:connectedAccounts.unlinkTitle', { provider: providerName })}
          </AlertDialogTitle>
          <AlertDialogDescription>
            {t('settings:connectedAccounts.unlinkDescription', { provider: providerName })}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <Alert variant="default">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            {t('settings:connectedAccounts.unlinkNote', { provider: providerName })}
          </AlertDescription>
        </Alert>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isLoading}>
            {t('common:cancel')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} disabled={isLoading}>
            {isLoading
              ? t('common:loading')
              : t('settings:connectedAccounts.unlinkConfirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
