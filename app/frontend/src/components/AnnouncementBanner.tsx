import { useState, useEffect, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { useAnnouncements } from '@/hooks/useAnnouncements'
import { useAppSelector } from '@/store/hooks'
import { cn } from '@/lib/utils'
import { AnnouncementCard } from '@/components/AnnouncementCard'
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { VisuallyHidden } from '@radix-ui/react-visually-hidden'

const CYCLE_INTERVAL_MS = 10000 // 10 seconds
const TICKER_SPEED = 25 // pixels per second (slower)

/**
 * AnnouncementBanner - Compact inline banner for the app header
 *
 * Features:
 * - Displays announcement title: body inline with ticker for long text
 * - "Learn more" CTA link (if announcement has CTA)
 * - X of Y navigation with prev/next arrows
 * - Dismiss button (X) for dismissible announcements
 * - Auto-cycles through announcements every 10 seconds (pauses on hover)
 * - Click to open full announcement details
 * - Ordered by priority (highest first) then recency (newest first)
 */
export function AnnouncementBanner() {
  const { t } = useTranslation('common')
  const { announcements, dismissAnnouncement, isLoading } = useAnnouncements()
  const [currentIndex, setCurrentIndex] = useState(0)
  const [cycleKey, setCycleKey] = useState(0)
  const [isOverflowing, setIsOverflowing] = useState(false)
  const [isPaused, setIsPaused] = useState(false)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [slideDirection, setSlideDirection] = useState<'left' | 'right'>('right')
  const [animationDuration, setAnimationDuration] = useState(20)
  const textContainerRef = useRef<HTMLButtonElement>(null)
  const textRef = useRef<HTMLSpanElement>(null)
  const isAuthenticated = useAppSelector((state) => state.auth.isAuthenticated)

  // Reset index when announcements change (derive the safe index)
  const safeCurrentIndex = currentIndex >= announcements.length ? 0 : currentIndex

  // Update index state only when it's actually out of bounds
  useEffect(() => {
    if (currentIndex >= announcements.length && announcements.length > 0) {
      // Use setTimeout to avoid setState during render
      const timer = setTimeout(() => setCurrentIndex(0), 0)
      return () => clearTimeout(timer)
    }
  }, [announcements.length, currentIndex])

  // Check if text overflows container and calculate animation duration
  useEffect(() => {
    const checkOverflow = () => {
      if (textContainerRef.current && textRef.current) {
        const containerWidth = textContainerRef.current.offsetWidth
        const textWidth = textRef.current.scrollWidth
        setIsOverflowing(textWidth > containerWidth)

        // Calculate animation duration based on text length
        const duration = (textWidth * 2) / TICKER_SPEED
        setAnimationDuration(duration)
      }
    }

    checkOverflow()
    window.addEventListener('resize', checkOverflow)
    return () => window.removeEventListener('resize', checkOverflow)
  }, [safeCurrentIndex, announcements])

  // Auto-cycle through announcements every 10 seconds (paused on hover or dialog open)
  useEffect(() => {
    if (announcements.length <= 1 || isPaused || isDialogOpen) return

    const interval = setInterval(() => {
      setSlideDirection('right')
      setCurrentIndex((prev) => (prev + 1) % announcements.length)
    }, CYCLE_INTERVAL_MS)

    return () => clearInterval(interval)
  }, [announcements.length, cycleKey, isPaused, isDialogOpen])

  const goToPrev = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setSlideDirection('left')
    setCurrentIndex((prev) => (prev - 1 + announcements.length) % announcements.length)
    setCycleKey((prev) => prev + 1)
  }, [announcements.length])

  const goToNext = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    setSlideDirection('right')
    setCurrentIndex((prev) => (prev + 1) % announcements.length)
    setCycleKey((prev) => prev + 1)
  }, [announcements.length])

  const handleDismiss = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation()
    const announcement = announcements[currentIndex]
    if (!announcement || !announcement.is_dismissible) return
    await dismissAnnouncement(announcement.id)
  }, [announcements, currentIndex, dismissAnnouncement])

  const handleDialogDismiss = useCallback((announcementId: string) => {
    dismissAnnouncement(announcementId)
    setIsDialogOpen(false)
  }, [dismissAnnouncement])

  // Don't render for unauthenticated users or if no announcements
  if (!isAuthenticated || isLoading || announcements.length === 0) {
    return null
  }

  const currentAnnouncement = announcements[safeCurrentIndex]
  if (!currentAnnouncement) return null

  const hasMultiple = announcements.length > 1

  // Get background color for the banner
  const getBannerBackgroundColor = () => {
    if (currentAnnouncement.background_color) {
      // Check if it's a Tailwind class or a hex color
      if (currentAnnouncement.background_color.startsWith('bg-')) {
        return currentAnnouncement.background_color
      }
      return '' // Will use inline style
    }
    // Default based on priority
    switch (currentAnnouncement.priority) {
      case 'critical':
        return 'bg-destructive/10 text-destructive'
      case 'high':
        return 'bg-warning/10 text-warning'
      case 'normal':
        return 'bg-info/10 text-info'
      case 'low':
      default:
        return 'bg-primary/10 text-primary'
    }
  }

  const bannerBgClass = getBannerBackgroundColor()
  const bannerBgStyle = currentAnnouncement.background_color &&
    !currentAnnouncement.background_color.startsWith('bg-')
    ? { backgroundColor: currentAnnouncement.background_color }
    : undefined

  return (
    <>
      <div
        className="flex items-center gap-2 min-w-0 flex-1 px-2 max-w-2xl overflow-hidden"
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        <div
          key={currentAnnouncement.id}
          className={cn(
            'flex items-center gap-2 min-w-0 flex-1 rounded-md px-3 py-1.5 text-sm',
            'transition-opacity',
            slideDirection === 'right' ? 'animate-announcement-slide-in-right' : 'animate-announcement-slide-in-left',
            bannerBgClass
          )}
          style={bannerBgStyle}
        >
          {/* Title : Body with ticker animation - clickable area */}
          <button
            type="button"
            ref={textContainerRef}
            className="min-w-0 flex-1 overflow-hidden text-left hover:opacity-90 cursor-pointer"
            onClick={() => setIsDialogOpen(true)}
            aria-label={t('announcements.viewDetails')}
          >
            <span
              ref={textRef}
              className={cn(
                'inline-block whitespace-nowrap',
                isOverflowing && 'animate-announcement-ticker'
              )}
              style={isOverflowing ? { animationDuration: `${animationDuration}s` } : undefined}
              data-text={`${currentAnnouncement.title}: ${currentAnnouncement.body}`}
            >
              <strong>{currentAnnouncement.title}</strong>: {currentAnnouncement.body}
            </span>
          </button>

          {/* Navigation */}
          {hasMultiple && (
            <span className="flex items-center gap-0.5 shrink-0 text-xs opacity-70">
              <button
                type="button"
                className="p-0.5 rounded hover:bg-foreground/10"
                onClick={goToPrev}
                aria-label={t('announcements.previous')}
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="tabular-nums px-0.5">
                {currentIndex + 1}/{announcements.length}
              </span>
              <button
                type="button"
                className="p-0.5 rounded hover:bg-foreground/10"
                onClick={goToNext}
                aria-label={t('announcements.next')}
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </span>
          )}

          {/* Dismiss */}
          {currentAnnouncement.is_dismissible && (
            <button
              type="button"
              className="p-0.5 rounded hover:bg-destructive/20 shrink-0"
              onClick={handleDismiss}
              aria-label={t('announcements.dismiss')}
            >
              <X className="h-3 w-3 text-destructive" />
            </button>
          )}
        </div>
      </div>

      {/* Full announcement dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl p-0 overflow-hidden" aria-describedby={undefined}>
          <VisuallyHidden>
            <DialogTitle>{currentAnnouncement.title}</DialogTitle>
          </VisuallyHidden>
          <AnnouncementCard
            announcement={currentAnnouncement}
            onDismiss={handleDialogDismiss}
          />
        </DialogContent>
      </Dialog>
    </>
  )
}
