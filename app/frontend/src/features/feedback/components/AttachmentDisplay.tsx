import { FileImage as FileImageIcon, FileText, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { FileImageWithPreview } from '@/components/FileImageWithPreview'
import { useLazyGetDownloadUrlQuery } from '@/features/files/filesApi'
import { isValidDownloadUrl } from '@/lib/url-validation'
import type { FeedbackAttachment } from '../types'

interface AttachmentDisplayProps {
  attachment: FeedbackAttachment
}

export function AttachmentDisplay({ attachment }: AttachmentDisplayProps) {
  const [getDownloadUrl] = useLazyGetDownloadUrlQuery()

  const isImage = attachment.file_type.startsWith('image/')
  // file_path now contains the file ID
  const fileId = attachment.file_path

  // Check if file_path looks like a UUID (file ID) vs a filename
  const isFileId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(fileId)

  const handleDownload = async () => {
    if (!isFileId) return

    try {
      const result = await getDownloadUrl(fileId).unwrap()
      // SEC-F-011: Validate URL before using
      if (result.download_url && isValidDownloadUrl(result.download_url)) {
        // Create a temporary link to trigger download
        const link = document.createElement('a')
        link.href = result.download_url
        link.download = isImage ? 'screenshot.png' : 'attachment'
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      }
    } catch {
      // Failed to get download URL - silently handle
    }
  }

  // For legacy attachments that only have filename (not uploaded to S3)
  if (!isFileId) {
    return (
      <div className="border rounded-md overflow-hidden">
        <div className="flex items-center justify-between p-2 bg-muted/50">
          <div className="flex items-center gap-2">
            {isImage ? (
              <FileImageIcon className="h-4 w-4 text-muted-foreground" />
            ) : (
              <FileText className="h-4 w-4 text-muted-foreground" />
            )}
            <div>
              <p className="text-sm font-medium">{fileId}</p>
              <p className="text-xs text-muted-foreground">
                {attachment.file_type} - {(attachment.file_size_bytes / 1024).toFixed(2)} KB
              </p>
            </div>
          </div>
        </div>
        <div className="p-3 text-center text-sm text-muted-foreground bg-muted/30">
          File not available for preview
        </div>
      </div>
    )
  }

  return (
    <div className="border rounded-md overflow-hidden">
      <div className="flex items-center justify-between p-2 bg-muted/50">
        <div className="flex items-center gap-2">
          {isImage ? (
            <FileImageIcon className="h-4 w-4 text-muted-foreground" />
          ) : (
            <FileText className="h-4 w-4 text-muted-foreground" />
          )}
          <div>
            <p className="text-sm font-medium">
              {isImage ? 'Screenshot' : 'Attachment'}
            </p>
            <p className="text-xs text-muted-foreground">
              {attachment.file_type} - {(attachment.file_size_bytes / 1024).toFixed(2)} KB
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={handleDownload}>
          <Download className="h-4 w-4" />
        </Button>
      </div>

      {isImage && (
        <div className="p-2">
          <FileImageWithPreview
            fileId={fileId}
            hasThumbnail={false}
            alt="Feedback attachment"
            className="w-full max-h-64 rounded"
            imageClassName="object-contain"
            mode="thumbnail"
            enablePreview={true}
          />
        </div>
      )}
    </div>
  )
}
