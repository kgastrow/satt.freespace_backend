import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, X, CheckCircle, Loader2 } from 'lucide-react'
import { cn, formatBytes } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { FileIcon } from '@/components/FileIcon'
import { useTranslation } from 'react-i18next'

interface UploadingFile {
  file: File
  progress: number
  status: 'uploading' | 'success' | 'error'
  error?: string
}

interface FileUploaderProps {
  onUpload: (file: File) => Promise<void>
  accept?: Record<string, string[]>
  maxSize?: number
  maxFiles?: number
  disabled?: boolean
  className?: string
}

export function FileUploader({
  onUpload,
  accept,
  maxSize = 100 * 1024 * 1024, // 100MB default
  maxFiles = 10,
  disabled = false,
  className,
}: FileUploaderProps) {
  const { t } = useTranslation()
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([])

  const handleUpload = useCallback(
    async (file: File) => {
      const uploadFile: UploadingFile = {
        file,
        progress: 0,
        status: 'uploading',
      }

      setUploadingFiles((prev) => [...prev, uploadFile])

      try {
        // Simulate progress (actual progress would come from XMLHttpRequest)
        const progressInterval = setInterval(() => {
          setUploadingFiles((prev) =>
            prev.map((f) =>
              f.file === file && f.status === 'uploading'
                ? { ...f, progress: Math.min(f.progress + 10, 90) }
                : f
            )
          )
        }, 200)

        await onUpload(file)

        clearInterval(progressInterval)
        setUploadingFiles((prev) =>
          prev.map((f) => (f.file === file ? { ...f, progress: 100, status: 'success' } : f))
        )

        // Remove successful uploads after a delay
        setTimeout(() => {
          setUploadingFiles((prev) => prev.filter((f) => f.file !== file))
        }, 2000)
      } catch (error) {
        setUploadingFiles((prev) =>
          prev.map((f) =>
            f.file === file
              ? { ...f, status: 'error', error: error instanceof Error ? error.message : 'Upload failed' }
              : f
          )
        )
      }
    },
    [onUpload]
  )

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      acceptedFiles.forEach((file) => {
        handleUpload(file)
      })
    },
    [handleUpload]
  )

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    onDrop,
    accept,
    maxSize,
    maxFiles,
    disabled,
    multiple: maxFiles > 1,
  })

  const removeFile = (file: File) => {
    setUploadingFiles((prev) => prev.filter((f) => f.file !== file))
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
            <p className="text-destructive">{t('fileUploader.dragReject')}</p>
          ) : (
            <p className="text-primary">{t('fileUploader.dragActive')}</p>
          )
        ) : (
          <>
            <p className="text-muted-foreground mb-1">
              {t('fileUploader.placeholder')}
            </p>
            <p className="text-xs text-muted-foreground">
              {t('fileUploader.maxSize', { size: formatBytes(maxSize) })}
            </p>
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
              <FileIcon
                contentType={uploadFile.file.type}
                extension={uploadFile.file.name.split('.').pop()}
                size="md"
              />
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
