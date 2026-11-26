import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from '@/lib/toast'
import { Download, Trash2, Settings, Search, Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FileIcon } from '@/components/FileIcon'
import { FileImageWithPreview } from '@/components/FileImageWithPreview'
import { StorageUsageBar } from '@/components/StorageUsageBar'
import { formatBytes } from '@/lib/utils'
import { safeOpenDownloadUrl } from '@/lib/url-validation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  useGetOrgFilesQuery,
  useLazyGetDownloadUrlQuery,
  useDeleteFileMutation,
  useGetOrgUsageQuery,
  type FileRecord,
} from '@/features/files/filesApi'
import { usePermission } from '@/hooks/usePermission'

type CategoryFilter = 'all' | 'image' | 'video' | 'document' | 'other'

export function AdminFilesPage() {
  const { t } = useTranslation('files')
  const { canWrite, canDelete } = usePermission('files')
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState<CategoryFilter>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [deletingFile, setDeletingFile] = useState<FileRecord | null>(null)
  const pageSize = 20

  const { data: filesData, isLoading } = useGetOrgFilesQuery({
    category: category === 'all' ? undefined : category,
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const { data: usageData } = useGetOrgUsageQuery()
  const [triggerDownload] = useLazyGetDownloadUrlQuery()
  const [deleteFile, { isLoading: isDeleting }] = useDeleteFileMutation()

  const handleDownload = async (file: FileRecord) => {
    try {
      const result = await triggerDownload(file.id).unwrap()
      // SEC-F-011: Validate URL before opening
      if (!safeOpenDownloadUrl(result.download_url)) {
        toast.error('Invalid download URL', { category: 'file' })
      }
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to get download URL', { category: 'file' })
    }
  }

  const handleDelete = async () => {
    if (!deletingFile) return
    try {
      await deleteFile(deletingFile.id).unwrap()
      toast.success('File deleted successfully', { category: 'file' })
      setDeletingFile(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to delete file', { category: 'file' })
    }
  }

  const filteredFiles =
    filesData?.items.filter((file) =>
      file.original_filename.toLowerCase().includes(searchQuery.toLowerCase())
    ) || []

  const columns: Column<FileRecord>[] = [
    {
      key: 'file',
      header: 'File',
      cell: (file) => {
        const isImage = file.category === 'image'
        return (
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
                  enablePreview={true}
                />
              </div>
            ) : (
              <FileIcon
                contentType={file.content_type}
                extension={file.file_extension}
                size="md"
              />
            )}
            <div className="min-w-0">
              <p className="font-medium truncate max-w-[200px]" title={file.original_filename}>
                {file.original_filename}
              </p>
              <p className="text-xs text-muted-foreground">
                {formatBytes(file.size_bytes)}
              </p>
            </div>
          </div>
        )
      },
    },
    {
      key: 'category',
      header: 'Type',
      cell: (file) => (
        <Badge variant="secondary" className="capitalize">
          {file.category || 'other'}
        </Badge>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cell: (file) => {
        const statusColors: Record<string, string> = {
          uploaded: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
          pending: 'bg-yellow-500/10 text-yellow-600 dark:bg-yellow-500/20 dark:text-yellow-400',
          processing: 'bg-blue-500/10 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400',
          ready: 'bg-green-500/10 text-green-600 dark:bg-green-500/20 dark:text-green-400',
          failed: 'bg-red-500/10 text-red-600 dark:bg-red-500/20 dark:text-red-400',
        }
        return <Badge className={statusColors[file.status]}>{file.status}</Badge>
      },
    },
    {
      key: 'is_public',
      header: t('badges.public'),
      cell: (file) => {
        const isPublic = (file as FileRecord & { is_public?: boolean }).is_public
        return isPublic ? (
          <Badge variant="outline" className="gap-0.5">
            <Globe className="h-3 w-3" />
            {t('badges.public')}
          </Badge>
        ) : null
      },
    },
    {
      key: 'downloads',
      header: 'Downloads',
      cell: (file) => file.download_count.toLocaleString(),
    },
    {
      key: 'created_time',
      header: 'Uploaded',
      cell: (file) => new Date(file.created_time).toLocaleDateString(),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (file) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => handleDownload(file)}>
              <Download className="h-4 w-4 mr-2" />
              Download
            </DropdownMenuItem>
            {canDelete && (
              <DropdownMenuItem
                onClick={() => setDeletingFile(file)}
                className="text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader title="File Management" description="Manage organization files">
        {canWrite && (
          <Button asChild variant="outline">
            <Link to="/admin/files/settings">
              <Settings className="h-4 w-4 mr-2" />
              Settings
            </Link>
          </Button>
        )}
      </PageHeader>

      {/* Usage Stats */}
      {usageData && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Total Files</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{usageData.total_files.toLocaleString()}</div>
              <p className="text-xs text-muted-foreground">
                {usageData.user_count} users with files
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Storage Used</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatBytes(usageData.total_size_bytes)}</div>
              {usageData.org_quota_bytes && (
                <p className="text-xs text-muted-foreground">
                  of {formatBytes(usageData.org_quota_bytes)} quota
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Quota Usage</CardTitle>
            </CardHeader>
            <CardContent>
              <StorageUsageBar
                usedBytes={usageData.total_size_bytes}
                quotaBytes={usageData.org_quota_bytes ?? null}
                showLabel={false}
              />
              {usageData.org_quota_used_percent !== null && (
                <p className="text-xs text-muted-foreground mt-2">
                  {usageData.org_quota_used_percent}% used
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
        <Tabs value={category} onValueChange={(v) => setCategory(v as CategoryFilter)}>
          <TabsList>
            <TabsTrigger value="all">All</TabsTrigger>
            <TabsTrigger value="image">Images</TabsTrigger>
            <TabsTrigger value="video">Videos</TabsTrigger>
            <TabsTrigger value="document">Documents</TabsTrigger>
            <TabsTrigger value="other">Other</TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search files..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 w-[250px]"
          />
        </div>
      </div>

      {/* Files Table */}
      <DataTable
        columns={columns}
        data={filteredFiles}
        isLoading={isLoading}
        emptyMessage="No files found"
        pagination={{
          page,
          pageSize,
          total: filesData?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingFile}
        onOpenChange={() => setDeletingFile(null)}
        title="Delete File"
        description={`Are you sure you want to delete "${deletingFile?.original_filename}"? This action cannot be undone.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />
    </div>
  )
}
