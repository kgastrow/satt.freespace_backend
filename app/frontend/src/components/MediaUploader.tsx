import { useCallback, useState } from 'react'
import { useDropzone, type Accept } from 'react-dropzone'
import { Upload, X, CheckCircle, Loader2, Image as ImageIcon, Video } from 'lucide-react'
import { cn, formatBytes } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useTranslation } from 'react-i18next'
import { useUploadFileMutation, useLazyGetDownloadUrlQuery } from '@/features/files/filesApi'
import { MediaUse } from '@/types/generated'
import { toast } from 'sonner'
import { getErrorMessage } from '@/types/api'

interface UploadingMedia {
  file: File
  progress: number
  status: 'uploading' | 'success' | 'error'
  error?: string
  mediaId?: string
  thumbnailUrl?: string | null
}

interface MediaUploaderProps {
  media_use: MediaUse
  onUploadSuccess?: (mediaId: string, mediaUrl: string | null, file: File) => void
  accept?: 'image' | 'video' | 'both'
  maxSize?: number
  maxFiles?: number
  disabled?: boolean
  className?: string
  /** Whether uploaded files should be publicly accessible without authentication */
  isPublic?: boolean
}

export function MediaUploader({
  media_use,
  onUploadSuccess,
  accept = 'image',
  maxSize = 5 * 1024 * 1024, // 5MB default for images
  maxFiles = 1,
  disabled = false,
  className,
  isPublic = false,
}: MediaUploaderProps) {
  const { t } = useTranslation(['media', 'backend'])
  const [uploadingFiles, setUploadingFiles] = useState<UploadingMedia[]>([])
  const [uploadFile] = useUploadFileMutation()
  const [getDownloadUrl] = useLazyGetDownloadUrlQuery()

  const handleUpload = useCallback(
    async (file: File) => {
      const uploadingFile: UploadingMedia = {
        file,
        progress: 0,
        status: 'uploading',
      }

      setUploadingFiles((prev) => [...prev, uploadingFile])

      try {
        const progressInterval = setInterval(() => {
          setUploadingFiles((prev) =>
            prev.map((f) =>
              f.file === file && f.status === 'uploading'
                ? { ...f, progress: Math.min(f.progress + 10, 90) }
                : f
            )
          )
        }, 200)

        // Build FormData for the upload
        const formData = new FormData()
        formData.append('file', file)
        formData.append('media_use', media_use)
        formData.append('is_public', String(isPublic))

        const result = await uploadFile(formData).unwrap()

        clearInterval(progressInterval)

        // Fetch the actual download URL (presigned S3 URL or data URL)
        let downloadUrl: string | null = null
        try {
          const downloadResult = await getDownloadUrl(result.id).unwrap()
          downloadUrl = downloadResult.download_url
        } catch {
          // If we can't get download URL, proceed without it
        }

        const thumbnailUrl = result.thumbnail_url ?? null

        setUploadingFiles((prev) =>
          prev.map((f) =>
            f.file === file
              ? { ...f, progress: 100, status: 'success', mediaId: result.id, thumbnailUrl }
              : f
          )
        )

        if (onUploadSuccess) {
          onUploadSuccess(result.id, downloadUrl, file)
        }

        toast.success(t('media:upload.success'))

        setTimeout(() => {
          setUploadingFiles((prev) => prev.filter((f) => f.file !== file))
        }, 2000)
      } catch (error) {
        const errorMessage = getErrorMessage(error, t)
        setUploadingFiles((prev) =>
          prev.map((f) =>
            f.file === file ? { ...f, status: 'error', error: errorMessage } : f
          )
        )
        toast.error(errorMessage)
      }
    },
    [uploadFile, getDownloadUrl, media_use, onUploadSuccess, t, isPublic]
  )

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      acceptedFiles.forEach((file) => {
        // Block SVG files due to security concerns (XSS risk)
        if (file.type === 'image/svg+xml' || file.name.toLowerCase().endsWith('.svg')) {
          toast.error(t('media:upload.svgNotAllowed'))
          return
        }
        handleUpload(file)
      })
    },
    [handleUpload, t]
  )

  let acceptMime: Accept
  if (accept === 'image') {
    acceptMime = {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'],
    }
  } else if (accept === 'video') {
    acceptMime = {
      'video/*': ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv'],
    }
  } else {
    acceptMime = {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'],
      'video/*': ['.mp4', '.mov', '.avi', '.webm', '.mkv', '.flv'],
    }
  }

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept: acceptMime,
    maxSize,
    maxFiles,
    disabled,
    multiple: maxFiles > 1,
  })

  const removeFile = (file: File) => {
    setUploadingFiles((prev) => prev.filter((f) => f.file !== file))
  }

  const getMediaIcon = (file: File) => {
    if (file.type.startsWith('image/')) {
      return <ImageIcon className="h-8 w-8" />
    } else if (file.type.startsWith('video/')) {
      return <Video className="h-8 w-8" />
    }
    return <ImageIcon className="h-8 w-8" />
  }

  return (
    <div className={cn('space-y-4', className)}>
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors',
          isDragActive && !isDragReject && 'border-primary bg-primary/5',
          isDragReject && 'border-destructive bg-destructive/5',
          disabled && 'opacity-50 cursor-not-allowed',
          !isDragActive && !disabled && 'hover:border-primary/50 hover:bg-muted/50'
        )}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
        {isDragActive ? (
          isDragReject ? (
            <p className="text-destructive">{t('media:upload.dragReject')}</p>
          ) : (
            <p className="text-primary">{t('media:upload.dragActive')}</p>
          )
        ) : (
          <>
            <p className="text-muted-foreground mb-1">{t('media:upload.placeholder')}</p>
            <p className="text-xs text-muted-foreground">
              {t('media:upload.maxSize', { size: formatBytes(maxSize) })}
            </p>
            {accept === 'both' && (
              <p className="text-xs text-muted-foreground mt-1">
                {t('media:upload.acceptBoth')}
              </p>
            )}
            {accept === 'image' && (
              <p className="text-xs text-muted-foreground mt-1">
                {t('media:upload.acceptImage')}
              </p>
            )}
            {accept === 'video' && (
              <p className="text-xs text-muted-foreground mt-1">
                {t('media:upload.acceptVideo')}
              </p>
            )}
          </>
        )}
      </div>

      {uploadingFiles.length > 0 && (
        <div className="space-y-2">
          {uploadingFiles.map((uploadFile, index) => (
            <div
              key={`${uploadFile.file.name}-${index}`}
              className="flex items-center gap-3 p-3 border rounded-lg"
            >
              <div className="flex-shrink-0 text-muted-foreground">
                {uploadFile.status === 'success' && uploadFile.thumbnailUrl ? (
                  <img
                    src={uploadFile.thumbnailUrl}
                    alt={uploadFile.file.name}
                    className="h-12 w-12 object-cover rounded"
                  />
                ) : (
                  getMediaIcon(uploadFile.file)
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium truncate">
                    {uploadFile.file.name}
                  </span>
                  <span className="text-xs text-muted-foreground ml-2">
                    {formatBytes(uploadFile.file.size)}
                  </span>
                </div>
                {uploadFile.status === 'uploading' && (
                  <Progress value={uploadFile.progress} className="h-1" />
                )}
                {uploadFile.status === 'error' && (
                  <p className="text-xs text-destructive">{uploadFile.error}</p>
                )}
              </div>
              <div className="flex-shrink-0">
                {uploadFile.status === 'uploading' && (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                )}
                {uploadFile.status === 'success' && (
                  <CheckCircle className="h-5 w-5 text-green-500/90 dark:text-green-400/90" />
                )}
                {uploadFile.status === 'error' && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => removeFile(uploadFile.file)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
