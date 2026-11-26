import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { Download, Trash2, Grid, List, Search, Upload, Globe } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FileUploader } from '@/components/FileUploader'
import { FileIcon } from '@/components/FileIcon'
import { FileImageWithPreview } from '@/components/FileImageWithPreview'
import { StorageUsageBar } from '@/components/StorageUsageBar'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { formatBytes } from '@/lib/utils'
import { safeOpenDownloadUrl } from '@/lib/url-validation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { CardSkeleton } from '@/components/skeletons'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Pagination, PaginationContent, PaginationItem, PaginationLink, PaginationNext, PaginationPrevious } from '@/components/ui/pagination'
import {
  useGetFilesQuery,
  useUploadFileMutation,
  useLazyGetDownloadUrlQuery,
  useDeleteFileMutation,
  useGetUserUsageQuery,
  type FileRecord,
} from '@/features/files/filesApi'

type ViewMode = 'grid' | 'list'
type CategoryFilter = 'all' | 'image' | 'video' | 'document' | 'other'

export function FilesPage() {
  const { t } = useTranslation('files')
  const [page, setPage] = useState(1)
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [deletingFile, setDeletingFile] = useState<FileRecord | null>(null)

  const pageSize = 20

  const { data: filesData, isLoading: isLoadingFiles } = useGetFilesQuery({
    category: category === 'all' ? undefined : category,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const { data: usageData } = useGetUserUsageQuery()
  const [uploadFile] = useUploadFileMutation()
  const [triggerDownload] = useLazyGetDownloadUrlQuery()
  const [deleteFile, { isLoading: isDeleting }] = useDeleteFileMutation()

  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)

    try {
      await uploadFile(formData).unwrap()
      toast.success(t('messages.uploadSuccess'), { category: 'file' })
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      throw new Error(apiError.data?.detail || t('messages.uploadError'))
    }
  }

  const handleDownload = async (file: FileRecord) => {
    try {
      const result = await triggerDownload(file.id).unwrap()
      // SEC-F-011: Validate URL before opening
      if (!safeOpenDownloadUrl(result.download_url)) {
        toast.error(t('messages.downloadError'), { category: 'file' })
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('messages.downloadError'), { category: 'file' })
    }
  }

  const handleDelete = async () => {
    if (!deletingFile) return
    try {
      await deleteFile(deletingFile.id).unwrap()
      toast.success(t('messages.deleteSuccess'), { category: 'file' })
      setDeletingFile(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('messages.deleteError'), { category: 'file' })
    }
  }

  const filteredFiles =
    filesData?.items.filter((file) =>
      file.original_filename.toLowerCase().includes(searchQuery.toLowerCase())
    ) || []

  const totalPages = Math.ceil((filesData?.total || 0) / pageSize)

  return (
    <div className="space-y-6">
      <PageHeader title={t('title')} description={t('description')} />

      {/* Storage Usage Card */}
      {usageData && (
        <Card className="px-4 py-3">
          <div className="flex flex-col gap-3 text-sm sm:flex-row sm:items-center sm:justify-between sm:gap-6">
            <div className="flex items-center gap-4 sm:gap-6">
              <div>
                <span className="text-muted-foreground">{t('storage.title')}: </span>
                <span className="font-medium">{formatBytes(usageData.total_size_bytes)}</span>
                {usageData.user_quota_bytes && (
                  <span className="text-muted-foreground"> / {formatBytes(usageData.user_quota_bytes)}</span>
                )}
              </div>
              {usageData.user_quota_bytes && (
                <div className="w-32">
                  <StorageUsageBar
                    usedBytes={usageData.total_size_bytes}
                    quotaBytes={usageData.user_quota_bytes}
                    showLabel={false}
                  />
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-1 text-xs">
              <span className="px-2 py-1 rounded-md bg-muted">{usageData.image_count} {t('storage.categories.images')}</span>
              <span className="px-2 py-1 rounded-md bg-muted">{usageData.video_count} {t('storage.categories.videos')}</span>
              <span className="px-2 py-1 rounded-md bg-muted">{usageData.document_count} {t('storage.categories.documents')}</span>
              <span className="px-2 py-1 rounded-md bg-muted">{usageData.other_count} {t('storage.categories.other')}</span>
            </div>
          </div>
        </Card>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <Tabs value={category} onValueChange={(v) => setCategory(v as CategoryFilter)}>
          <TabsList>
            <TabsTrigger value="all">{t('filters.all')}</TabsTrigger>
            <TabsTrigger value="image">{t('filters.image')}</TabsTrigger>
            <TabsTrigger value="video">{t('filters.video')}</TabsTrigger>
            <TabsTrigger value="document">{t('filters.document')}</TabsTrigger>
            <TabsTrigger value="other">{t('filters.other')}</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex gap-2 items-center">
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={t('filters.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-8 w-[200px]"
            />
          </div>
          <div className="flex border rounded-md">
            <Button
              variant={viewMode === 'grid' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setViewMode('grid')}
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === 'list' ? 'secondary' : 'ghost'}
              size="icon"
              onClick={() => setViewMode('list')}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
          <Button onClick={() => setIsUploadOpen(true)}>
            <Upload className="h-4 w-4 mr-2" />
            {t('uploadButton')}
          </Button>
        </div>
      </div>

      {/* File List */}
      {isLoadingFiles ? (
        <div className={viewMode === 'grid' ? 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-3' : 'space-y-2'}>
          {Array.from({ length: pageSize }).map((_, i) => (
            <CardSkeleton key={i} variant={viewMode === 'grid' ? 'grid-item' : 'default'} />
          ))}
        </div>
      ) : filteredFiles.length === 0 ? (
        <Card className="p-12 text-center">
          <p className="text-muted-foreground">{t('emptyState.title')}</p>
        </Card>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 lg:grid-cols-8 xl:grid-cols-10 gap-3">
          {filteredFiles.map((file) => (
            <FileGridItem
              key={file.id}
              file={file}
              onDownload={() => handleDownload(file)}
              onDelete={() => setDeletingFile(file)}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {filteredFiles.map((file) => (
            <FileListItem
              key={file.id}
              file={file}
              onDownload={() => handleDownload(file)}
              onDelete={() => setDeletingFile(file)}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className={page === 1 ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
              />
            </PaginationItem>
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const pageNum = i + 1
              return (
                <PaginationItem key={pageNum}>
                  <PaginationLink
                    isActive={page === pageNum}
                    onClick={() => setPage(pageNum)}
                    className="cursor-pointer"
                  >
                    {pageNum}
                  </PaginationLink>
                </PaginationItem>
              )
            })}
            <PaginationItem>
              <PaginationNext
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className={page === totalPages ? 'pointer-events-none opacity-50' : 'cursor-pointer'}
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}

      {/* Upload Dialog */}
      <Dialog open={isUploadOpen} onOpenChange={setIsUploadOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>{t('dialogs.upload.title')}</DialogTitle>
          </DialogHeader>
          <FileUploader onUpload={handleUpload} />
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingFile}
        onOpenChange={() => setDeletingFile(null)}
        title={t('dialogs.delete.title')}
        description={t('dialogs.delete.description', { filename: deletingFile?.original_filename })}
        confirmLabel={t('dialogs.delete.confirmLabel')}
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />

    </div>
  )
}

function FileGridItem({
  file,
  onDownload,
  onDelete,
}: {
  file: FileRecord
  onDownload: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation('files')
  const isImage = file.category === 'image'
  const isPublic = (file as FileRecord & { is_public?: boolean }).is_public

  return (
    <Card className="group relative overflow-hidden hover:shadow-md transition-shadow">
      <div className="aspect-square flex items-center justify-center bg-muted overflow-hidden">
        {isImage ? (
          <FileImageWithPreview
            fileId={file.id}
            hasThumbnail={!!file.thumbnail_storage_key}
            alt={file.original_filename}
            className="h-full w-full"
            imageClassName="object-cover"
            mode="thumbnail"
            enablePreview={true}
          />
        ) : (
          <FileIcon
            contentType={file.content_type}
            extension={file.file_extension}
            size="md"
          />
        )}
      </div>
      <CardContent className="p-2">
        <p className="text-xs font-medium truncate" title={file.original_filename}>
          {file.original_filename}
        </p>
        {isPublic && (
          <Badge variant="outline" className="mt-1 text-[10px] px-1 py-0 h-4 gap-0.5">
            <Globe className="h-2.5 w-2.5" />
            {t('badges.public')}
          </Badge>
        )}
      </CardContent>
      <div className="absolute top-1 right-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="secondary" size="icon" className="h-8 w-8 sm:h-6 sm:w-6">
              <span className="text-xs">...</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onDownload}>
              <Download className="h-4 w-4 mr-2" />
              {t('actions.download')}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={onDelete} className="text-destructive">
              <Trash2 className="h-4 w-4 mr-2" />
              {t('actions.delete')}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </Card>
  )
}

function FileListItem({
  file,
  onDownload,
  onDelete,
}: {
  file: FileRecord
  onDownload: () => void
  onDelete: () => void
}) {
  const { t } = useTranslation('files')
  const isImage = file.category === 'image'
  const isPublic = (file as FileRecord & { is_public?: boolean }).is_public

  return (
    <Card className="p-3">
      <div className="flex items-center gap-3">
        {isImage ? (
          <div className="h-10 w-10 rounded overflow-hidden flex-shrink-0 bg-muted">
            <FileImageWithPreview
              fileId={file.id}
              hasThumbnail={!!file.thumbnail_storage_key}
              alt={file.original_filename}
              className="h-full w-full"
              imageClassName="object-cover"
              mode="thumbnail"
              enablePreview={false}
            />
          </div>
        ) : (
          <FileIcon
            contentType={file.content_type}
            extension={file.file_extension}
            size="md"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-medium truncate">{file.original_filename}</p>
            {isPublic && (
              <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 gap-0.5 shrink-0">
                <Globe className="h-2.5 w-2.5" />
                {t('badges.public')}
              </Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {formatBytes(file.size_bytes)} • {new Date(file.created_time).toLocaleDateString()}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="icon" onClick={onDownload}>
            <Download className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" onClick={onDelete} className="text-destructive">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </Card>
  )
}
