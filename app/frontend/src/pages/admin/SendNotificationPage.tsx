import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
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
  useSendNotificationMutation,
  useGetTemplatesQuery,
  type NotificationChannel,
} from '@/features/notifications/notificationsApi'
import { useGetUsersQuery } from '@/features/users/usersApi'
import { useAppSelector } from '@/store/hooks'
import { UserCombobox } from '@/components/UserCombobox'

const sendSchema = z.object({
  channel: z.enum(['email', 'sms', 'whatsapp', 'in_app']),
  user_id: z.string().min(1, 'User is required'),
  useTemplate: z.boolean(),
  template_code: z.string().optional(),
  subject: z.string().optional(),
  content: z.string().optional(),
  is_urgent: z.boolean(),
})

type SendFormData = z.infer<typeof sendSchema>

export function SendNotificationPage() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const [sendNotification, { isLoading }] = useSendNotificationMutation()
  const [selectedChannel, setSelectedChannel] = useState<NotificationChannel>('email')

  const { data: templatesData } = useGetTemplatesQuery({
    channel: selectedChannel,
    limit: 100,
  })

  // Fetch users for recipient selection
  const { data: usersData, isLoading: isLoadingUsers } = useGetUsersQuery({ limit: 100 })

  // Get current user to highlight them in the list
  const currentUser = useAppSelector((state) => state.auth.user)

  const form = useForm<SendFormData>({
    resolver: zodResolver(sendSchema),
    defaultValues: {
      channel: 'email',
      user_id: '',
      useTemplate: false,
      template_code: '',
      subject: '',
      content: '',
      is_urgent: false,
    },
  })

  const useTemplateValue = useWatch({ control: form.control, name: 'useTemplate' })

  const handleSubmit = async (data: SendFormData) => {
    try {
      await sendNotification({
        channel: data.channel,
        user_id: data.user_id,
        template_code: data.useTemplate ? data.template_code : undefined,
        subject: !data.useTemplate ? data.subject : undefined,
        content: !data.useTemplate ? data.content : undefined,
        is_urgent: data.is_urgent,
      }).unwrap()
      toast.success(t('notifications.send.toast.success'))
      navigate('/admin/notifications')
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('notifications.send.toast.error'))
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t('notifications.send.pageTitle')} description={t('notifications.send.pageDescription')}>
        <Button variant="outline" onClick={() => navigate('/admin/notifications')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          {t('notifications.send.backButton')}
        </Button>
      </PageHeader>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{t('notifications.send.channelSection.title')}</CardTitle>
              <CardDescription>{t('notifications.send.channelSection.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="channel"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('notifications.send.channelSection.channel')}</FormLabel>
                    <Select
                      onValueChange={(value) => {
                        field.onChange(value)
                        setSelectedChannel(value as NotificationChannel)
                      }}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder={t('notifications.send.channelSection.channelPlaceholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="email">{t('notifications.filters.email')}</SelectItem>
                        <SelectItem value="sms">{t('notifications.filters.sms')}</SelectItem>
                        <SelectItem value="whatsapp">{t('notifications.filters.whatsapp')}</SelectItem>
                        <SelectItem value="in_app">{t('notifications.filters.inApp')}</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="user_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('notifications.send.channelSection.recipient')}</FormLabel>
                    <FormControl>
                      <UserCombobox
                        users={usersData?.items ?? []}
                        value={field.value}
                        onChange={field.onChange}
                        isLoading={isLoadingUsers}
                        currentUserId={currentUser?.id}
                        placeholder={t('notifications.send.channelSection.userPlaceholder')}
                        searchPlaceholder={t('notifications.send.channelSection.searchUsers')}
                        emptyMessage={t('notifications.send.channelSection.noUsersFound')}
                        requirePhone={selectedChannel === 'sms' || selectedChannel === 'whatsapp'}
                      />
                    </FormControl>
                    <FormDescription>
                      {t('notifications.send.channelSection.recipientUserDescription')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('notifications.send.contentSection.title')}</CardTitle>
              <CardDescription>{t('notifications.send.contentSection.description')}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="useTemplate"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">{t('notifications.send.contentSection.useTemplate')}</FormLabel>
                      <FormDescription>
                        {t('notifications.send.contentSection.useTemplateDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {useTemplateValue ? (
                <FormField
                  control={form.control}
                  name="template_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('notifications.send.contentSection.template')}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder={t('notifications.send.contentSection.templatePlaceholder')} />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {templatesData?.items.map((template: { id: string; code: string; name: string }) => (
                            <SelectItem key={template.id} value={template.code}>
                              {template.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ) : (
                <>
                  {(selectedChannel === 'email' || selectedChannel === 'in_app') && (
                    <FormField
                      control={form.control}
                      name="subject"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>
                            {selectedChannel === 'email'
                              ? t('notifications.send.contentSection.subject')
                              : t('notifications.send.contentSection.title', 'Title')}
                          </FormLabel>
                          <FormControl>
                            <Input
                              placeholder={
                                selectedChannel === 'email'
                                  ? t('notifications.send.contentSection.subjectPlaceholder')
                                  : t('notifications.send.contentSection.titlePlaceholder', 'Notification title')
                              }
                              {...field}
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="content"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('notifications.send.contentSection.message')}</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder={t('notifications.send.contentSection.messagePlaceholder')}
                            rows={6}
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('notifications.send.optionsSection.title')}</CardTitle>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="is_urgent"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">{t('notifications.send.optionsSection.urgent')}</FormLabel>
                      <FormDescription>
                        {t('notifications.send.optionsSection.urgentDescription')}
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <div className="flex justify-end gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/admin/notifications')}
            >
              {t('notifications.send.actions.cancel')}
            </Button>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? t('notifications.send.actions.sending') : t('notifications.send.actions.send')}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
