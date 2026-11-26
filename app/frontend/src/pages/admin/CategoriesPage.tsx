import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Plus, Pencil, Trash2, Lock, GripVertical } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
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
  useGetNotificationCategoriesQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useDeleteCategoryMutation,
  type NotificationCategory,
} from '@/features/notifications/notificationsApi'

const categorySchema = z.object({
  code: z.string().min(1, 'Code is required').max(50),
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().optional(),
  default_enabled: z.boolean(),
  user_configurable: z.boolean(),
  display_order: z.number().int().min(0),
})

const editCategorySchema = categorySchema.omit({ code: true })

type CategoryFormData = z.infer<typeof categorySchema>
type EditCategoryFormData = z.infer<typeof editCategorySchema>

export function CategoriesPage() {
  const [page, setPage] = useState(1)
  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingCategory, setEditingCategory] = useState<NotificationCategory | null>(null)
  const [deletingCategory, setDeletingCategory] = useState<NotificationCategory | null>(null)
  const pageSize = 10

  const { data, isLoading } = useGetNotificationCategoriesQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createCategory, { isLoading: isCreating }] = useCreateCategoryMutation()
  const [updateCategory, { isLoading: isUpdating }] = useUpdateCategoryMutation()
  const [deleteCategory, { isLoading: isDeleting }] = useDeleteCategoryMutation()

  const createForm = useForm<CategoryFormData>({
    resolver: zodResolver(categorySchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
      default_enabled: true,
      user_configurable: true,
      display_order: 0,
    },
  })

  const editForm = useForm<EditCategoryFormData>({
    resolver: zodResolver(editCategorySchema),
    defaultValues: {
      name: '',
      description: '',
      default_enabled: true,
      user_configurable: true,
      display_order: 0,
    },
  })

  const handleCreate = async (formData: CategoryFormData) => {
    try {
      await createCategory({
        ...formData,
        description: formData.description || undefined,
      }).unwrap()
      toast.success('Category created successfully')
      setIsCreateOpen(false)
      createForm.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to create category')
    }
  }

  const handleEdit = async (formData: EditCategoryFormData) => {
    if (!editingCategory) return
    try {
      await updateCategory({
        id: editingCategory.id,
        data: {
          name: formData.name,
          description: formData.description || undefined,
          default_enabled: formData.default_enabled,
          user_configurable: formData.user_configurable,
          display_order: formData.display_order,
        },
      }).unwrap()
      toast.success('Category updated successfully')
      setEditingCategory(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update category')
    }
  }

  const handleDelete = async () => {
    if (!deletingCategory) return
    try {
      await deleteCategory(deletingCategory.id).unwrap()
      toast.success('Category deleted successfully')
      setDeletingCategory(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to delete category')
    }
  }

  const openEditDialog = (category: NotificationCategory) => {
    editForm.reset({
      name: category.name,
      description: category.description || '',
      default_enabled: category.default_enabled,
      user_configurable: category.user_configurable,
      display_order: category.display_order,
    })
    setEditingCategory(category)
  }

  const columns: Column<NotificationCategory>[] = [
    {
      key: 'order',
      header: '',
      className: 'w-[40px]',
      cell: () => (
        <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab" />
      ),
    },
    {
      key: 'name',
      header: 'Category',
      cell: (category) => (
        <div className="flex items-center gap-2">
          {category.organization_id === null && (
            <Lock className="h-4 w-4 text-muted-foreground" aria-label="System category" />
          )}
          <div>
            <p className="font-medium">{category.name}</p>
            <p className="text-sm text-muted-foreground">{category.code}</p>
          </div>
        </div>
      ),
    },
    {
      key: 'description',
      header: 'Description',
      cell: (category) => (
        <span className="text-muted-foreground truncate max-w-[200px] block">
          {category.description || '-'}
        </span>
      ),
    },
    {
      key: 'default_enabled',
      header: 'Default',
      cell: (category) => (
        <Badge variant={category.default_enabled ? 'default' : 'secondary'}>
          {category.default_enabled ? 'Enabled' : 'Disabled'}
        </Badge>
      ),
    },
    {
      key: 'user_configurable',
      header: 'User Config',
      cell: (category) => (
        <Badge variant={category.user_configurable ? 'outline' : 'secondary'}>
          {category.user_configurable ? 'Yes' : 'No'}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (category) =>
        category.organization_id !== null && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                ...
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => openEditDialog(category)}>
                <Pencil className="h-4 w-4 mr-2" />
                Edit
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => setDeletingCategory(category)}
                className="text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notification Categories"
        description="Organize notifications into categories that users can subscribe/unsubscribe from"
      >
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Create Category
        </Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage="No categories found"
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Create Category</DialogTitle>
            <DialogDescription>Create a new notification category</DialogDescription>
          </DialogHeader>
          <Form {...createForm}>
            <form onSubmit={createForm.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={createForm.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code</FormLabel>
                    <FormControl>
                      <Input placeholder="marketing_updates" {...field} />
                    </FormControl>
                    <FormDescription>Unique identifier (lowercase, underscores)</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Marketing Updates" {...field} />
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
                      <Input placeholder="News about products and features" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="display_order"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display Order</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                      />
                    </FormControl>
                    <FormDescription>Lower numbers appear first</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="default_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Enabled by Default</FormLabel>
                      <FormDescription>
                        New users will have this category enabled
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={createForm.control}
                name="user_configurable"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">User Configurable</FormLabel>
                      <FormDescription>
                        Users can enable/disable this category
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
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
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editingCategory} onOpenChange={() => setEditingCategory(null)}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Edit Category</DialogTitle>
            <DialogDescription>Update category: {editingCategory?.code}</DialogDescription>
          </DialogHeader>
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

              <FormField
                control={editForm.control}
                name="display_order"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Display Order</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="default_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Enabled by Default</FormLabel>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <FormField
                control={editForm.control}
                name="user_configurable"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">User Configurable</FormLabel>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              <div className="flex justify-end gap-2 pt-4">
                <Button type="button" variant="outline" onClick={() => setEditingCategory(null)}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? 'Saving...' : 'Save'}
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
        title="Delete Category"
        description={`Are you sure you want to delete "${deletingCategory?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
