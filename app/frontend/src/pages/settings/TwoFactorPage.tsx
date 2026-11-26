import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TwoFactorSetup } from '@/components/two-factor/TwoFactorSetup'
import { BackupCodesDisplay } from '@/components/two-factor/BackupCodesDisplay'
import { TwoFactorStatus } from '@/components/two-factor/TwoFactorStatus'
import { useGetUserTwoFactorStatusQuery } from '@/store/api/twoFactorApi'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Loader2 } from 'lucide-react'

export function TwoFactorPage() {
  const { t } = useTranslation(['settings'])
  const { data: status, isLoading, error, refetch } = useGetUserTwoFactorStatusQuery()
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null)

  const handleSetupComplete = (codes: string[]) => {
    setBackupCodes(codes)
  }

  const handleBackupCodesComplete = () => {
    setBackupCodes(null)
    refetch()
  }

  const handleDisableComplete = () => {
    refetch()
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
        <AlertTitle>{t('settings:twoFactor.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:twoFactor.error.description')}</AlertDescription>
      </Alert>
    )
  }

  if (!status) {
    return (
      <Alert>
        <AlertTitle>{t('settings:twoFactor.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:twoFactor.error.noData')}</AlertDescription>
      </Alert>
    )
  }

  if (backupCodes) {
    return <BackupCodesDisplay backupCodes={backupCodes} onComplete={handleBackupCodesComplete} />
  }

  if (status.is_enabled) {
    return <TwoFactorStatus status={status} onDisableComplete={handleDisableComplete} />
  }

  return <TwoFactorSetup onSetupComplete={handleSetupComplete} />
}
