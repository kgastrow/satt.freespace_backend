import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { QRCodeSVG } from 'qrcode.react'
import { toast } from 'sonner'
import { Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSeparator,
  InputOTPSlot,
} from '@/components/ui/input-otp'
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
import { useInitiateTwoFactorSetupMutation, useVerifyTwoFactorSetupMutation } from '@/store/api/twoFactorApi'

const createVerificationSchema = (t: (key: string) => string) =>
  z.object({
    code: z
      .string()
      .length(6, t('settings:twoFactor.setup.validation.codeLength'))
      .regex(/^\d+$/, t('settings:twoFactor.setup.validation.codeNumeric')),
  })

type VerificationFormData = z.infer<ReturnType<typeof createVerificationSchema>>

interface TwoFactorSetupProps {
  onSetupComplete: (backupCodes: string[]) => void
}

export function TwoFactorSetup({ onSetupComplete }: TwoFactorSetupProps) {
  const { t } = useTranslation(['settings'])
  const [initiateSetup, { isLoading: isInitiating }] = useInitiateTwoFactorSetupMutation()
  const [verifySetup, { isLoading: isVerifying }] = useVerifyTwoFactorSetupMutation()

  const [setupData, setSetupData] = useState<{
    secret: string
    provisioning_uri: string
  } | null>(null)
  const [copiedSecret, setCopiedSecret] = useState(false)

  const form = useForm<VerificationFormData>({
    resolver: zodResolver(createVerificationSchema(t)),
    defaultValues: { code: '' },
  })

  const handleInitiateSetup = async () => {
    try {
      const result = await initiateSetup().unwrap()
      setSetupData(result)
    } catch {
      toast.error(t('settings:twoFactor.setup.messages.initiateFailed'))
    }
  }

  const handleCopySecret = async () => {
    if (setupData) {
      await navigator.clipboard.writeText(setupData.secret)
      setCopiedSecret(true)
      toast.success(t('settings:twoFactor.setup.messages.secretCopied'))
      setTimeout(() => setCopiedSecret(false), 2000)
    }
  }

  const onSubmit = async (data: VerificationFormData) => {
    if (!setupData) return

    try {
      const result = await verifySetup({
        code: data.code,
        secret: setupData.secret,
      }).unwrap()
      toast.success(t('settings:twoFactor.setup.messages.verifySuccess'))
      onSetupComplete(result.backup_codes)
    } catch {
      form.setError('code', {
        message: t('settings:twoFactor.setup.messages.verifyFailed'),
      })
    }
  }

  if (!setupData) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:twoFactor.setup.title')}</CardTitle>
          <CardDescription>{t('settings:twoFactor.setup.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          <Alert>
            <AlertTitle>{t('settings:twoFactor.setup.alert.title')}</AlertTitle>
            <AlertDescription>{t('settings:twoFactor.setup.alert.description')}</AlertDescription>
          </Alert>
          <Button onClick={handleInitiateSetup} disabled={isInitiating} className="mt-4">
            {isInitiating ? t('settings:twoFactor.setup.buttons.starting') : t('settings:twoFactor.setup.buttons.start')}
          </Button>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('settings:twoFactor.setup.scanning.title')}</CardTitle>
        <CardDescription>{t('settings:twoFactor.setup.scanning.description')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-col items-center space-y-4">
          <div className="p-4 rounded-lg border" style={{ backgroundColor: 'white' }}>
            <QRCodeSVG value={setupData.provisioning_uri} size={200} level="M" />
          </div>

          <div className="w-full">
            <p className="text-sm font-medium mb-2">{t('settings:twoFactor.setup.manualEntry.label')}</p>
            <div className="flex items-center gap-2">
              <code className="flex-1 px-3 py-2 bg-muted rounded-md text-sm font-mono break-all">
                {setupData.secret}
              </code>
              <Button
                variant="outline"
                size="icon"
                onClick={handleCopySecret}
                aria-label={t('settings:twoFactor.setup.manualEntry.copyButton')}
              >
                {copiedSecret ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {t('settings:twoFactor.setup.manualEntry.description')}
            </p>
          </div>
        </div>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="code"
              render={({ field }) => (
                <FormItem className="flex flex-col items-center">
                  <FormLabel>{t('settings:twoFactor.setup.verification.label')}</FormLabel>
                  <FormControl>
                    <InputOTP
                      maxLength={6}
                      value={field.value}
                      onChange={field.onChange}
                      autoFocus
                    >
                      <InputOTPGroup>
                        <InputOTPSlot index={0} className="h-14 w-12 text-xl" />
                        <InputOTPSlot index={1} className="h-14 w-12 text-xl" />
                        <InputOTPSlot index={2} className="h-14 w-12 text-xl" />
                      </InputOTPGroup>
                      <InputOTPSeparator />
                      <InputOTPGroup>
                        <InputOTPSlot index={3} className="h-14 w-12 text-xl" />
                        <InputOTPSlot index={4} className="h-14 w-12 text-xl" />
                        <InputOTPSlot index={5} className="h-14 w-12 text-xl" />
                      </InputOTPGroup>
                    </InputOTP>
                  </FormControl>
                  <FormDescription>{t('settings:twoFactor.setup.verification.description')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button type="submit" disabled={isVerifying} className="w-full">
              {isVerifying ? t('settings:twoFactor.setup.buttons.verifying') : t('settings:twoFactor.setup.buttons.verify')}
            </Button>
          </form>
        </Form>
      </CardContent>
    </Card>
  )
}
