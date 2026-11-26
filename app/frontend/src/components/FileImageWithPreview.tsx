import { useState, useEffect } from 'react'
import { ImageOff, X, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'
import {
  useLazyGetDownloadUrlQuery,
  useLazyGetThumbnailUrlQuery,
} from '@/features/files/filesApi'

interface FileImageWithPreviewProps {
  /** File ID to fetch URLs for */
  fileId: string
  /** Whether the file has a thumbnail available */
  hasThumbnail?: boolean
  /** Alt text for the image */
  alt: string
  /** Additional CSS classes for the container */
  className?: string
  /** Additional CSS classes for the image */
  imageClassName?: string
  /**
   * Display mode:
   * - 'thumbnail': Show thumbnail, fetch full image only when clicked (default)
   * - 'full': Show full image directly, no thumbnail fetching
   */
  mode?: 'thumbnail' | 'full'
  /** Whether clicking opens the full-size preview (default: true for thumbnail mode, false for full mode) */
  enablePreview?: boolean
  /** Callback when preview is opened */
  onPreviewOpen?: () => void
  /** Callback when preview is closed */
  onPreviewClose?: () => void
}

/**
 * A reusable image component that:
 * - In 'thumbnail' mode: displays thumbnail, fetches full image only on click
 * - In 'full' mode: displays full image directly
 * - Handles loading and error states
 * - Works with both S3 and local storage
 */
export function FileImageWithPreview({
  fileId,
  hasThumbnail = false,
  alt,
  className,
  imageClassName,
  mode = 'thumbnail',
  enablePreview,
  onPreviewOpen,
  onPreviewClose,
}: FileImageWithPreviewProps) {
  const [displayUrl, setDisplayUrl] = useState<string | null>(null)
  const [fullImageUrl, setFullImageUrl] = useState<string | null>(null)
  const [isPreviewOpen, setIsPreviewOpen] = useState(false)
  const [displayError, setDisplayError] = useState(false)
  const [fullImageError, setFullImageError] = useState(false)
  const [isLoadingFull, setIsLoadingFull] = useState(false)

  const [triggerDownload] = useLazyGetDownloadUrlQuery()
  const [triggerThumbnail] = useLazyGetThumbnailUrlQuery()

  // Default enablePreview based on mode if not explicitly set
  const showPreview = enablePreview ?? (mode === 'thumbnail')

  // Fetch the appropriate image on mount based on mode
  useEffect(() => {
    let cancelled = false

    const fetchImage = async () => {
      try {
        if (mode === 'thumbnail' && hasThumbnail) {
          // Thumbnail mode with thumbnail available - fetch thumbnail
          try {
            const result = await triggerThumbnail(fileId).unwrap()
            if (!cancelled) {
              setDisplayUrl(result.thumbnail_url)
              return
            }
          } catch {
            // Thumbnail fetch failed, fall through to full image
          }
        }

        // Full mode OR thumbnail not available - fetch full image
        const result = await triggerDownload(fileId).unwrap()
        if (!cancelled) {
          setDisplayUrl(result.download_url)
          // In full mode, we already have the full image URL
          if (mode === 'full') {
            setFullImageUrl(result.download_url)
          }
        }
      } catch {
        if (!cancelled) setDisplayError(true)
      }
    }

    fetchImage()
    return () => {
      cancelled = true
    }
  }, [fileId, hasThumbnail, mode, triggerDownload, triggerThumbnail])

  // Fetch full image when preview opens (only needed in thumbnail mode)
  const handleOpenPreview = async () => {
    if (!showPreview) return

    setIsPreviewOpen(true)
    onPreviewOpen?.()

    // Only fetch full image if we don't have it yet (thumbnail mode)
    if (!fullImageUrl && !isLoadingFull) {
      setIsLoadingFull(true)
      try {
        const result = await triggerDownload(fileId).unwrap()
        setFullImageUrl(result.download_url)
      } catch {
        setFullImageError(true)
      } finally {
        setIsLoadingFull(false)
      }
    }
  }

  const handleClosePreview = () => {
    setIsPreviewOpen(false)
    onPreviewClose?.()
  }

  // Render error state
  if (displayError) {
    return (
      <div className={cn('flex items-center justify-center bg-muted', className)}>
        <ImageOff className="h-6 w-6 text-muted-foreground" />
      </div>
    )
  }

  // Render loading state
  if (!displayUrl) {
    return <div className={cn('animate-pulse bg-muted', className)} />
  }

  return (
    <>
      {/* Display image (thumbnail or full based on mode) */}
      <div
        className={cn(
          'overflow-hidden',
          showPreview && 'cursor-pointer hover:opacity-90 transition-opacity',
          className
        )}
        onClick={showPreview ? handleOpenPreview : undefined}
      >
        <img
          src={displayUrl}
          alt={alt}
          width={200}
          height={200}
          className={cn('h-full w-full object-cover', imageClassName)}
          onError={() => setDisplayError(true)}
          loading="lazy"
        />
      </div>

      {/* Full-size preview modal */}
      {showPreview && (
        <Dialog open={isPreviewOpen} onOpenChange={handleClosePreview}>
          <DialogContent className="max-w-[90vw] max-h-[90vh] p-0 overflow-hidden">
            <VisuallyHidden>
              <DialogTitle>{alt}</DialogTitle>
            </VisuallyHidden>
            <button
              onClick={handleClosePreview}
              className="absolute top-2 right-2 z-10 rounded-full bg-black/50 p-2 text-white hover:bg-black/70 transition-colors"
              aria-label="Close preview"
            >
              <X className="h-5 w-5" />
            </button>
            <div className="flex items-center justify-center min-h-[200px] bg-black/5">
              {isLoadingFull ? (
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              ) : fullImageError ? (
                <div className="flex flex-col items-center gap-2 text-muted-foreground">
                  <ImageOff className="h-12 w-12" />
                  <span>Failed to load image</span>
                </div>
              ) : fullImageUrl ? (
                <img
                  src={fullImageUrl}
                  alt={alt}
                  width={800}
                  height={600}
                  className="max-w-full max-h-[85vh] object-contain"
                  onError={() => setFullImageError(true)}
                  loading="lazy"
                />
              ) : null}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  )
}
