import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { ArrowUpDown } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { SortableList } from '@/components/SortableList'
import { MediaUploader } from '@/components/MediaUploader'
import { MediaUse } from '@/types/generated'
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
import {
  useGetAdminArticlesQuery,
  useGetHelpCategoriesQuery,
  useCreateArticleMutation,
  useUpdateArticleMutation,
  useDeleteArticleMutation,
  useReorderArticlesMutation,
} from '@/store/api/helpCenterApi'
import type { HelpArticle, ReorderItem } from '@/types/helpCenter'

const articleSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  slug: z.string().min(1, 'Slug is required').max(200).regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Slug must be lowercase letters, numbers, and single hyphens only (no leading, trailing, or consecutive hyphens)'),
  content: z.string().min(1, 'Content is required'),
  category_id: z.string().min(1, 'Category is required'),
  status: z.enum(['draft', 'published']),
  featured_image_url: z.string().url().optional().nullable().or(z.literal('')),
  is_platform_wide: z.boolean(),
})

type ArticleFormData = z.infer<typeof articleSchema>

function extractApiErrorMessage(error: unknown, fallbackMessage: string): string {
  const apiError = error as { data?: { detail?: string | Array<{ msg: string }> } }
  const detail = apiError.data?.detail
  if (Array.isArray(detail)) {
    return detail.map(e => e.msg).join(', ')
  }
  return detail || fallbackMessage
}

export function HelpArticlesPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const [isReorderMode, setIsReorderMode] = useState(false)
  const [pendingReorder, setPendingReorder] = useState<ReorderItem[] | null>(null)
  const pageSize = 10

  // Use a larger limit in reorder mode to get all items
  const { data, isLoading } = useGetAdminArticlesQuery({
    limit: isReorderMode ? 500 : pageSize,
    offset: isReorderMode ? 0 : (page - 1) * pageSize,
  })
  const { data: categoriesData } = useGetHelpCategoriesQuery()

  const [createArticle, { isLoading: isCreating }] = useCreateArticleMutation()
  const [updateArticle, { isLoading: isUpdating }] = useUpdateArticleMutation()
  const [deleteArticle, { isLoading: isDeleting }] = useDeleteArticleMutation()
  const [reorderArticles, { isLoading: isReordering }] = useReorderArticlesMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingArticle, setEditingArticle] = useState<HelpArticle | null>(null)
  const [deletingArticle, setDeletingArticle] = useState<HelpArticle | null>(null)
  const [previewArticle, setPreviewArticle] = useState<{ data: ArticleFormData; isCreate: boolean } | null>(null)

  const handleReorder = (reorderedItems: Array<HelpArticle & { display_order: number }>) => {
    setPendingReorder(
      reorderedItems.map((item) => ({
        id: item.id,
        display_order: item.display_order,
      }))
    )
  }

  const handleSaveOrder = async () => {
    if (!pendingReorder) return
    try {
      await reorderArticles({ items: pendingReorder }).unwrap()
      toast.success(t('helpCenter.articles.toast.reorderSuccess'))
      setIsReorderMode(false)
      setPendingReorder(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.articles.toast.reorderError')))
    }
  }

  const handleCancelReorder = () => {
    setIsReorderMode(false)
    setPendingReorder(null)
  }

  const form = useForm<ArticleFormData>({
    resolver: zodResolver(articleSchema),
    defaultValues: {
      title: '',
      slug: '',
      content: '',
      category_id: '',
      status: 'draft',
      featured_image_url: '',
      is_platform_wide: true,
    },
  })

  const handleCreatePreview = (data: ArticleFormData) => {
    setPreviewArticle({ data, isCreate: true })
  }

  const handleEditPreview = (data: ArticleFormData) => {
    setPreviewArticle({ data, isCreate: false })
  }

  const handleConfirmCreate = async () => {
    if (!previewArticle) return
    const data = previewArticle.data
    try {
      await createArticle({
        title: data.title,
        slug: data.slug,
        content: data.content,
        category_id: data.category_id,
        status: data.status,
        featured_image_url: data.featured_image_url || null,
        is_platform_wide: data.is_platform_wide,
        published_at: data.status === 'published' ? new Date().toISOString() : null,
      }).unwrap()
      toast.success(t('helpCenter.articles.toast.createSuccess'))
      setIsCreateOpen(false)
      setPreviewArticle(null)
      form.reset()
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.articles.toast.createError')))
    }
  }

  const handleConfirmEdit = async () => {
    if (!previewArticle || !editingArticle) return
    const data = previewArticle.data
    try {
      await updateArticle({
        id: editingArticle.id,
        body: {
          title: data.title,
          slug: data.slug,
          content: data.content,
          category_id: data.category_id,
          status: data.status,
          featured_image_url: data.featured_image_url || null,
          published_at: data.status === 'published' && !editingArticle.published_at ? new Date().toISOString() : undefined,
        },
      }).unwrap()
      toast.success(t('helpCenter.articles.toast.updateSuccess'))
      setEditingArticle(null)
      setPreviewArticle(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.articles.toast.updateError')))
    }
  }

  const handleConfirmSave = () => {
    if (previewArticle?.isCreate) {
      handleConfirmCreate()
    } else {
      handleConfirmEdit()
    }
  }

  // Parse markdown content for preview
  const previewContent = previewArticle?.data.content
  const previewHtmlContent = useMemo(() => {
    if (!previewContent) return ''
    const rawHtml = marked.parse(previewContent, { async: false }) as string
    return DOMPurify.sanitize(rawHtml, {
      ADD_TAGS: ['iframe'],
      ADD_ATTR: ['allow', 'allowfullscreen', 'frameborder', 'scrolling', 'target'],
    })
  }, [previewContent])

  const handleDelete = async () => {
    if (!deletingArticle) return
    try {
      await deleteArticle(deletingArticle.id).unwrap()
      toast.success(t('helpCenter.articles.toast.deleteSuccess'))
      setDeletingArticle(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.articles.toast.deleteError')))
    }
  }

  const openEditDialog = (article: HelpArticle) => {
    form.reset({
      title: article.title,
      slug: article.slug,
      content: article.content,
      category_id: article.category_id,
      status: article.status,
      featured_image_url: article.featured_image_url || '',
      is_platform_wide: article.is_platform_wide,
    })
    setEditingArticle(article)
  }

  const openCreateDialog = () => {
    form.reset({
      title: '',
      slug: '',
      content: '',
      category_id: '',
      status: 'draft',
      featured_image_url: '',
      is_platform_wide: true,
    })
    setIsCreateOpen(true)
  }

  const handleImageUploadSuccess = (_mediaId: string, mediaUrl: string | null) => {
    if (mediaUrl) {
      form.setValue('featured_image_url', mediaUrl)
    }
  }

  const columns: Column<HelpArticle>[] = [
    {
      key: 'title',
      header: t('helpCenter.articles.table.title'),
      cell: (article) => (
        <div className="max-w-[300px] truncate font-medium">{article.title}</div>
      ),
    },
    {
      key: 'slug',
      header: t('helpCenter.articles.table.slug'),
      cell: (article) => (
        <div className="max-w-[200px] truncate text-muted-foreground text-sm">{article.slug}</div>
      ),
    },
    {
      key: 'status',
      header: t('helpCenter.articles.table.status'),
      cell: (article) => (
        <Badge variant={article.status === 'published' ? 'default' : 'secondary'}>
          {t(`helpCenter.status.${article.status}`)}
        </Badge>
      ),
    },
    {
      key: 'scope',
      header: t('helpCenter.articles.table.scope'),
      cell: (article) => (
        <Badge variant={article.is_platform_wide ? 'default' : 'outline'}>
          {article.is_platform_wide ? t('helpCenter.scope.platform') : t('helpCenter.scope.organization')}
        </Badge>
      ),
    },
    {
      key: 'published',
      header: t('helpCenter.articles.table.published'),
      cell: (article) =>
        article.published_at
          ? new Date(article.published_at).toLocaleDateString()
          : '-',
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (article) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(article)}>
              {t('helpCenter.articles.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingArticle(article)}
              className="text-destructive"
            >
              {t('helpCenter.articles.actions.delete')}
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
            <FormLabel>{t('helpCenter.articles.form.title')}</FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="slug"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.articles.form.slug')}</FormLabel>
            <FormDescription>{t('helpCenter.articles.form.slugDescription')}</FormDescription>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="category_id"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.articles.form.category')}</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder={t('helpCenter.articles.form.categoryPlaceholder')} />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {categoriesData?.items.map((category) => (
                  <SelectItem key={category.id} value={category.id}>
                    {category.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="content"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.articles.form.content')}</FormLabel>
            <FormDescription>{t('helpCenter.articles.form.contentDescription')}</FormDescription>
            <FormControl>
              <Textarea {...field} rows={10} className="font-mono text-sm" />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="space-y-2">
        <FormLabel>{t('helpCenter.articles.form.featuredImage')} <span className="text-muted-foreground font-normal">({t('helpCenter.form.optional')})</span></FormLabel>
        <MediaUploader
          media_use={MediaUse.HELP_ARTICLE}
          onUploadSuccess={handleImageUploadSuccess}
          accept="image"
          maxSize={5 * 1024 * 1024}
          isPublic={true}
        />
        <FormField
          control={form.control}
          name="featured_image_url"
          render={({ field }) => (
            <FormItem>
              <FormDescription>{t('helpCenter.articles.form.imageUrlOrUpload')}</FormDescription>
              <FormControl>
                <Input {...field} value={field.value || ''} placeholder="https://..." />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="status"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('helpCenter.articles.form.status')}</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="draft">{t('helpCenter.status.draft')}</SelectItem>
                  <SelectItem value="published">{t('helpCenter.status.published')}</SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
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
                  <FormLabel>{t('helpCenter.articles.form.platformWide')}</FormLabel>
                  <FormDescription>{t('helpCenter.articles.form.platformWideDescription')}</FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />
        )}
      </div>
    </>
  )

  // Get category name helper
  const getCategoryName = (categoryId: string) => {
    return categoriesData?.items?.find((c) => c.id === categoryId)?.name || '-'
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('helpCenter.articles.pageTitle')}
        description={t('helpCenter.articles.pageDescription')}
      >
        <div className="flex gap-2">
          {isReorderMode ? (
            <>
              <Button variant="outline" onClick={handleCancelReorder} disabled={isReordering}>
                {t('helpCenter.reorder.cancel')}
              </Button>
              <Button onClick={handleSaveOrder} disabled={isReordering || !pendingReorder}>
                {isReordering ? t('helpCenter.reorder.saving') : t('helpCenter.reorder.saveOrder')}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setIsReorderMode(true)}>
                <ArrowUpDown className="h-4 w-4 mr-2" />
                {t('helpCenter.reorder.reorderButton')}
              </Button>
              <Button onClick={openCreateDialog}>{t('helpCenter.articles.createButton')}</Button>
            </>
          )}
        </div>
      </PageHeader>

      {isReorderMode ? (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            {t('helpCenter.reorder.instructions')}
          </p>
          <SortableList
            items={data?.items || []}
            onReorder={handleReorder}
            renderItem={(article) => (
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{article.title}</div>
                  <div className="text-sm text-muted-foreground truncate">
                    {getCategoryName(article.category_id)}
                  </div>
                </div>
                <Badge variant={article.status === 'published' ? 'default' : 'secondary'}>
                  {t(`helpCenter.status.${article.status}`)}
                </Badge>
              </div>
            )}
          />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={data?.items || []}
          isLoading={isLoading}
          emptyMessage={t('helpCenter.articles.emptyMessage')}
          pagination={{
            page,
            pageSize,
            total: data?.total || 0,
            onPageChange: setPage,
          }}
        />
      )}

      {/* Create Article Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.articles.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.articles.createDialog.description')}</DialogDescription>
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
                  {t('helpCenter.articles.createDialog.cancel')}
                </Button>
                <Button type="submit">
                  {t('helpCenter.articles.createDialog.preview')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Article Dialog */}
      <Dialog open={!!editingArticle} onOpenChange={() => setEditingArticle(null)}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.articles.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.articles.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEditPreview)} className="space-y-4">
              {renderFormFields(true)}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingArticle(null)}
                >
                  {t('helpCenter.articles.editDialog.cancel')}
                </Button>
                <Button type="submit">
                  {t('helpCenter.articles.editDialog.preview')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Preview Dialog */}
      <Dialog open={!!previewArticle} onOpenChange={() => setPreviewArticle(null)}>
        <DialogContent className="sm:max-w-6xl w-[90vw] max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.articles.previewDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.articles.previewDialog.description')}</DialogDescription>
          </DialogHeader>
          {previewArticle && (
            <div className="border rounded-lg p-6 bg-muted/30 space-y-4">
              <div>
                <h2 className="text-2xl font-bold">{previewArticle.data.title}</h2>
                <p className="text-sm text-muted-foreground">/{previewArticle.data.slug}</p>
              </div>
              {previewArticle.data.featured_image_url && (
                <img
                  src={previewArticle.data.featured_image_url}
                  alt={previewArticle.data.title}
                  className="w-full h-48 object-cover rounded-md"
                />
              )}
              <div
                className="prose prose-gray max-w-none dark:prose-invert prose-headings:font-semibold prose-a:text-primary prose-img:rounded-lg prose-pre:bg-muted"
                dangerouslySetInnerHTML={{ __html: previewHtmlContent }}
              />
            </div>
          )}
          <div className="flex justify-end gap-2 mt-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => setPreviewArticle(null)}
            >
              {t('helpCenter.articles.previewDialog.back')}
            </Button>
            <Button
              onClick={handleConfirmSave}
              disabled={isCreating || isUpdating}
            >
              {isCreating || isUpdating
                ? t('helpCenter.articles.previewDialog.saving')
                : t('helpCenter.articles.previewDialog.confirm')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingArticle}
        onOpenChange={() => setDeletingArticle(null)}
        title={t('helpCenter.articles.deleteDialog.title')}
        description={t('helpCenter.articles.deleteDialog.description', { title: deletingArticle?.title })}
        confirmLabel={t('helpCenter.articles.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
