import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { X } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { AnnouncementCard } from '@/components/AnnouncementCard'
import { MediaUploader } from '@/components/MediaUploader'
import { MediaUse } from '@/types/generated'
import { useDeleteFileMutation } from '@/features/files/filesApi'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { ColorPicker } from '@/components/ui/color-picker'
import {
  useGetAnnouncementsQuery,
  useCreateAnnouncementMutation,
  useUpdateAnnouncementMutation,
  useDeleteAnnouncementMutation,
} from '@/features/announcements/announcementsApi'
import type { Announcement, AnnouncementPriority } from '@/types/announcement'

const announcementSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  body: z.string().min(1, 'Body is required').max(2000),
  priority: z.enum(['critical', 'high', 'normal', 'low']),
  is_dismissible: z.boolean(),
  is_platform_wide: z.boolean(),
  background_color: z.string().optional().nullable(),
  text_color: z.string().optional().nullable(),
  featured_image_url: z.string().optional().nullable(),
  cta_text: z.string().max(100).optional().nullable(),
  cta_url: z.string().optional().nullable(),
  cta_dismisses: z.boolean(),
  cta_button_color: z.string().optional().nullable(),
  cta_button_variant: z.string().optional().nullable(),
  start_time: z.string().optional().nullable(),
  end_time: z.string().optional().nullable(),
})

interface UploadedImageInfo {
  mediaId: string
  url: string
  previewUrl: string // blob URL for local preview (authenticated access not required)
}

type AnnouncementFormData = z.infer<typeof announcementSchema>

const priorityColors: Record<AnnouncementPriority, string> = {
  critical: 'bg-red-500',
  high: 'bg-orange-500',
  normal: 'bg-blue-500',
  low: 'bg-gray-500',
}

type AnnouncementStatus = 'scheduled' | 'active' | 'expired'

/**
 * Determine the status of an announcement based on start_time and end_time
 */
function getAnnouncementStatus(announcement: Announcement): AnnouncementStatus {
  const now = new Date()

  if (announcement.start_time && new Date(announcement.start_time) > now) {
    return 'scheduled'
  }

  if (announcement.end_time && new Date(announcement.end_time) < now) {
    return 'expired'
  }

  return 'active'
}

const statusConfig: Record<AnnouncementStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; className?: string }> = {
  scheduled: { variant: 'outline', className: 'border-blue-500 text-blue-600' },
  active: { variant: 'default', className: 'bg-green-500 hover:bg-green-500/80' },
  expired: { variant: 'secondary', className: 'text-muted-foreground' },
}

/**
 * Extract error message from API error response
 */
function extractApiErrorMessage(error: unknown, fallbackMessage: string): string {
  const apiError = error as { data?: { detail?: string | Array<{ msg: string }> } }
  const detail = apiError.data?.detail
  if (Array.isArray(detail)) {
    return detail.map(e => e.msg).join(', ')
  }
  return detail || fallbackMessage
}

export function AnnouncementsPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data, isLoading } = useGetAnnouncementsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createAnnouncement, { isLoading: isCreating }] = useCreateAnnouncementMutation()
  const [updateAnnouncement, { isLoading: isUpdating }] = useUpdateAnnouncementMutation()
  const [deleteAnnouncement, { isLoading: isDeleting }] = useDeleteAnnouncementMutation()
  const [deleteFile] = useDeleteFileMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [uploadedImage, setUploadedImage] = useState<UploadedImageInfo | null>(null)
  const [editingAnnouncement, setEditingAnnouncement] = useState<Announcement | null>(null)
  const [deletingAnnouncement, setDeletingAnnouncement] = useState<Announcement | null>(null)
  const [previewData, setPreviewData] = useState<{ data: AnnouncementFormData; isCreate: boolean } | null>(null)

  const form = useForm<AnnouncementFormData>({
    resolver: zodResolver(announcementSchema),
    defaultValues: {
      title: '',
      body: '',
      priority: 'low',
      is_dismissible: true,
      is_platform_wide: false,
      background_color: '',
      text_color: '',
      featured_image_url: '',
      cta_text: '',
      cta_url: '',
      cta_dismisses: true,
      cta_button_color: '',
      cta_button_variant: '',
      start_time: '',
      end_time: '',
    },
  })

  // Show preview before creating
  const handleCreatePreview = (data: AnnouncementFormData) => {
    setPreviewData({ data, isCreate: true })
  }

  // Show preview before editing
  const handleEditPreview = (data: AnnouncementFormData) => {
    setPreviewData({ data, isCreate: false })
  }

  // Actually create the announcement after preview confirmation
  const handleConfirmCreate = async () => {
    if (!previewData) return
    const data = previewData.data
    try {
      await createAnnouncement({
        title: data.title,
        body: data.body,
        priority: data.priority,
        is_dismissible: data.is_dismissible,
        is_platform_wide: data.is_platform_wide,
        background_color: data.background_color || null,
        text_color: data.text_color || null,
        featured_image_url: data.featured_image_url || null,
        cta_text: data.cta_text || null,
        cta_url: data.cta_url || null,
        cta_dismisses: data.cta_dismisses,
        cta_button_color: data.cta_button_color || null,
        cta_button_variant: data.cta_button_variant || null,
        start_time: data.start_time || null,
        end_time: data.end_time || null,
      }).unwrap()
      toast.success(t('announcements.toast.createSuccess'))
      setIsCreateOpen(false)
      setPreviewData(null)
      form.reset()
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('announcements.toast.createError')))
    }
  }

  // Actually update the announcement after preview confirmation
  const handleConfirmEdit = async () => {
    if (!previewData || !editingAnnouncement) return
    const data = previewData.data
    try {
      await updateAnnouncement({
        id: editingAnnouncement.id,
        body: {
          title: data.title,
          body: data.body,
          priority: data.priority,
          is_dismissible: data.is_dismissible,
          background_color: data.background_color || null,
          text_color: data.text_color || null,
          featured_image_url: data.featured_image_url || null,
          cta_text: data.cta_text || null,
          cta_url: data.cta_url || null,
          cta_dismisses: data.cta_dismisses,
          cta_button_color: data.cta_button_color || null,
          cta_button_variant: data.cta_button_variant || null,
          start_time: data.start_time || null,
          end_time: data.end_time || null,
        },
      }).unwrap()
      toast.success(t('announcements.toast.updateSuccess'))
      setEditingAnnouncement(null)
      setPreviewData(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('announcements.toast.updateError')))
    }
  }

  const handleConfirmSave = () => {
    if (previewData?.isCreate) {
      handleConfirmCreate()
    } else {
      handleConfirmEdit()
    }
  }

  const handleDelete = async () => {
    if (!deletingAnnouncement) return
    try {
      await deleteAnnouncement(deletingAnnouncement.id).unwrap()
      toast.success(t('announcements.toast.deleteSuccess'))
      setDeletingAnnouncement(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('announcements.toast.deleteError')))
    }
  }

  const openEditDialog = (announcement: Announcement) => {
    form.reset({
      title: announcement.title,
      body: announcement.body,
      priority: announcement.priority,
      is_dismissible: announcement.is_dismissible,
      is_platform_wide: announcement.is_platform_wide,
      background_color: announcement.background_color || '',
      text_color: announcement.text_color || '',
      featured_image_url: announcement.featured_image_url || '',
      cta_text: announcement.cta_text || '',
      cta_url: announcement.cta_url || '',
      cta_dismisses: announcement.cta_dismisses,
      cta_button_color: announcement.cta_button_color || '',
      cta_button_variant: announcement.cta_button_variant || '',
      start_time: announcement.start_time ? announcement.start_time.slice(0, 16) : '',
      end_time: announcement.end_time ? announcement.end_time.slice(0, 16) : '',
    })
    // Set existing image if present (we don't have mediaId for existing images, so use empty string)
    // For existing images, use the URL directly as preview (may fail for local storage due to auth)
    if (announcement.featured_image_url) {
      setUploadedImage({ mediaId: '', url: announcement.featured_image_url, previewUrl: announcement.featured_image_url })
    } else {
      setUploadedImage(null)
    }
    setEditingAnnouncement(announcement)
  }

  const openCreateDialog = () => {
    form.reset({
      title: '',
      body: '',
      priority: 'low',
      is_dismissible: true,
      is_platform_wide: false,
      background_color: '',
      text_color: '',
      featured_image_url: '',
      cta_text: '',
      cta_url: '',
      cta_dismisses: true,
      cta_button_color: '',
      cta_button_variant: '',
      start_time: '',
      end_time: '',
    })
    setUploadedImage(null)
    setIsCreateOpen(true)
  }

  const handleImageUploadSuccess = (mediaId: string, mediaUrl: string | null, file: File) => {
    if (mediaUrl) {
      // Create a blob URL for local preview (doesn't require auth)
      const previewUrl = URL.createObjectURL(file)
      form.setValue('featured_image_url', mediaUrl)
      setUploadedImage({ mediaId, url: mediaUrl, previewUrl })
    }
  }

  const handleImageDelete = async () => {
    if (uploadedImage) {
      // Revoke the blob URL to prevent memory leaks
      if (uploadedImage.previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(uploadedImage.previewUrl)
      }
      // Only try to delete the file if we have a valid mediaId (not for existing announcements)
      if (uploadedImage.mediaId) {
        try {
          await deleteFile(uploadedImage.mediaId).unwrap()
        } catch {
          // File may not exist or already deleted, continue anyway
        }
      }
    }
    form.setValue('featured_image_url', '')
    setUploadedImage(null)
  }

  // Cleanup blob URLs on unmount
  useEffect(() => {
    return () => {
      if (uploadedImage?.previewUrl.startsWith('blob:')) {
        URL.revokeObjectURL(uploadedImage.previewUrl)
      }
    }
  }, [uploadedImage])

  // Create preview announcement object from form data
  const createPreviewAnnouncement = (data: AnnouncementFormData): Announcement => ({
    id: 'preview',
    organization_id: null,
    title: data.title,
    body: data.body,
    priority: data.priority,
    background_color: data.background_color || null,
    text_color: data.text_color || null,
    featured_image_url: data.featured_image_url || null,
    cta_text: data.cta_text || null,
    cta_url: data.cta_url || null,
    cta_dismisses: data.cta_dismisses,
    cta_button_color: data.cta_button_color || null,
    cta_button_variant: data.cta_button_variant || null,
    is_dismissible: data.is_dismissible,
    start_time: data.start_time || null,
    end_time: data.end_time || null,
    created_by_id: '',
    created_time: new Date().toISOString(),
    updated_time: null,
    is_platform_wide: data.is_platform_wide,
  })

  const columns: Column<Announcement>[] = [
    {
      key: 'title',
      header: t('announcements.table.title'),
      cell: (announcement) => (
        <div className="max-w-[200px] truncate">{announcement.title}</div>
      ),
    },
    {
      key: 'priority',
      header: t('announcements.table.priority'),
      cell: (announcement) => (
        <Badge className={priorityColors[announcement.priority]}>
          {announcement.priority}
        </Badge>
      ),
    },
    {
      key: 'status',
      header: t('announcements.table.status'),
      cell: (announcement) => {
        const status = getAnnouncementStatus(announcement)
        const config = statusConfig[status]
        return (
          <Badge variant={config.variant} className={config.className}>
            {t(`announcements.status.${status}`)}
          </Badge>
        )
      },
    },
    {
      key: 'scope',
      header: t('announcements.table.scope'),
      cell: (announcement) => (
        <Badge variant={announcement.is_platform_wide ? 'default' : 'secondary'}>
          {announcement.is_platform_wide ? t('announcements.scope.platform') : t('announcements.scope.organization')}
        </Badge>
      ),
    },
    {
      key: 'dismissible',
      header: t('announcements.table.dismissible'),
      cell: (announcement) => (
        <span>{announcement.is_dismissible ? t('common:yes') : t('common:no')}</span>
      ),
    },
    {
      key: 'created',
      header: t('announcements.table.created'),
      cell: (announcement) =>
        announcement.created_time
          ? new Date(announcement.created_time).toLocaleDateString()
          : '-',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (announcement) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(announcement)}>
              {t('announcements.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingAnnouncement(announcement)}
              className="text-destructive"
            >
              {t('announcements.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  const renderFormFields = (isEditing: boolean) => (
    <>
      <FormField
        control={form.control}
        name="title"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('announcements.form.title')}</FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="body"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('announcements.form.body')}</FormLabel>
            <FormControl>
              <Textarea {...field} rows={3} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="priority"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('announcements.form.priority')}</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                <SelectItem value="critical">{t('announcements.priority.critical')}</SelectItem>
                <SelectItem value="high">{t('announcements.priority.high')}</SelectItem>
                <SelectItem value="normal">{t('announcements.priority.normal')}</SelectItem>
                <SelectItem value="low">{t('announcements.priority.low')}</SelectItem>
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="background_color"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('announcements.form.backgroundColor')}</FormLabel>
              <FormDescription>{t('announcements.form.backgroundColorDescription')}</FormDescription>
              <FormControl>
                <ColorPicker
                  value={field.value || ''}
                  onChange={field.onChange}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="text_color"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('announcements.form.textColor')}</FormLabel>
              <FormDescription>{t('announcements.form.textColorDescription')}</FormDescription>
              <FormControl>
                <ColorPicker
                  value={field.value || ''}
                  onChange={field.onChange}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="is_dismissible"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <FormLabel>{t('announcements.form.dismissible')}</FormLabel>
                <FormDescription>{t('announcements.form.dismissibleDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
        {!isEditing && (
          <FormField
            control={form.control}
            name="is_platform_wide"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <FormLabel>{t('announcements.form.platformWide')}</FormLabel>
                  <FormDescription>{t('announcements.form.platformWideDescription')}</FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        )}
      </div>
      <div className="space-y-2">
        <FormLabel>{t('announcements.form.featuredImage')} <span className="text-muted-foreground font-normal">({t('announcements.form.optional')})</span></FormLabel>
        {uploadedImage ? (
          <div className="relative inline-block">
            <img
              src={uploadedImage.previewUrl}
              alt={t('announcements.form.featuredImageAlt')}
              className="h-32 w-auto rounded-lg border object-cover"
            />
            <button
              type="button"
              onClick={handleImageDelete}
              className="absolute -top-2 -right-2 rounded-full bg-destructive p-1 text-destructive-foreground shadow-sm hover:bg-destructive/90 transition-colors"
              aria-label={t('announcements.form.removeImage')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <MediaUploader
            media_use={MediaUse.ANNOUNCEMENT}
            onUploadSuccess={handleImageUploadSuccess}
            accept="image"
            maxSize={5 * 1024 * 1024}
          />
        )}
      </div>
      <div className="space-y-2">
        <h4 className="font-medium">{t('announcements.form.ctaSection')}</h4>
        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="cta_text"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('announcements.form.ctaText')}</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value || ''} placeholder="Learn More" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="cta_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('announcements.form.ctaUrl')}</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value || ''} placeholder="/page or https://..." />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="cta_dismisses"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <FormLabel>{t('announcements.form.ctaDismisses')}</FormLabel>
                <FormDescription>{t('announcements.form.ctaDismissesDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
      </div>
      <div className="space-y-2">
        <h4 className="font-medium">{t('announcements.form.schedulingSection')}</h4>
        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="start_time"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('announcements.form.startTime')}</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value || ''} type="datetime-local" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="end_time"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('announcements.form.endTime')}</FormLabel>
                <FormControl>
                  <Input {...field} value={field.value || ''} type="datetime-local" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </div>
    </>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('announcements.pageTitle')}
        description={t('announcements.pageDescription')}
      >
        <Button onClick={openCreateDialog}>{t('announcements.createButton')}</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage={t('announcements.emptyMessage')}
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Announcement Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('announcements.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('announcements.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreatePreview)} className="space-y-4">
              {renderFormFields(false)}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('announcements.createDialog.cancel')}
                </Button>
                <Button type="submit">
                  {t('announcements.createDialog.preview')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Announcement Dialog */}
      <Dialog open={!!editingAnnouncement} onOpenChange={() => setEditingAnnouncement(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('announcements.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('announcements.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEditPreview)} className="space-y-4">
              {renderFormFields(true)}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingAnnouncement(null)}
                >
                  {t('announcements.editDialog.cancel')}
                </Button>
                <Button type="submit">
                  {t('announcements.editDialog.preview')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Preview Confirmation Dialog */}
      <Dialog open={!!previewData} onOpenChange={() => setPreviewData(null)}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('announcements.previewDialog.title')}</DialogTitle>
            <DialogDescription>{t('announcements.previewDialog.description')}</DialogDescription>
          </DialogHeader>
          {previewData && (
            <div className="border rounded-lg overflow-hidden bg-muted/30">
              <AnnouncementCard announcement={createPreviewAnnouncement(previewData.data)} />
            </div>
          )}
          <div className="flex justify-end gap-2 mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setPreviewData(null)}
            >
              {t('announcements.previewDialog.back')}
            </Button>
            <Button
              onClick={handleConfirmSave}
              disabled={isCreating || isUpdating}
            >
              {isCreating || isUpdating
                ? t('announcements.previewDialog.saving')
                : t('announcements.previewDialog.confirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingAnnouncement}
        onOpenChange={() => setDeletingAnnouncement(null)}
        title={t('announcements.deleteDialog.title')}
        description={t('announcements.deleteDialog.description', { title: deletingAnnouncement?.title })}
        confirmLabel={t('announcements.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
