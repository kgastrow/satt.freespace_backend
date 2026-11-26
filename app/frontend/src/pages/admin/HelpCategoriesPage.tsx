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
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import {
  useGetHelpCategoriesQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useDeleteCategoryMutation,
  useReorderCategoriesMutation,
} from '@/store/api/helpCenterApi'
import type { HelpCategory, ReorderItem } from '@/types/helpCenter'

const categorySchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().max(500).optional().nullable(),
  slug: z.string().min(1, 'Slug is required').max(100).regex(/^[a-z0-9-]+$/, 'Slug must be lowercase letters, numbers, and hyphens only'),
  display_order: z.number().min(0),
})

type CategoryFormData = z.infer<typeof categorySchema>

function extractApiErrorMessage(error: unknown, fallbackMessage: string): string {
  const apiError = error as { data?: { detail?: string | Array<{ msg: string }> } }
  const detail = apiError.data?.detail
  if (Array.isArray(detail)) {
    return detail.map(e => e.msg).join(', ')
  }
  return detail || fallbackMessage
}

export function HelpCategoriesPage() {
  const { t } = useTranslation('admin')
  const [isReorderMode, setIsReorderMode] = useState(false)
  const [pendingReorder, setPendingReorder] = useState<ReorderItem[] | null>(null)

  const { data, isLoading } = useGetHelpCategoriesQuery()
  const [createCategory, { isLoading: isCreating }] = useCreateCategoryMutation()
  const [updateCategory, { isLoading: isUpdating }] = useUpdateCategoryMutation()
  const [deleteCategory, { isLoading: isDeleting }] = useDeleteCategoryMutation()
  const [reorderCategories, { isLoading: isReordering }] = useReorderCategoriesMutation()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingCategory, setEditingCategory] = useState<HelpCategory | null>(null)
  const [deletingCategory, setDeletingCategory] = useState<HelpCategory | null>(null)

  const handleReorder = (reorderedItems: Array<HelpCategory & { display_order: number }>) => {
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
      await reorderCategories({ items: pendingReorder }).unwrap()
      toast.success(t('helpCenter.categories.toast.reorderSuccess'))
      setIsReorderMode(false)
      setPendingReorder(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.categories.toast.reorderError')))
    }
  }

  const handleCancelReorder = () => {
    setIsReorderMode(false)
    setPendingReorder(null)
  }

  const form = useForm<CategoryFormData>({
    resolver: zodResolver(categorySchema),
    defaultValues: {
      name: '',
      description: '',
      slug: '',
      display_order: 0,
    },
  })

  const handleCreate = async (data: CategoryFormData) => {
    try {
      await createCategory({
        name: data.name,
        description: data.description || null,
        slug: data.slug,
        display_order: data.display_order,
      }).unwrap()
      toast.success(t('helpCenter.categories.toast.createSuccess'))
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.categories.toast.createError')))
    }
  }

  const handleEdit = async (data: CategoryFormData) => {
    if (!editingCategory) return
    try {
      await updateCategory({
        id: editingCategory.id,
        body: {
          name: data.name,
          description: data.description || null,
          slug: data.slug,
          display_order: data.display_order,
        },
      }).unwrap()
      toast.success(t('helpCenter.categories.toast.updateSuccess'))
      setEditingCategory(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.categories.toast.updateError')))
    }
  }

  const handleDelete = async () => {
    if (!deletingCategory) return
    try {
      await deleteCategory(deletingCategory.id).unwrap()
      toast.success(t('helpCenter.categories.toast.deleteSuccess'))
      setDeletingCategory(null)
    } catch (error: unknown) {
      toast.error(extractApiErrorMessage(error, t('helpCenter.categories.toast.deleteError')))
    }
  }

  const openEditDialog = (category: HelpCategory) => {
    form.reset({
      name: category.name,
      description: category.description || '',
      slug: category.slug,
      display_order: category.display_order,
    })
    setEditingCategory(category)
  }

  const openCreateDialog = () => {
    form.reset({
      name: '',
      description: '',
      slug: '',
      display_order: 0,
    })
    setIsCreateOpen(true)
  }

  const columns: Column<HelpCategory>[] = [
    {
      key: 'order',
      header: t('helpCenter.categories.table.order'),
      className: 'w-[80px]',
      cell: (category) => (
        <span className="text-muted-foreground">{category.display_order}</span>
      ),
    },
    {
      key: 'name',
      header: t('helpCenter.categories.table.name'),
      cell: (category) => (
        <div className="font-medium">{category.name}</div>
      ),
    },
    {
      key: 'slug',
      header: t('helpCenter.categories.table.slug'),
      cell: (category) => (
        <div className="text-muted-foreground text-sm">{category.slug}</div>
      ),
    },
    {
      key: 'description',
      header: t('helpCenter.categories.table.description'),
      cell: (category) => (
        <div className="max-w-[400px] truncate text-sm">{category.description || '-'}</div>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (category) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(category)}>
              {t('helpCenter.categories.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => setDeletingCategory(category)}
              className="text-destructive"
            >
              {t('helpCenter.categories.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  const renderFormFields = () => (
    <>
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.categories.form.name')}</FormLabel>
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
            <FormLabel>{t('helpCenter.categories.form.slug')}</FormLabel>
            <FormDescription>{t('helpCenter.categories.form.slugDescription')}</FormDescription>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.categories.form.description')} <span className="text-muted-foreground font-normal">({t('helpCenter.form.optional')})</span></FormLabel>
            <FormControl>
              <Textarea {...field} value={field.value || ''} rows={3} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <FormField
        control={form.control}
        name="display_order"
        render={({ field }) => (
          <FormItem>
            <FormLabel>{t('helpCenter.categories.form.displayOrder')}</FormLabel>
            <FormDescription>{t('helpCenter.categories.form.displayOrderDescription')}</FormDescription>
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
    </>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('helpCenter.categories.pageTitle')}
        description={t('helpCenter.categories.pageDescription')}
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
              <Button onClick={openCreateDialog}>{t('helpCenter.categories.createButton')}</Button>
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
            renderItem={(category) => (
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{category.name}</div>
                  <div className="text-sm text-muted-foreground truncate">
                    {category.slug}
                  </div>
                </div>
              </div>
            )}
          />
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={data?.items || []}
          isLoading={isLoading}
          emptyMessage={t('helpCenter.categories.emptyMessage')}
        />
      )}

      {/* Create Category Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.categories.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.categories.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              {renderFormFields()}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('helpCenter.categories.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating
                    ? t('helpCenter.categories.createDialog.creating')
                    : t('helpCenter.categories.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Category Dialog */}
      <Dialog open={!!editingCategory} onOpenChange={() => setEditingCategory(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('helpCenter.categories.editDialog.title')}</DialogTitle>
            <DialogDescription>{t('helpCenter.categories.editDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEdit)} className="space-y-4">
              {renderFormFields()}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingCategory(null)}
                >
                  {t('helpCenter.categories.editDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating
                    ? t('helpCenter.categories.editDialog.saving')
                    : t('helpCenter.categories.editDialog.save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingCategory}
        onOpenChange={() => setDeletingCategory(null)}
        title={t('helpCenter.categories.deleteDialog.title')}
        description={t('helpCenter.categories.deleteDialog.description', { name: deletingCategory?.name })}
        confirmLabel={t('helpCenter.categories.deleteDialog.delete')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
