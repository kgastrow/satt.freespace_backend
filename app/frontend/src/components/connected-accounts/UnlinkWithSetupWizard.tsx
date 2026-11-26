import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { QRCodeSVG } from 'qrcode.react'
import { toast } from 'sonner'
import { Copy, Check, Shield, Lock, AlertTriangle } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { PasswordRequirements } from '@/components/password/PasswordRequirements'
import { BackupCodesDisplay } from '@/components/two-factor/BackupCodesDisplay'
import { createPasswordSchema } from '@/lib/password-validation'
import { useInitiateTwoFactorSetupMutation } from '@/store/api/twoFactorApi'
import { useUnlinkWithSetupMutation } from '@/store/api/identityApi'

type WizardStep = 'intro' | 'password' | '2fa' | 'confirm' | 'backup-codes'

interface UnlinkWithSetupWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  provider: string
  twoFactorPolicy: 'disabled' | 'optional' | 'mandatory'
  onComplete: () => void
}

export function UnlinkWithSetupWizard({
  open,
  onOpenChange,
  provider,
  twoFactorPolicy,
  onComplete,
}: UnlinkWithSetupWizardProps) {
  const { t } = useTranslation(['settings', 'auth', 'common'])
  const [step, setStep] = useState<WizardStep>('intro')
  const [password, setPassword] = useState('')
  const [totpSecret, setTotpSecret] = useState<string | null>(null)
  const [provisioningUri, setProvisioningUri] = useState<string | null>(null)
  const [copiedSecret, setCopiedSecret] = useState(false)
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null)

  const [initiateTwoFactorSetup, { isLoading: isInitiating2FA }] = useInitiateTwoFactorSetupMutation()
  const [unlinkWithSetup, { isLoading: isUnlinking }] = useUnlinkWithSetupMutation()

  const providerName = t(`settings:connectedAccounts.providers.${provider}`, {
    defaultValue: provider.charAt(0).toUpperCase() + provider.slice(1),
  })

  // Password form
  const passwordSchema = z.object({
    password: createPasswordSchema(t),
    confirmPassword: z.string(),
  }).refine((data) => data.password === data.confirmPassword, {
    message: t('auth:validation.passwordMismatch'),
    path: ['confirmPassword'],
  })

  type PasswordFormData = z.infer<typeof passwordSchema>

  const passwordForm = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { password: '', confirmPassword: '' },
  })

  // 2FA form
  const totpSchema = z.object({
    code: z
      .string()
      .length(6, t('settings:twoFactor.setup.validation.codeLength'))
      .regex(/^\d+$/, t('settings:twoFactor.setup.validation.codeNumeric')),
  })

  type TotpFormData = z.infer<typeof totpSchema>

  const totpForm = useForm<TotpFormData>({
    resolver: zodResolver(totpSchema),
    defaultValues: { code: '' },
  })

  const handlePasswordSubmit = async (data: PasswordFormData) => {
    setPassword(data.password)

    // If 2FA is needed, initiate setup
    if (twoFactorPolicy !== 'disabled') {
      try {
        const result = await initiateTwoFactorSetup().unwrap()
        setTotpSecret(result.secret)
        setProvisioningUri(result.provisioning_uri)
        setStep('2fa')
      } catch {
        toast.error(t('settings:twoFactor.setup.messages.initiateFailed'))
      }
    } else {
      setStep('confirm')
    }
  }

  const handleCopySecret = async () => {
    if (totpSecret) {
      await navigator.clipboard.writeText(totpSecret)
      setCopiedSecret(true)
      toast.success(t('settings:twoFactor.setup.messages.secretCopied'))
      setTimeout(() => setCopiedSecret(false), 2000)
    }
  }

  const handleSkip2FA = () => {
    setTotpSecret(null)
    setStep('confirm')
  }

  const handle2FASubmit = async () => {
    // Just advance to confirm step - we'll use the form values in the final submit
    totpForm.clearErrors()
    setStep('confirm')
  }

  const handleFinalSubmit = async () => {
    try {
      const result = await unlinkWithSetup({
        provider,
        new_password: password,
        totp_secret: totpSecret || undefined,
        totp_code: totpSecret ? totpForm.getValues('code') : undefined,
      }).unwrap()

      toast.success(t('settings:connectedAccounts.unlinkSuccess', { provider: providerName }))

      if (result.backup_codes && result.backup_codes.length > 0) {
        setBackupCodes(result.backup_codes)
        setStep('backup-codes')
      } else {
        handleClose()
        onComplete()
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string; detail_code?: string } }
      if (apiError.data?.detail_code === 'two_factor.invalid_code') {
        setStep('2fa')
        totpForm.setError('code', {
          message: t('settings:twoFactor.setup.messages.verifyFailed'),
        })
      } else {
        toast.error(apiError.data?.detail || t('common:error'))
      }
    }
  }

  const handleClose = () => {
    setStep('intro')
    setPassword('')
    setTotpSecret(null)
    setProvisioningUri(null)
    setBackupCodes(null)
    passwordForm.reset()
    totpForm.reset()
    onOpenChange(false)
  }

  const handleBackupCodesComplete = () => {
    handleClose()
    onComplete()
  }

  const renderIntro = () => (
    <>
      <DialogHeader>
        <DialogTitle>{t('settings:connectedAccounts.setupRequired')}</DialogTitle>
        <DialogDescription>
          {t('settings:connectedAccounts.setupRequiredDescription', { provider: providerName })}
        </DialogDescription>
      </DialogHeader>

      <Alert>
        <Shield className="h-4 w-4" />
        <AlertTitle>{t('settings:connectedAccounts.setupRequiredSteps')}</AlertTitle>
        <AlertDescription>
          <ul className="mt-2 list-disc list-inside space-y-1">
            <li>{t('settings:connectedAccounts.stepCreatePassword')}</li>
            {twoFactorPolicy === 'mandatory' && (
              <li>{t('settings:connectedAccounts.step2FARequired')}</li>
            )}
            {twoFactorPolicy === 'optional' && (
              <li>{t('settings:connectedAccounts.step2FARecommended')}</li>
            )}
          </ul>
        </AlertDescription>
      </Alert>

      <DialogFooter>
        <Button variant="outline" onClick={handleClose}>
          {t('common:cancel')}
        </Button>
        <Button onClick={() => setStep('password')}>
          {t('settings:connectedAccounts.beginSetup')}
        </Button>
      </DialogFooter>
    </>
  )

  const renderPasswordStep = () => (
    <>
      <DialogHeader>
        <DialogTitle>{t('settings:connectedAccounts.stepPassword')}</DialogTitle>
        <DialogDescription>
          {t('settings:connectedAccounts.stepPasswordDescription', { provider: providerName })}
        </DialogDescription>
      </DialogHeader>

      <Form {...passwordForm}>
        <form onSubmit={passwordForm.handleSubmit(handlePasswordSubmit)} className="space-y-4">
          <FormField
            control={passwordForm.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('auth:passwordLabel')}</FormLabel>
                <FormControl>
                  <Input type="password" {...field} autoComplete="new-password" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <PasswordRequirements
            control={passwordForm.control}
            name="password"
            compact
          />

          <FormField
            control={passwordForm.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('auth:confirmPasswordLabel')}</FormLabel>
                <FormControl>
                  <Input type="password" {...field} autoComplete="new-password" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <DialogFooter>
            <Button variant="outline" type="button" onClick={() => setStep('intro')}>
              {t('common:back')}
            </Button>
            <Button type="submit" disabled={isInitiating2FA}>
              {isInitiating2FA ? t('common:loading') : t('common:continue')}
            </Button>
          </DialogFooter>
        </form>
      </Form>
    </>
  )

  const render2FAStep = () => (
    <>
      <DialogHeader>
        <DialogTitle>{t('settings:connectedAccounts.step2FA')}</DialogTitle>
        <DialogDescription>
          {twoFactorPolicy === 'mandatory'
            ? t('settings:connectedAccounts.step2FAMandatory')
            : t('settings:connectedAccounts.step2FAOptional')}
        </DialogDescription>
      </DialogHeader>

      {provisioningUri && (
        <div className="flex flex-col items-center space-y-4">
          <div className="p-4 rounded-lg border" style={{ backgroundColor: 'white' }}>
            <QRCodeSVG value={provisioningUri} size={160} level="M" />
          </div>

          {totpSecret && (
            <div className="w-full">
              <p className="text-sm font-medium mb-2">
                {t('settings:twoFactor.setup.manualEntry.label')}
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-3 py-2 bg-muted rounded-md text-sm font-mono break-all">
                  {totpSecret}
                </code>
                <Button
                  variant="outline"
                  size="icon"
                  onClick={handleCopySecret}
                  type="button"
                >
                  {copiedSecret ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}

      <Form {...totpForm}>
        <form onSubmit={totpForm.handleSubmit(handle2FASubmit)} className="space-y-4">
          <FormField
            control={totpForm.control}
            name="code"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('settings:twoFactor.setup.verification.label')}</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="123456"
                    maxLength={6}
                    className="text-center text-2xl tracking-widest font-mono"
                    autoComplete="off"
                  />
                </FormControl>
                <FormDescription>
                  {t('settings:twoFactor.setup.verification.description')}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          <DialogFooter className="flex-col sm:flex-row gap-2">
            <Button variant="outline" type="button" onClick={() => setStep('password')}>
              {t('common:back')}
            </Button>
            {twoFactorPolicy === 'optional' && (
              <Button variant="ghost" type="button" onClick={handleSkip2FA}>
                {t('settings:connectedAccounts.skip2FA')}
              </Button>
            )}
            <Button type="submit">
              {t('common:continue')}
            </Button>
          </DialogFooter>
        </form>
      </Form>
    </>
  )

  const renderConfirmStep = () => (
    <>
      <DialogHeader>
        <DialogTitle>{t('settings:connectedAccounts.stepConfirm')}</DialogTitle>
        <DialogDescription>
          {t('settings:connectedAccounts.stepConfirmDescription', { provider: providerName })}
        </DialogDescription>
      </DialogHeader>

      <Alert>
        <Lock className="h-4 w-4" />
        <AlertDescription>
          <ul className="space-y-1">
            <li className="flex items-center gap-2">
              <Check className="h-4 w-4 text-green-600" />
              {t('settings:connectedAccounts.stepCreatePassword')}
            </li>
            {totpSecret && (
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-green-600" />
                {t('settings:connectedAccounts.step2FA')}
              </li>
            )}
          </ul>
        </AlertDescription>
      </Alert>

      <Alert variant="default">
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          {t('settings:connectedAccounts.unlinkNote', { provider: providerName })}
        </AlertDescription>
      </Alert>

      <DialogFooter>
        <Button
          variant="outline"
          onClick={() => setStep(totpSecret ? '2fa' : 'password')}
          disabled={isUnlinking}
        >
          {t('common:back')}
        </Button>
        <Button onClick={handleFinalSubmit} disabled={isUnlinking}>
          {isUnlinking ? t('common:loading') : t('settings:connectedAccounts.completeUnlink')}
        </Button>
      </DialogFooter>
    </>
  )

  const renderBackupCodes = () => {
    if (!backupCodes) return null

    return (
      <BackupCodesDisplay
        backupCodes={backupCodes}
        onComplete={handleBackupCodesComplete}
      />
    )
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md" showCloseButton={step !== 'backup-codes'}>
        {step === 'intro' && renderIntro()}
        {step === 'password' && renderPasswordStep()}
        {step === '2fa' && render2FAStep()}
        {step === 'confirm' && renderConfirmStep()}
        {step === 'backup-codes' && renderBackupCodes()}
      </DialogContent>
    </Dialog>
  )
}
