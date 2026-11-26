import { useState } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Plus, Pencil, Trash2, Eye, Lock } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  useGetTemplatesQuery,
  useCreateTemplateMutation,
  useUpdateTemplateMutation,
  useDeleteTemplateMutation,
  type NotificationTemplate,
  type NotificationChannel,
} from '@/features/notifications/notificationsApi'

const templateSchema = z.object({
  code: z.string().min(1, 'Code is required').max(100),
  name: z.string().min(1, 'Name is required').max(255),
  description: z.string().optional(),
  channel: z.enum(['email', 'sms', 'whatsapp', 'in_app']),
  subject: z.string().max(255).optional(),
  body_text: z.string().min(1, 'Body text is required'),
  body_html: z.string().optional(),
  is_active: z.boolean(),
})

const editTemplateSchema = templateSchema.omit({ code: true, channel: true })

type TemplateFormData = z.infer<typeof templateSchema>
type EditTemplateFormData = z.infer<typeof editTemplateSchema>

const channelColors: Record<NotificationChannel, string> = {
  email: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
  sms: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
  whatsapp: 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400',
  in_app: 'bg-purple-500/10 text-purple-600 dark:bg-purple-500/20 dark:text-purple-400',
}

export function TemplatesPage() {
  const [page, setPage] = useState(1)
  const [channelFilter, setChannelFilter] = useState<NotificationChannel | 'all'>('all')
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<NotificationTemplate | null>(null)
  const [deletingTemplate, setDeletingTemplate] = useState<NotificationTemplate | null>(null)
  const [previewTemplate, setPreviewTemplate] = useState<NotificationTemplate | null>(null)
  const pageSize = 10

  const { data, isLoading } = useGetTemplatesQuery({
    channel: channelFilter === 'all' ? undefined : channelFilter,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createTemplate, { isLoading: isCreating }] = useCreateTemplateMutation()
  const [updateTemplate, { isLoading: isUpdating }] = useUpdateTemplateMutation()
  const [deleteTemplate, { isLoading: isDeleting }] = useDeleteTemplateMutation()

  const createForm = useForm<TemplateFormData>({
    resolver: zodResolver(templateSchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
      channel: 'email',
      subject: '',
      body_text: '',
      body_html: '',
      is_active: true,
    },
  })

  const editForm = useForm<EditTemplateFormData>({
    resolver: zodResolver(editTemplateSchema),
    defaultValues: {
      name: '',
      description: '',
      subject: '',
      body_text: '',
      body_html: '',
      is_active: true,
    },
  })

  const handleCreate = async (formData: TemplateFormData) => {
    try {
      await createTemplate({
        ...formData,
        description: formData.description || undefined,
        subject: formData.subject || undefined,
        body_html: formData.body_html || undefined,
      }).unwrap()
      toast.success('Template created successfully')
      setIsCreateOpen(false)
      createForm.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to create template')
    }
  }

  const handleEdit = async (formData: EditTemplateFormData) => {
    if (!editingTemplate) return
    try {
      await updateTemplate({
        id: editingTemplate.id,
        data: {
          name: formData.name,
          description: formData.description || undefined,
          subject: formData.subject || undefined,
          body_text: formData.body_text,
          body_html: formData.body_html || undefined,
          is_active: formData.is_active,
        },
      }).unwrap()
      toast.success('Template updated successfully')
      setEditingTemplate(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update template')
    }
  }

  const handleDelete = async () => {
    if (!deletingTemplate) return
    try {
      await deleteTemplate(deletingTemplate.id).unwrap()
      toast.success('Template deleted successfully')
      setDeletingTemplate(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to delete template')
    }
  }

  const openEditDialog = (template: NotificationTemplate) => {
    editForm.reset({
      name: template.name,
      description: template.description || '',
      subject: template.subject || '',
      body_text: template.body_text,
      body_html: template.body_html || '',
      is_active: template.is_active,
    })
    setEditingTemplate(template)
  }

  const columns: Column<NotificationTemplate>[] = [
    {
      key: 'name',
      header: 'Template',
      cell: (template) => (
        <div className="flex items-center gap-2">
          {template.organization_id === null && (
            <Lock className="h-4 w-4 text-muted-foreground" aria-label="System template" />
          )}
          <div>
            <p className="font-medium">{template.name}</p>
            <p className="text-sm text-muted-foreground">{template.code}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'channel',
      header: 'Channel',
      cell: (template) => {
        const channel = template.channel as NotificationChannel
        const colorClass = channelColors[channel] || ''
        return <Badge className={colorClass}>{template.channel}</Badge>
      },
    },
    {
      key: 'status',
      header: 'Status',
      cell: (template) => (
        <Badge variant={template.is_active ? 'default' : 'secondary'}>
          {template.is_active ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (template) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setPreviewTemplate(template)}>
              <Eye className="h-4 w-4 mr-2" />
              Preview
            </DropdownMenuItem>
            {template.organization_id !== null && (
              <>
                <DropdownMenuItem onClick={() => openEditDialog(template)}>
                  <Pencil className="h-4 w-4 mr-2" />
                  Edit
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => setDeletingTemplate(template)}
                  className="text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  const selectedChannel = useWatch({ control: createForm.control, name: 'channel' })

  return (
    <div className="space-y-6">
      <PageHeader title="Notification Templates" description="Manage notification templates">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Template
        </Button>
      </PageHeader>

      <Tabs value={channelFilter} onValueChange={(v) => setChannelFilter(v as NotificationChannel | 'all')}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="email">Email</TabsTrigger>
          <TabsTrigger value="sms">SMS</TabsTrigger>
          <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
          <TabsTrigger value="in_app">In-App</TabsTrigger>
        </TabsList>
      </Tabs>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage="No templates found"
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] p-0">
          <DialogHeader className="px-6 pt-6">
            <DialogTitle>Create Template</DialogTitle>
            <DialogDescription>Create a new notification template</DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[calc(90vh-8rem)] px-6 pb-6">
          <Form {...createForm}>
            <form onSubmit={createForm.handleSubmit(handleCreate)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={createForm.control}
                  name="code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Code</FormLabel>
                      <FormControl>
                        <Input placeholder="welcome_email" {...field} />
                      </FormControl>
                      <FormDescription>Unique identifier</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={createForm.control}
                  name="channel"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Channel</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
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
              </div>

              <FormField
                control={createForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Welcome Email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Input placeholder="Sent to new users after registration" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {selectedChannel === 'email' && (
                <FormField
                  control={createForm.control}
                  name="subject"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Subject</FormLabel>
                      <FormControl>
                        <Input placeholder="Welcome to {{app_name}}!" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={createForm.control}
                name="body_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Body (Text)</FormLabel>
                    <FormControl>
                      <Textarea rows={4} placeholder="Hello {{name}}..." {...field} />
                    </FormControl>
                    <FormDescription>Use {"{{variable}}"} for dynamic content</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {selectedChannel === 'email' && (
                <FormField
                  control={createForm.control}
                  name="body_html"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Body (HTML)</FormLabel>
                      <FormControl>
                        <Textarea rows={6} placeholder="<html>...</html>" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={createForm.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-2">
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                    <FormLabel className="!mt-0">Active</FormLabel>
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setIsCreateOpen(false)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? 'Creating...' : 'Create'}
                </Button>
              </div>
            </form>
          </Form>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingTemplate} onOpenChange={() => setEditingTemplate(null)}>
        <DialogContent className="sm:max-w-[700px] max-h-[90vh] p-0">
          <DialogHeader className="px-6 pt-6">
            <DialogTitle>Edit Template</DialogTitle>
            <DialogDescription>Update template: {editingTemplate?.code}</DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[calc(90vh-8rem)] px-6 pb-6">
          <Form {...editForm}>
            <form onSubmit={editForm.handleSubmit(handleEdit)} className="space-y-4">
              <FormField
                control={editForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {editingTemplate?.channel === 'email' && (
                <FormField
                  control={editForm.control}
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
                control={editForm.control}
                name="body_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Body (Text)</FormLabel>
                    <FormControl>
                      <Textarea rows={4} {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {editingTemplate?.channel === 'email' && (
                <FormField
                  control={editForm.control}
                  name="body_html"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Body (HTML)</FormLabel>
                      <FormControl>
                        <Textarea rows={6} {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              <FormField
                control={editForm.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center gap-2">
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                    <FormLabel className="!mt-0">Active</FormLabel>
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setEditingTemplate(null)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? 'Saving...' : 'Save'}
                </Button>
              </div>
            </form>
          </Form>
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={!!previewTemplate} onOpenChange={() => setPreviewTemplate(null)}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>{previewTemplate?.name}</DialogTitle>
            <DialogDescription>Template preview</DialogDescription>
          </DialogHeader>
          {previewTemplate && (
            <div className="space-y-4">
              {previewTemplate.subject && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Subject</p>
                  <p>{previewTemplate.subject}</p>
                </div>
              )}
              <div>
                <p className="text-sm font-medium text-muted-foreground">Body</p>
                <pre className="mt-2 p-4 bg-muted rounded-lg text-sm whitespace-pre-wrap">
                  {previewTemplate.body_text}
                </pre>
              </div>
              {previewTemplate.variables && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Variables</p>
                  <pre className="mt-2 p-4 bg-muted rounded-lg text-sm">
                    {JSON.stringify(previewTemplate.variables, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingTemplate}
        onOpenChange={() => setDeletingTemplate(null)}
        title="Delete Template"
        description={`Are you sure you want to delete "${deletingTemplate?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
