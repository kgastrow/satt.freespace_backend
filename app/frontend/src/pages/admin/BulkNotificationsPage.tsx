import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Plus, XCircle } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  useGetNotificationsQuery,
  useCreateBulkNotificationMutation,
  useCancelBulkNotificationMutation,
  useGetTemplatesQuery,
  type BulkNotification,
  type NotificationChannel,
} from '@/features/notifications/notificationsApi'

const bulkSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  channel: z.enum(['email', 'sms', 'whatsapp', 'in_app']),
  useTemplate: z.boolean(),
  template_code: z.string().optional(),
  subject: z.string().optional(),
  body_text: z.string().optional(),
  verified_contact_only: z.boolean(),
})

type BulkFormData = z.infer<typeof bulkSchema>

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-500/10 text-yellow-600 dark:bg-yellow-500/20 dark:text-yellow-400',
  processing: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
  completed: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
  failed: 'bg-red-500/10 text-red-600 dark:bg-red-500/20 dark:text-red-400',
  cancelled: 'bg-muted text-muted-foreground',
}

export function BulkNotificationsPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [cancellingId, setCancellingId] = useState<string | null>(null)
  const [selectedChannel, setSelectedChannel] = useState<NotificationChannel>('email')
  const pageSize = 10

  // For now, we'll simulate bulk notifications list
  // In a real app, you'd have a separate endpoint for listing bulk notifications
  const { isLoading } = useGetNotificationsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const { data: templatesData } = useGetTemplatesQuery({
    channel: selectedChannel,
    limit: 100,
  })

  const [createBulk, { isLoading: isCreating }] = useCreateBulkNotificationMutation()
  const [cancelBulk, { isLoading: isCancelling }] = useCancelBulkNotificationMutation()

  const form = useForm<BulkFormData>({
    resolver: zodResolver(bulkSchema),
    defaultValues: {
      name: '',
      channel: 'email',
      useTemplate: true,
      template_code: '',
      subject: '',
      body_text: '',
      verified_contact_only: true,
    },
  })

  const useTemplateValue = useWatch({ control: form.control, name: 'useTemplate' })

  // Mirrors the backend's CHANNEL_VERIFICATION_COLUMN: the recipient filter
  // checks the contact address the chosen channel actually delivers to, so the
  // copy must name that address rather than always saying "email".
  const verificationContactKey: 'email' | 'phone' | 'none' =
    selectedChannel === 'email'
      ? 'email'
      : selectedChannel === 'sms' || selectedChannel === 'whatsapp'
        ? 'phone'
        : 'none'

  // Simulated bulk notifications for display
  const bulkNotifications: BulkNotification[] = [
    {
      id: '1',
      name: 'Welcome Campaign',
      channel: 'email',
      status: 'completed',
      total_recipients: 1250,
      sent_count: 1245,
      failed_count: 5,
      scheduled_time: null,
      started_time: '2024-01-15T10:00:00Z',
      completed_time: '2024-01-15T10:15:00Z',
      created_time: '2024-01-15T09:55:00Z',
    },
    {
      id: '2',
      name: 'System Maintenance Notice',
      channel: 'email',
      status: 'processing',
      total_recipients: 5000,
      sent_count: 2500,
      failed_count: 10,
      scheduled_time: null,
      started_time: '2024-01-16T14:00:00Z',
      completed_time: null,
      created_time: '2024-01-16T13:55:00Z',
    },
    {
      id: '3',
      name: 'SMS Alert',
      channel: 'sms',
      status: 'pending',
      total_recipients: 500,
      sent_count: 0,
      failed_count: 0,
      scheduled_time: '2024-01-17T09:00:00Z',
      started_time: null,
      completed_time: null,
      created_time: '2024-01-16T16:00:00Z',
    },
  ]

  const handleCreate = async (formData: BulkFormData) => {
    try {
      await createBulk({
        name: formData.name,
        channel: formData.channel,
        template_code: formData.useTemplate ? formData.template_code : undefined,
        subject: !formData.useTemplate ? formData.subject : undefined,
        body_text: !formData.useTemplate ? formData.body_text : undefined,
        recipient_filters: {
          verified_contact_only: formData.verified_contact_only,
        },
      }).unwrap()
      toast.success('Bulk notification created')
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to create bulk notification')
    }
  }

  const handleCancel = async () => {
    if (!cancellingId) return
    try {
      await cancelBulk(cancellingId).unwrap()
      toast.success('Bulk notification cancelled')
      setCancellingId(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to cancel bulk notification')
    }
  }

  const columns: Column<BulkNotification>[] = [
    {
      key: 'name',
      header: 'Campaign',
      cell: (bulk) => (
        <div>
          <p className="font-medium">{bulk.name}</p>
          <p className="text-sm text-muted-foreground capitalize">{bulk.channel}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cell: (bulk) => <Badge className={statusColors[bulk.status]}>{bulk.status}</Badge>,
    },
    {
      key: 'progress',
      header: 'Progress',
      cell: (bulk) => {
        const progress =
          bulk.total_recipients > 0
            ? Math.min(Math.round((bulk.sent_count / bulk.total_recipients) * 100), 100)
            : 0
        return (
          <div className="w-32">
            <Progress value={progress} className="h-2" />
            <p className="text-xs text-muted-foreground mt-1">
              {bulk.sent_count.toLocaleString()} / {bulk.total_recipients.toLocaleString()}
            </p>
          </div>
        )
      },
    },
    {
      key: 'failed',
      header: 'Failed',
      cell: (bulk) => (
        <span className={bulk.failed_count > 0 ? 'text-red-600 dark:text-red-400' : ''}>
          {bulk.failed_count.toLocaleString()}
        </span>
      ),
    },
    {
      key: 'created_time',
      header: 'Created',
      cell: (bulk) => bulk.created_time ? new Date(bulk.created_time).toLocaleDateString() : '-',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[100px]',
      cell: (bulk) =>
        (bulk.status === 'pending' || bulk.status === 'processing') && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCancellingId(bulk.id)}
            className="text-destructive"
          >
            <XCircle className="h-4 w-4 mr-1" />
            Cancel
          </Button>
        ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader title="Bulk Notifications" description="Create and manage bulk notification campaigns">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          New Campaign
        </Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={bulkNotifications}
        isLoading={isLoading}
        emptyMessage="No bulk notifications found"
        pagination={{
          page,
          pageSize,
          total: bulkNotifications.length,
          onPageChange: setPage,
        }}
      />

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Create Bulk Notification</DialogTitle>
            <DialogDescription>
              Send a notification to multiple recipients at once
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Campaign Name</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., Welcome Campaign" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="channel"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Channel</FormLabel>
                    <Select
                      onValueChange={(value) => {
                        field.onChange(value)
                        setSelectedChannel(value as NotificationChannel)
                      }}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="email">Email</SelectItem>
                        <SelectItem value="sms">SMS</SelectItem>
                        <SelectItem value="whatsapp">WhatsApp</SelectItem>
                        <SelectItem value="in_app">In-App</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="useTemplate"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Content Source</FormLabel>
                    <Select
                      onValueChange={(value) => field.onChange(value === 'template')}
                      value={field.value ? 'template' : 'custom'}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="template">Use Template</SelectItem>
                        <SelectItem value="custom">Custom Content</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {useTemplateValue ? (
                <FormField
                  control={form.control}
                  name="template_code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Template</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select a template" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {templatesData?.items.map((template) => (
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
                  {selectedChannel === 'email' && (
                    <FormField
                      control={form.control}
                      name="subject"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Subject</FormLabel>
                          <FormControl>
                            <Input {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}

                  <FormField
                    control={form.control}
                    name="body_text"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Message</FormLabel>
                        <FormControl>
                          <Textarea rows={4} {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}

              <FormField
                control={form.control}
                name="verified_contact_only"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-center gap-2">
                      <FormControl>
                        <input
                          type="checkbox"
                          checked={field.value}
                          onChange={field.onChange}
                          className="h-4 w-4"
                        />
                      </FormControl>
                      <FormLabel className="!mt-0">
                        {t('notifications.bulk.verifiedContact.label')}
                      </FormLabel>
                    </div>
                    <FormDescription>
                      {/* Which contact field is checked depends on the channel,
                          so say which one rather than always claiming "email". */}
                      {t(
                        `notifications.bulk.verifiedContact.description.${verificationContactKey}`
                      )}
                    </FormDescription>
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? 'Creating...' : 'Create Campaign'}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Cancel Confirmation */}
      <ConfirmDialog
        open={!!cancellingId}
        onOpenChange={() => setCancellingId(null)}
        title="Cancel Bulk Notification"
        description="Are you sure you want to cancel this bulk notification? Any pending messages will not be sent."
        confirmLabel="Cancel Campaign"
        onConfirm={handleCancel}
        isLoading={isCancelling}
        variant="destructive"
      />
    </div>
  )
}
