import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { MoreHorizontal } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
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
  useGetChangelogsQuery,
  useCreateChangelogMutation,
  useUpdateChangelogMutation,
  useDeleteChangelogMutation,
} from '@/features/changelog/changelogApi'
import type { ChangelogEntry, ChangelogCategory } from '@/types/changelog'

const changelogSchema = z.object({
  version: z.string().min(1).max(50),
  title: z.string().min(1).max(255),
  body: z.string().min(1),
  category: z.enum(['feature', 'improvement', 'bugfix', 'breaking', 'other']),
  release_date: z.string().min(1),
  is_published: z.boolean(),
  is_platform_wide: z.boolean(),
})

type ChangelogFormValues = z.infer<typeof changelogSchema>

const CATEGORY_VARIANTS: Record<ChangelogCategory, string> = {
  feature: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  improvement:
    'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  bugfix: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  breaking:
    'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  other: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
}

export function ChangelogPage() {
  const { t } = useTranslation('admin')
  const [createOpen, setCreateOpen] = useState(false)
  const [editEntry, setEditEntry] = useState<ChangelogEntry | null>(null)
  const [deleteEntry, setDeleteEntry] = useState<ChangelogEntry | null>(null)

  const { data, isLoading } = useGetChangelogsQuery()
  const [createChangelog, { isLoading: isCreating }] =
    useCreateChangelogMutation()
  const [updateChangelog, { isLoading: isUpdating }] =
    useUpdateChangelogMutation()
  const [deleteChangelog] = useDeleteChangelogMutation()

  const form = useForm<ChangelogFormValues>({
    resolver: zodResolver(changelogSchema),
    defaultValues: {
      version: '',
      title: '',
      body: '',
      category: 'other',
      release_date: new Date().toISOString().slice(0, 16),
      is_published: false,
      is_platform_wide: false,
    },
  })

  const openCreate = () => {
    form.reset({
      version: '',
      title: '',
      body: '',
      category: 'other',
      release_date: new Date().toISOString().slice(0, 16),
      is_published: false,
      is_platform_wide: false,
    })
    setCreateOpen(true)
  }

  const openEdit = (entry: ChangelogEntry) => {
    form.reset({
      version: entry.version,
      title: entry.title,
      body: entry.body,
      category: entry.category,
      release_date: entry.release_date.slice(0, 16),
      is_published: entry.is_published,
      is_platform_wide: entry.is_platform_wide,
    })
    setEditEntry(entry)
  }

  const onSubmitCreate = async (values: ChangelogFormValues) => {
    try {
      await createChangelog({
        ...values,
        release_date: new Date(values.release_date).toISOString(),
      }).unwrap()
      toast.success(t('changelog.toast.createSuccess'))
      setCreateOpen(false)
    } catch {
      toast.error(t('changelog.toast.createError'))
    }
  }

  const onSubmitEdit = async (values: ChangelogFormValues) => {
    if (!editEntry) return
    try {
      await updateChangelog({
        id: editEntry.id,
        body: {
          version: values.version,
          title: values.title,
          body: values.body,
          category: values.category,
          release_date: new Date(values.release_date).toISOString(),
          is_published: values.is_published,
        },
      }).unwrap()
      toast.success(t('changelog.toast.updateSuccess'))
      setEditEntry(null)
    } catch {
      toast.error(t('changelog.toast.updateError'))
    }
  }

  const onDelete = async () => {
    if (!deleteEntry) return
    try {
      await deleteChangelog(deleteEntry.id).unwrap()
      toast.success(t('changelog.toast.deleteSuccess'))
      setDeleteEntry(null)
    } catch {
      toast.error(t('changelog.toast.deleteError'))
    }
  }

  const columns: Column<ChangelogEntry>[] = [
    {
      key: 'version',
      header: t('changelog.table.version'),
      cell: (entry) => (
        <span className="font-mono text-sm">{entry.version}</span>
      ),
    },
    {
      key: 'title',
      header: t('changelog.table.title'),
      cell: (entry) => <span className="font-medium">{entry.title}</span>,
    },
    {
      key: 'category',
      header: t('changelog.table.category'),
      cell: (entry) => (
        <Badge variant="outline" className={CATEGORY_VARIANTS[entry.category]}>
          {t(`changelog.categories.${entry.category}`)}
        </Badge>
      ),
    },
    {
      key: 'is_published',
      header: t('changelog.table.status'),
      cell: (entry) => (
        <Badge variant={entry.is_published ? 'default' : 'secondary'}>
          {entry.is_published
            ? t('changelog.status.published')
            : t('changelog.status.draft')}
        </Badge>
      ),
    },
    {
      key: 'organization_id',
      header: t('changelog.table.scope'),
      cell: (entry) => (
        <Badge variant="outline">
          {entry.is_platform_wide
            ? t('changelog.scope.platform')
            : t('changelog.scope.organization')}
        </Badge>
      ),
    },
    {
      key: 'release_date',
      header: t('changelog.table.releaseDate'),
      cell: (entry) => new Date(entry.release_date).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: '',
      cell: (entry) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEdit(entry)}>
              {t('changelog.actions.edit')}
            </DropdownMenuItem>
            <DropdownMenuItem
              className="text-destructive"
              onClick={() => setDeleteEntry(entry)}
            >
              {t('changelog.actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  const formContent = (
    <Form {...form}>
      <form className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="version"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('changelog.form.version')}</FormLabel>
                <FormControl>
                  <Input placeholder="1.0.0" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="category"
            render={({ field }) => (
              <FormItem>
                <FormLabel>{t('changelog.form.category')}</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  defaultValue={field.value}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {(
                      [
                        'feature',
                        'improvement',
                        'bugfix',
                        'breaking',
                        'other',
                      ] as ChangelogCategory[]
                    ).map((cat) => (
                      <SelectItem key={cat} value={cat}>
                        {t(`changelog.categories.${cat}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
        <FormField
          control={form.control}
          name="title"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('changelog.form.title')}</FormLabel>
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
              <FormLabel>{t('changelog.form.body')}</FormLabel>
              <FormControl>
                <Textarea rows={6} {...field} />
              </FormControl>
              <FormDescription>
                {t('changelog.form.bodyDescription')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="release_date"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('changelog.form.releaseDate')}</FormLabel>
              <FormControl>
                <Input type="datetime-local" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <div className="flex gap-6">
          <FormField
            control={form.control}
            name="is_published"
            render={({ field }) => (
              <FormItem className="flex items-center gap-2 space-y-0">
                <FormControl>
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <FormLabel className="!mt-0">
                  {t('changelog.form.published')}
                </FormLabel>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="is_platform_wide"
            render={({ field }) => (
              <FormItem className="flex items-center gap-2 space-y-0">
                <FormControl>
                  <Switch
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </FormControl>
                <FormLabel className="!mt-0">
                  {t('changelog.form.platformWide')}
                </FormLabel>
                <FormDescription>
                  {t('changelog.form.platformWideDescription')}
                </FormDescription>
              </FormItem>
            )}
          />
        </div>
      </form>
    </Form>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('changelog.pageTitle')}
        description={t('changelog.pageDescription')}
      >
        <Button onClick={openCreate}>{t('changelog.createButton')}</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        isLoading={isLoading}
        emptyMessage={t('changelog.emptyMessage')}
      />

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('changelog.createDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('changelog.createDialog.description')}
            </DialogDescription>
          </DialogHeader>
          {formContent}
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={form.handleSubmit(onSubmitCreate)}
              disabled={isCreating}
            >
              {isCreating
                ? t('common.creating')
                : t('changelog.createDialog.create')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Edit Dialog */}
      <Dialog open={!!editEntry} onOpenChange={(o) => !o && setEditEntry(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t('changelog.editDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('changelog.editDialog.description')}
            </DialogDescription>
          </DialogHeader>
          {formContent}
          <div className="flex justify-end gap-2 pt-4">
            <Button variant="outline" onClick={() => setEditEntry(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={form.handleSubmit(onSubmitEdit)}
              disabled={isUpdating}
            >
              {isUpdating ? t('common.saving') : t('common.save')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <ConfirmDialog
        open={!!deleteEntry}
        onOpenChange={(o) => !o && setDeleteEntry(null)}
        title={t('changelog.deleteDialog.title')}
        description={t('changelog.deleteDialog.description', {
          title: deleteEntry?.title,
        })}
        confirmLabel={t('changelog.deleteDialog.delete')}
        variant="destructive"
        onConfirm={onDelete}
      />
    </div>
  )
}
