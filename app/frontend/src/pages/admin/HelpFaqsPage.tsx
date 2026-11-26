import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { ArrowUpDown } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { SortableList } from '@/components/SortableList'
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
  useGetAdminFaqsQuery,
  useGetHelpCategoriesQuery,
  useCreateFaqMutation,
  useUpdateFaqMutation,
  useDeleteFaqMutation,
  useReorderFaqsMutation,
} from '@/store/api/helpCenterApi'
import type { HelpFaq, ReorderItem } from '@/types/helpCenter'

const faqSchema = z.object({
  question: z.string().min(1, 'Question is required').max(500),
  answer: z.string().min(1, 'Answer is required'),
  category_id: z.string().min(1, 'Category is required'),
  status: z.enum(['draft', 'published']),
  display_order: z.number().min(0),
  is_platform_wide: z.boolean(),
})

type FaqFormData = z.infer<typeof faqSchema>

function extractApiErrorMessage(error: unknown, fallbackMessage: string): string {
  const apiError = error as { data?: { detail?: string | Array<{ msg: string }> } }
  const detail = apiError.data?.detail
  if (Array.isArray(detail)) {
    return detail.map(e => e.msg).join(', ')
  }
  return detail || fallbackMessage
}

export function HelpFaqsPage() {
  const { t } = useTranslation('admin')
  const [page, setPage] = useState(1)
  const [isReorderMode, setIsReorderMode] = useState(false)
  const [pendingReorder, setPendingReorder] = useState<ReorderItem[] | null>(null)
  const pageSize = 20

  // Use a larger limit in reorder mode to get all items
  const { data, isLoading } = useGetAdminFaqsQuery({
    limit: isReorderMode ? 500 : pageSize,
    offset: isReorderMode ? 0 : (page - 1) * pageSize,
  })
  const { data: categoriesData } = useGetHelpCategoriesQuery()

  const [createFaq, { isLoading: isCreating }] = useCreateFaqMutation()
  const [updateFaq, { isLoading: isUpdating }] = useUpdateFaqMutation()
  const [deleteFaq, { isLoading: isDeleting }] = useDeleteFaqMutation()
  const [reorderFaqs, { isLoading: isReordering }] = useReorderFaqsMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingFaq, setEditingFaq] = useState<HelpFaq | null>(null)
  const [deletingFaq, setDeletingFaq] = useState<HelpFaq | null>(null)

  const handleReorder = (reorderedItems: Array<HelpFaq & { display_order: number }>) => {
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
      await reorderFaqs({ items: pendingReorder }).unwrap()
      toast.success(t('helpCenter.faqs.toast.reorderSuccess'))
      setIsReorderMode(false)
      setPendingReorder(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.faqs.toast.reorderError')))
    }
  }

  const handleCancelReorder = () => {
    setIsReorderMode(false)
    setPendingReorder(null)
  }

  const form = useForm<FaqFormData>({
    resolver: zodResolver(faqSchema),
    defaultValues: {
      question: '',
      answer: '',
      category_id: '',
      status: 'draft',
      display_order: 0,
      is_platform_wide: true,
    },
  })

  const handleCreate = async (data: FaqFormData) => {
    try {
      await createFaq({
        question: data.question,
        answer: data.answer,
        category_id: data.category_id,
        status: data.status,
        display_order: data.display_order,
        is_platform_wide: data.is_platform_wide,
      }).unwrap()
      toast.success(t('helpCenter.faqs.toast.createSuccess'))
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.faqs.toast.createError')))
    }
  }

  const handleEdit = async (data: FaqFormData) => {
    if (!editingFaq) return
    try {
      await updateFaq({
        id: editingFaq.id,
        body: {
          question: data.question,
          answer: data.answer,
          category_id: data.category_id,
          status: data.status,
          display_order: data.display_order,
        },
      }).unwrap()
      toast.success(t('helpCenter.faqs.toast.updateSuccess'))
      setEditingFaq(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.faqs.toast.updateError')))
    }
  }

  const handleDelete = async () => {
    if (!deletingFaq) return
    try {
      await deleteFaq(deletingFaq.id).unwrap()
      toast.success(t('helpCenter.faqs.toast.deleteSuccess'))
      setDeletingFaq(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.faqs.toast.deleteError')))
    }
  }

  const openEditDialog = (faq: HelpFaq) => {
    form.reset({
      question: faq.question,
      answer: faq.answer,
      category_id: faq.category_id,
      status: faq.status,
      display_order: faq.display_order,
      is_platform_wide: faq.is_platform_wide,
    })
    setEditingFaq(faq)
  }

  const openCreateDialog = () => {
    form.reset({
      question: '',
      answer: '',
      category_id: '',
      status: 'draft',
      display_order: 0,
      is_platform_wide: true,
    })
    setIsCreateOpen(true)
  }

  const columns: Column<HelpFaq>[] = [
    {
      key: 'order',
      header: t('helpCenter.faqs.table.order'),
      className: 'w-[80px]',
      cell: (faq) => (
        <span className="text-muted-foreground">{faq.display_order}</span>
      ),
    },
    {
      key: 'question',
      header: t('helpCenter.faqs.table.question'),
      cell: (faq) => (
        <div className="max-w-[400px] truncate font-medium">{faq.question}</div>
      ),
    },
    {
      key: 'status',
      header: t('helpCenter.faqs.table.status'),
      cell: (faq) => (
        <Badge variant={faq.status === 'published' ? 'default' : 'secondary'}>
          {t(`helpCenter.status.${faq.status}`)}
        </Badge>
      ),
    },
    {
      key: 'scope',
      header: t('helpCenter.faqs.table.scope'),
      cell: (faq) => (
        <Badge variant={faq.is_platform_wide ? 'default' : 'outline'}>
          {faq.is_platform_wide ? t('helpCenter.scope.platform') : t('helpCenter.scope.organization')}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (faq) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(faq)}>
              {t('helpCenter.faqs.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingFaq(faq)}
              className="text-destructive"
            >
              {t('helpCenter.faqs.actions.delete')}
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
        name="question"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.faqs.form.question')}</FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="answer"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.faqs.form.answer')}</FormLabel>
            <FormControl>
              <Textarea {...field} rows={6} />
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
            <FormLabel>{t('helpCenter.faqs.form.category')}</FormLabel>
            <Select onValueChange={field.onChange} value={field.value}>
              <FormControl>
                <SelectTrigger>
                  <SelectValue placeholder={t('helpCenter.faqs.form.categoryPlaceholder')} />
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
      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="status"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('helpCenter.faqs.form.status')}</FormLabel>
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
        <FormField
          control={form.control}
          name="display_order"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('helpCenter.faqs.form.displayOrder')}</FormLabel>
              <FormDescription>{t('helpCenter.faqs.form.displayOrderDescription')}</FormDescription>
              <FormControl>
                <Input
                  type="number"
                  {...field}
                  onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
      {!isEditing && (
        <FormField
          control={form.control}
          name="is_platform_wide"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <FormLabel>{t('helpCenter.faqs.form.platformWide')}</FormLabel>
                <FormDescription>{t('helpCenter.faqs.form.platformWideDescription')}</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
      )}
    </>
  )

  // Get category name helper
  const getCategoryName = (categoryId: string) => {
    return categoriesData?.items?.find((c) => c.id === categoryId)?.name || '-'
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('helpCenter.faqs.pageTitle')}
        description={t('helpCenter.faqs.pageDescription')}
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
              <Button onClick={openCreateDialog}>{t('helpCenter.faqs.createButton')}</Button>
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
            renderItem={(faq) => (
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{faq.question}</div>
                  <div className="text-sm text-muted-foreground truncate">
                    {getCategoryName(faq.category_id)}
                  </div>
                </div>
                <Badge variant={faq.status === 'published' ? 'default' : 'secondary'}>
                  {t(`helpCenter.status.${faq.status}`)}
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
          emptyMessage={t('helpCenter.faqs.emptyMessage')}
          pagination={{
            page,
            pageSize,
            total: data?.total || 0,
            onPageChange: setPage,
          }}
        />
      )}

      {/* Create FAQ Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.faqs.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.faqs.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              {renderFormFields(false)}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('helpCenter.faqs.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating
                    ? t('helpCenter.faqs.createDialog.creating')
                    : t('helpCenter.faqs.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit FAQ Dialog */}
      <Dialog open={!!editingFaq} onOpenChange={() => setEditingFaq(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.faqs.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.faqs.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEdit)} className="space-y-4">
              {renderFormFields(true)}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingFaq(null)}
                >
                  {t('helpCenter.faqs.editDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating
                    ? t('helpCenter.faqs.editDialog.saving')
                    : t('helpCenter.faqs.editDialog.save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingFaq}
        onOpenChange={() => setDeletingFaq(null)}
        title={t('helpCenter.faqs.deleteDialog.title')}
        description={t('helpCenter.faqs.deleteDialog.description', { question: deletingFaq?.question })}
        confirmLabel={t('helpCenter.faqs.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
