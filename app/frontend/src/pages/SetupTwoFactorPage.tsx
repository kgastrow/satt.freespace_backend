import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Shield, ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { TwoFactorSetup } from '@/components/two-factor/TwoFactorSetup'
import { BackupCodesDisplay } from '@/components/two-factor/BackupCodesDisplay'
import { useGetTwoFactorPolicyQuery } from '@/store/api/twoFactorApi'

type SetupStep = 'intro' | 'setup' | 'backup-codes' | 'complete'

export function SetupTwoFactorPage() {
  const { t } = useTranslation(['auth', 'settings'])
  const navigate = useNavigate()
  const { data: policy } = useGetTwoFactorPolicyQuery()

  const [step, setStep] = useState<SetupStep>('intro')
  const [backupCodes, setBackupCodes] = useState<string[]>([])

  const isMandatory = policy?.is_mandatory ?? false
  const isOptional = policy?.two_factor_policy === 'optional'

  const handleSetupComplete = (codes: string[]) => {
    setBackupCodes(codes)
    setStep('backup-codes')
  }

  const handleBackupCodesSaved = () => {
    setStep('complete')
  }

  const handleSkip = () => {
    navigate('/dashboard')
  }

  const handleContinue = () => {
    navigate('/dashboard')
  }

  // If 2FA is not available, redirect to dashboard
  if (policy && !policy.two_factor_available) {
    navigate('/dashboard')
    return null
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      {step === 'intro' && (
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Shield className="h-6 w-6 text-primary" />
            </div>
            <CardTitle className="text-2xl font-bold">
              {isMandatory
                ? t('auth:setup2fa.titleMandatory')
                : t('auth:setup2fa.titleOptional')}
            </CardTitle>
            <CardDescription>
              {isMandatory
                ? t('auth:setup2fa.descriptionMandatory')
                : t('auth:setup2fa.descriptionOptional')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-muted p-4">
              <h4 className="font-medium mb-2">{t('auth:setup2fa.benefitsTitle')}</h4>
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>• {t('auth:setup2fa.benefit1')}</li>
                <li>• {t('auth:setup2fa.benefit2')}</li>
                <li>• {t('auth:setup2fa.benefit3')}</li>
              </ul>
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-2">
            <Button className="w-full" onClick={() => setStep('setup')}>
              {t('auth:setup2fa.setupButton')}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            {isOptional && (
              <Button variant="ghost" className="w-full" onClick={handleSkip}>
                {t('auth:setup2fa.skipButton')}
              </Button>
            )}
          </CardFooter>
        </Card>
      )}

      {step === 'setup' && (
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>{t('settings:twoFactor.setup.title')}</CardTitle>
            <CardDescription>{t('settings:twoFactor.setup.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            <TwoFactorSetup onSetupComplete={handleSetupComplete} />
          </CardContent>
          {isOptional && (
            <CardFooter>
              <Button variant="ghost" className="w-full" onClick={handleSkip}>
                {t('auth:setup2fa.skipButton')}
              </Button>
            </CardFooter>
          )}
        </Card>
      )}

      {step === 'backup-codes' && (
        <Card className="w-full max-w-lg">
          <CardHeader>
            <CardTitle>{t('settings:twoFactor.backupCodes.title')}</CardTitle>
            <CardDescription>{t('settings:twoFactor.backupCodes.description')}</CardDescription>
          </CardHeader>
          <CardContent>
            <BackupCodesDisplay
              backupCodes={backupCodes}
              onComplete={handleBackupCodesSaved}
            />
          </CardContent>
        </Card>
      )}

      {step === 'complete' && (
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-green-100 dark:bg-green-900">
              <Shield className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <CardTitle className="text-2xl font-bold">
              {t('auth:setup2fa.completeTitle')}
            </CardTitle>
            <CardDescription>
              {t('auth:setup2fa.completeDescription')}
            </CardDescription>
          </CardHeader>
          <CardFooter>
            <Button className="w-full" onClick={handleContinue}>
              {t('auth:setup2fa.continueButton')}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </CardFooter>
        </Card>
      )}
    </div>
  )
}
