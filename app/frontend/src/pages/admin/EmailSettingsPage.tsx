import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  useGetEmailSettingsQuery,
  useGetEffectiveEmailConfigQuery,
  useUpdateEmailSettingsMutation,
  useTestEmailSettingsMutation,
  useResetEmailSettingsMutation,
  type EmailProvider,
} from '@/features/emailSettings/emailSettingsApi'
import { CheckCircle2, Mail, RefreshCw, Send } from 'lucide-react'

const formSchema = z
  .object({
    provider: z.enum(['smtp', 'sendgrid', '']).nullable(),
    smtp_host: z.string().max(255).optional().nullable(),
    smtp_port: z.number().min(1).max(65535).optional().nullable(),
    smtp_username: z.string().max(255).optional().nullable(),
    smtp_password: z.string().max(255).optional().nullable(),
    smtp_use_tls: z.boolean().optional().nullable(),
    smtp_use_ssl: z.boolean().optional().nullable(),
    sendgrid_api_key: z.string().max(255).optional().nullable(),
    sender_email: z.string().email().max(255).optional().nullable().or(z.literal('')),
    sender_name: z.string().max(255).optional().nullable(),
    reply_to_email: z.string().email().max(255).optional().nullable().or(z.literal('')),
  })
  .refine(
    (data) => {
      // If SMTP is selected, host is recommended
      if (data.provider === 'smtp' && !data.smtp_host) {
        return true // We'll show a warning instead of blocking
      }
      return true
    },
    { message: 'SMTP host is required when using SMTP provider' }
  )

type FormData = z.infer<typeof formSchema>

export function EmailSettingsPage() {
  const { t } = useTranslation(['settings', 'common'])
  const [isTestDialogOpen, setIsTestDialogOpen] = useState(false)
  const [isResetDialogOpen, setIsResetDialogOpen] = useState(false)
  const [testEmail, setTestEmail] = useState('')

  const { data: settings, isLoading } = useGetEmailSettingsQuery()
  const { data: effectiveConfig } = useGetEffectiveEmailConfigQuery()
  const [updateSettings, { isLoading: isUpdating }] = useUpdateEmailSettingsMutation()
  const [testSettings, { isLoading: isTesting }] = useTestEmailSettingsMutation()
  const [resetSettings, { isLoading: isResetting }] = useResetEmailSettingsMutation()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      provider: null,
      smtp_host: null,
      smtp_port: null,
      smtp_username: null,
      smtp_password: null,
      smtp_use_tls: true,
      smtp_use_ssl: false,
      sendgrid_api_key: null,
      sender_email: null,
      sender_name: null,
      reply_to_email: null,
    },
    values: settings
      ? {
          provider: settings.provider || null,
          smtp_host: settings.smtp_host || null,
          smtp_port: settings.smtp_port || null,
          smtp_username: settings.smtp_username || null,
          smtp_password: null, // Don't populate password fields
          smtp_use_tls: settings.smtp_use_tls ?? true,
          smtp_use_ssl: settings.smtp_use_ssl ?? false,
          sendgrid_api_key: null, // Don't populate API key
          sender_email: settings.sender_email || null,
          sender_name: settings.sender_name || null,
          reply_to_email: settings.reply_to_email || null,
        }
      : undefined,
  })

  const selectedProvider = form.watch('provider')
  // Branding (sender_email, sender_name, reply_to_email) is locked when the
  // org is on platform defaults — the platform owns the verified sender
  // identity (especially for SendGrid). Backend enforces this with HTTP 422 +
  // detail_code email_settings.sender_locked_on_platform_defaults.
  const brandingLocked = selectedProvider === null || selectedProvider === ''

  const handleSubmit = async (data: FormData) => {
    try {
      // Build update payload, only including changed fields
      const updateData: Record<string, unknown> = {}

      // Convert empty string provider to null
      const provider = data.provider === '' ? null : data.provider
      updateData.provider = provider as EmailProvider

      // Include SMTP settings if SMTP is selected
      if (provider === 'smtp' || provider === null) {
        if (data.smtp_host) updateData.smtp_host = data.smtp_host
        if (data.smtp_port) updateData.smtp_port = data.smtp_port
        if (data.smtp_username) updateData.smtp_username = data.smtp_username
        if (data.smtp_password) updateData.smtp_password = data.smtp_password
        updateData.smtp_use_tls = data.smtp_use_tls
        updateData.smtp_use_ssl = data.smtp_use_ssl
      }

      // Include SendGrid settings if SendGrid is selected
      if (provider === 'sendgrid') {
        if (data.sendgrid_api_key) updateData.sendgrid_api_key = data.sendgrid_api_key
      }

      // Branding settings: only include when org runs its own provider. When
      // on platform defaults the backend rejects any non-null branding field.
      if (provider !== null) {
        updateData.sender_email = data.sender_email || null
        updateData.sender_name = data.sender_name || null
        updateData.reply_to_email = data.reply_to_email || null
      }

      await updateSettings(updateData).unwrap()
      toast.success(t('settings:emailSettings.toast.updateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string; detail_code?: string } }
      if (apiError.data?.detail_code === 'email_settings.sender_locked_on_platform_defaults') {
        toast.error(t('settings:emailSettings.toast.senderLockedOnDefaults'))
      } else {
        toast.error(apiError.data?.detail || t('settings:emailSettings.toast.updateError'))
      }
    }
  }

  const handleTest = async () => {
    if (!testEmail) {
      toast.error(t('settings:emailSettings.toast.emailRequired'))
      return
    }

    try {
      const result = await testSettings({ recipient_email: testEmail }).unwrap()
      if (result.success) {
        toast.success(t('settings:emailSettings.toast.testSuccess'))
      } else {
        toast.error(result.message || t('settings:emailSettings.toast.testFailed'))
      }
      setIsTestDialogOpen(false)
      setTestEmail('')
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('settings:emailSettings.toast.testFailed'))
    }
  }

  const handleReset = async () => {
    try {
      await resetSettings().unwrap()
      toast.success(t('settings:emailSettings.toast.resetSuccess'))
      setIsResetDialogOpen(false)
      form.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('settings:emailSettings.toast.resetError'))
    }
  }

  if (isLoading) {
    return (
      <div className="container max-w-4xl py-8">
        <Skeleton className="h-10 w-64 mb-6" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    )
  }

  return (
    <div className="container max-w-4xl py-8">
      <PageHeader
        title={t('settings:emailSettings.title')}
        description={t('settings:emailSettings.description')}
      />

      {/* Effective Configuration Info */}
      {effectiveConfig && (
        <Alert className="mb-6">
          <Mail className="h-4 w-4" />
          <AlertTitle>{t('settings:emailSettings.effectiveConfig.title')}</AlertTitle>
          <AlertDescription className="flex items-center gap-2">
            {t('settings:emailSettings.effectiveConfig.using')}{' '}
            <Badge variant="secondary">{effectiveConfig.provider_display}</Badge>
            {t('settings:emailSettings.effectiveConfig.from')}{' '}
            <Badge variant="outline">{effectiveConfig.config_source}</Badge>
          </AlertDescription>
        </Alert>
      )}

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Provider Selection */}
          <Card>
            <CardHeader>
              <CardTitle>{t('settings:emailSettings.provider.title')}</CardTitle>
              <CardDescription>{t('settings:emailSettings.provider.description')}</CardDescription>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:emailSettings.provider.label')}</FormLabel>
                    <Select
                      onValueChange={(value) => field.onChange(value === 'default' ? null : value)}
                      value={field.value || 'default'}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder={t('settings:emailSettings.provider.placeholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="default">
                          {t('settings:emailSettings.provider.options.default')}
                        </SelectItem>
                        <SelectItem value="smtp">
                          {t('settings:emailSettings.provider.options.smtp')}
                        </SelectItem>
                        <SelectItem value="sendgrid">
                          {t('settings:emailSettings.provider.options.sendgrid')}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      {t('settings:emailSettings.provider.hint')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* SMTP Settings */}
          {(selectedProvider === 'smtp' || selectedProvider === null) && (
            <Card>
              <CardHeader>
                <CardTitle>{t('settings:emailSettings.smtp.title')}</CardTitle>
                <CardDescription>{t('settings:emailSettings.smtp.description')}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="smtp_host"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('settings:emailSettings.smtp.host')}</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="smtp.example.com"
                            {...field}
                            value={field.value || ''}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="smtp_port"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('settings:emailSettings.smtp.port')}</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="587"
                            {...field}
                            value={field.value || ''}
                            onChange={(e) =>
                              field.onChange(e.target.value ? parseInt(e.target.value) : null)
                            }
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="smtp_username"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('settings:emailSettings.smtp.username')}</FormLabel>
                        <FormControl>
                          <Input
                            placeholder={t('settings:emailSettings.smtp.usernamePlaceholder')}
                            {...field}
                            value={field.value || ''}
                          />
                        </FormControl>
                        {settings?.smtp_username && (
                          <FormDescription>
                            {t('settings:emailSettings.smtp.currentUsername')}: {settings.smtp_username}
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="smtp_password"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('settings:emailSettings.smtp.password')}</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder={t('settings:emailSettings.smtp.passwordPlaceholder')}
                            {...field}
                            value={field.value || ''}
                          />
                        </FormControl>
                        {settings?.smtp_password_set && (
                          <FormDescription className="flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3 text-green-500" />
                            {t('settings:emailSettings.smtp.passwordSet')}
                          </FormDescription>
                        )}
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
                <div className="flex gap-6">
                  <FormField
                    control={form.control}
                    name="smtp_use_tls"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2">
                        <FormControl>
                          <Switch checked={field.value ?? true} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">
                          {t('settings:emailSettings.smtp.useTls')}
                        </FormLabel>
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="smtp_use_ssl"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2">
                        <FormControl>
                          <Switch checked={field.value ?? false} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">
                          {t('settings:emailSettings.smtp.useSsl')}
                        </FormLabel>
                      </FormItem>
                    )}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* SendGrid Settings */}
          {selectedProvider === 'sendgrid' && (
            <Card>
              <CardHeader>
                <CardTitle>{t('settings:emailSettings.sendgrid.title')}</CardTitle>
                <CardDescription>{t('settings:emailSettings.sendgrid.description')}</CardDescription>
              </CardHeader>
              <CardContent>
                <FormField
                  control={form.control}
                  name="sendgrid_api_key"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('settings:emailSettings.sendgrid.apiKey')}</FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          placeholder={t('settings:emailSettings.sendgrid.apiKeyPlaceholder')}
                          {...field}
                          value={field.value || ''}
                        />
                      </FormControl>
                      {settings?.sendgrid_api_key_set && (
                        <FormDescription className="flex items-center gap-1">
                          <CheckCircle2 className="h-3 w-3 text-green-500" />
                          {t('settings:emailSettings.sendgrid.apiKeySet')}
                        </FormDescription>
                      )}
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          )}

          {/* Sender Branding */}
          <Card>
            <CardHeader>
              <CardTitle>{t('settings:emailSettings.branding.title')}</CardTitle>
              <CardDescription>{t('settings:emailSettings.branding.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {brandingLocked && (
                <Alert>
                  <AlertDescription>
                    {t('settings:emailSettings.branding.lockedHint')}
                  </AlertDescription>
                </Alert>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                <FormField
                  control={form.control}
                  name="sender_email"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('settings:emailSettings.branding.senderEmail')}</FormLabel>
                      <FormControl>
                        <Input
                          type="email"
                          placeholder="noreply@example.com"
                          {...field}
                          value={field.value || ''}
                          disabled={brandingLocked}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="sender_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('settings:emailSettings.branding.senderName')}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder={t('settings:emailSettings.branding.senderNamePlaceholder')}
                          {...field}
                          value={field.value || ''}
                          disabled={brandingLocked}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={form.control}
                name="reply_to_email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('settings:emailSettings.branding.replyTo')}</FormLabel>
                    <FormControl>
                      <Input
                        type="email"
                        placeholder="support@example.com"
                        {...field}
                        value={field.value || ''}
                        disabled={brandingLocked}
                      />
                    </FormControl>
                    <FormDescription>{t('settings:emailSettings.branding.replyToHint')}</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex justify-between">
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsTestDialogOpen(true)}
                disabled={isUpdating || isTesting}
              >
                <Send className="mr-2 h-4 w-4" />
                {t('settings:emailSettings.actions.testEmail')}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setIsResetDialogOpen(true)}
                disabled={isUpdating || isResetting || settings?.using_platform_defaults}
              >
                <RefreshCw className="mr-2 h-4 w-4" />
                {t('settings:emailSettings.actions.resetToDefaults')}
              </Button>
            </div>
            <Button type="submit" disabled={isUpdating}>
              {isUpdating
                ? t('common:saving')
                : t('settings:emailSettings.actions.saveChanges')}
            </Button>
          </div>
        </form>
      </Form>

      {/* Test Email Dialog */}
      <Dialog open={isTestDialogOpen} onOpenChange={setIsTestDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings:emailSettings.testDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('settings:emailSettings.testDialog.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <Input
              type="email"
              placeholder={t('settings:emailSettings.testDialog.emailPlaceholder')}
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsTestDialogOpen(false)}>
              {t('common:cancel')}
            </Button>
            <Button onClick={handleTest} disabled={isTesting || !testEmail}>
              {isTesting ? t('common:sending') : t('settings:emailSettings.testDialog.send')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Confirmation Dialog */}
      <ConfirmDialog
        open={isResetDialogOpen}
        onOpenChange={setIsResetDialogOpen}
        title={t('settings:emailSettings.resetDialog.title')}
        description={t('settings:emailSettings.resetDialog.description')}
        confirmLabel={t('settings:emailSettings.resetDialog.confirm')}
        cancelLabel={t('common:cancel')}
        onConfirm={handleReset}
        isLoading={isResetting}
        variant="destructive"
      />
    </div>
  )
}

export default EmailSettingsPage
