import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useGetNotificationSettingsQuery,
  useUpdateNotificationSettingsMutation,
} from '@/features/notifications/notificationsApi'

const settingsSchema = z.object({
  email_enabled: z.boolean(),
  sms_enabled: z.boolean(),
  whatsapp_enabled: z.boolean(),
  sms_provider: z.string().optional(),
  whatsapp_provider: z.string().optional(),
  notification_retention_days: z.number().int().min(1).max(365),
  sms_rate_limit: z.number().int().min(1),
  whatsapp_rate_limit: z.number().int().min(1),
  email_sender_name: z.string().max(255).optional(),
  sms_sender_id: z.string().max(20).optional(),
})

type SettingsFormData = z.infer<typeof settingsSchema>

export function NotificationSettingsPage() {
  const { data: settings, isLoading } = useGetNotificationSettingsQuery()
  const [updateSettings, { isLoading: isUpdating }] = useUpdateNotificationSettingsMutation()

  const form = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      email_enabled: true,
      sms_enabled: false,
      whatsapp_enabled: false,
      sms_provider: '',
      whatsapp_provider: '',
      notification_retention_days: 30,
      sms_rate_limit: 100,
      whatsapp_rate_limit: 100,
      email_sender_name: '',
      sms_sender_id: '',
    },
  })

  useEffect(() => {
    if (settings) {
      form.reset({
        email_enabled: settings.email_enabled,
        sms_enabled: settings.sms_enabled,
        whatsapp_enabled: settings.whatsapp_enabled,
        sms_provider: settings.sms_provider || '',
        whatsapp_provider: settings.whatsapp_provider || '',
        notification_retention_days: settings.notification_retention_days,
        sms_rate_limit: settings.sms_rate_limit,
        whatsapp_rate_limit: settings.whatsapp_rate_limit,
        email_sender_name: settings.email_sender_name || '',
        sms_sender_id: settings.sms_sender_id || '',
      })
    }
  }, [settings, form])

  const handleSubmit = async (data: SettingsFormData) => {
    try {
      await updateSettings({
        ...data,
        sms_provider: data.sms_provider || undefined,
        whatsapp_provider: data.whatsapp_provider || undefined,
        email_sender_name: data.email_sender_name || undefined,
        sms_sender_id: data.sms_sender_id || undefined,
      }).unwrap()
      toast.success('Settings updated successfully')
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update settings')
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notification Settings"
        description="Configure organization-wide notification settings"
      />

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Channel Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Channels</CardTitle>
              <CardDescription>Enable or disable notification channels</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="email_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Email</FormLabel>
                      <FormDescription>Send notifications via email</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="sms_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">SMS</FormLabel>
                      <FormDescription>Send notifications via SMS</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="whatsapp_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">WhatsApp</FormLabel>
                      <FormDescription>Send notifications via WhatsApp</FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Provider Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Providers</CardTitle>
              <CardDescription>Configure notification service providers</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="sms_provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>SMS Provider</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="aws_sns">AWS SNS</SelectItem>
                        <SelectItem value="twilio">Twilio</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="whatsapp_provider"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>WhatsApp Provider</FormLabel>
                    <Select onValueChange={field.onChange} value={field.value}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select provider" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="twilio">Twilio</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Sender Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Sender Information</CardTitle>
              <CardDescription>Configure sender names and IDs</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="email_sender_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email Sender Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Freespace Webapp" {...field} />
                    </FormControl>
                    <FormDescription>
                      The name that appears in the &quot;From&quot; field
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="sms_sender_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>SMS Sender ID</FormLabel>
                    <FormControl>
                      <Input placeholder="FREESPACE" maxLength={11} {...field} />
                    </FormControl>
                    <FormDescription>
                      Alphanumeric sender ID (max 11 characters)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Rate Limits */}
          <Card>
            <CardHeader>
              <CardTitle>Rate Limits</CardTitle>
              <CardDescription>Set daily limits for notifications per user</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="sms_rate_limit"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>SMS Daily Limit</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 1)}
                      />
                    </FormControl>
                    <FormDescription>Max SMS per user per day</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="whatsapp_rate_limit"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>WhatsApp Daily Limit</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 1)}
                      />
                    </FormControl>
                    <FormDescription>Max WhatsApp messages per user per day</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Retention */}
          <Card>
            <CardHeader>
              <CardTitle>Data Retention</CardTitle>
              <CardDescription>Configure how long notification data is kept</CardDescription>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="notification_retention_days"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Retention Period (days)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={365}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 30)}
                      />
                    </FormControl>
                    <FormDescription>
                      Notification history is deleted after this many days
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <div className="flex justify-end">
            <Button type="submit" disabled={isUpdating}>
              {isUpdating ? 'Saving...' : 'Save Settings'}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
