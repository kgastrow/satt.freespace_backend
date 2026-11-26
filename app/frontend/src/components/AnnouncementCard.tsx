import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { Announcement } from '@/types/announcement'

interface AnnouncementCardProps {
  announcement: Announcement
  onDismiss?: (announcementId: string) => void
  position?: number
  totalCount?: number
  className?: string
  fullImageUrl?: string
}

/**
 * AnnouncementCard - Individual announcement card component
 * Displays announcement details with optional featured image, CTA button, and dismiss functionality
 *
 * @param announcement - Announcement data
 * @param onDismiss - Callback when dismiss button clicked (only shown if announcement.is_dismissible)
 * @param position - Position in stack (1-based index for badge display)
 * @param totalCount - Total number of announcements (for badge display)
 * @param className - Additional CSS classes for styling
 */
export function AnnouncementCard({
  announcement,
  onDismiss,
  position,
  totalCount,
  className,
  fullImageUrl,
}: AnnouncementCardProps) {
  const { t } = useTranslation('common')
  const navigate = useNavigate()
  const [isLightboxOpen, setIsLightboxOpen] = useState(false)

  // Determine background color with fallback based on priority
  const getBackgroundColor = () => {
    if (announcement.background_color) {
      return announcement.background_color
    }

    // Default colors by priority - uses theme-aware semantic colors
    switch (announcement.priority) {
      case 'critical':
        return 'bg-destructive/10'
      case 'high':
        return 'bg-warning/10'
      case 'normal':
        return 'bg-info/10'
      case 'low':
        return 'bg-muted'
      default:
        return 'bg-info/10'
    }
  }

  // Get text color - use custom if set, otherwise auto-detect based on background
  const getTextColor = () => {
    if (announcement.text_color) {
      // Use custom text color if set
      return ''  // Will use inline style instead
    }
    if (announcement.background_color) {
      // If custom background, use dark text (could enhance with luminance detection)
      return 'text-gray-900'
    }
    // Use dark mode compatible text for default backgrounds
    return 'text-gray-900 dark:text-gray-100'
  }

  // Get inline text color style
  const getTextColorStyle = () => {
    if (announcement.text_color && !announcement.text_color.startsWith('text-')) {
      return { color: announcement.text_color }
    }
    return undefined
  }

  // Handle CTA click
  const handleCtaClick = () => {
    if (!announcement.cta_url) return

    // Check if URL is internal (starts with /)
    const isInternalUrl = announcement.cta_url.startsWith('/')

    if (isInternalUrl) {
      navigate(announcement.cta_url)
    } else {
      // External URL - open in new tab
      window.open(announcement.cta_url, '_blank', 'noopener,noreferrer')
    }

    // Dismiss if configured to dismiss on CTA click
    if (announcement.cta_dismisses && onDismiss) {
      onDismiss(announcement.id)
    }
  }

  // Determine CTA button variant
  const getCtaVariant = () => {
    const variant = announcement.cta_button_variant?.toLowerCase()
    switch (variant) {
      case 'default':
      case 'primary':
        return 'default'
      case 'secondary':
        return 'secondary'
      case 'outline':
        return 'outline'
      case 'destructive':
        return 'destructive'
      case 'ghost':
        return 'ghost'
      case 'link':
        return 'link'
      default:
        return 'default'
    }
  }

  const backgroundColorClass =
    announcement.background_color && announcement.background_color.startsWith('bg-')
      ? announcement.background_color
      : ''

  const inlineBackgroundStyle =
    announcement.background_color && !announcement.background_color.startsWith('bg-')
      ? { backgroundColor: announcement.background_color }
      : undefined

  const textColorClass =
    announcement.text_color && announcement.text_color.startsWith('text-')
      ? announcement.text_color
      : ''

  return (
    <div
      className={cn(
        'relative rounded-lg border shadow-md overflow-hidden',
        backgroundColorClass || getBackgroundColor(),
        textColorClass || getTextColor(),
        className
      )}
      style={{ ...inlineBackgroundStyle, ...getTextColorStyle() }}
    >
      <div className="p-6">
        {/* Header with title and badge */}
        <div className="flex items-start justify-between gap-4 mb-3">
          <h3 className="text-lg font-semibold flex-1">{announcement.title}</h3>

          {/* Badge showing position */}
          {position !== undefined && totalCount !== undefined && totalCount > 1 && (
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-foreground/10">
              {t('announcements.badge', { position, total: totalCount })}
            </span>
          )}
        </div>

        {/* Featured image - using thumbnail if available, falling back to full image */}
        {announcement.featured_image_url && (
          <div className="mb-4">
            <img
              src={announcement.featured_image_url}
              alt=""
              className={cn(
                'w-full h-48 object-cover rounded-md',
                fullImageUrl && 'cursor-pointer hover:opacity-80'
              )}
              onClick={() => fullImageUrl && setIsLightboxOpen(true)}
              title={fullImageUrl ? t('announcements.viewFullImage') : undefined}
            />
          </div>
        )}

        {/* Body text */}
        <p className="text-sm mb-4 whitespace-pre-wrap">{announcement.body}</p>

        {/* Footer with CTA and Dismiss button */}
        {(announcement.cta_text || announcement.is_dismissible) && (
          <div className="flex items-center justify-between gap-4 mt-4">
            {/* CTA Button */}
            {announcement.cta_text && announcement.cta_url ? (
              <Button
                onClick={handleCtaClick}
                variant={getCtaVariant()}
                size="sm"
                className={cn(
                  announcement.cta_button_color &&
                    announcement.cta_button_color.startsWith('bg-') &&
                    announcement.cta_button_color
                )}
                style={
                  announcement.cta_button_color &&
                  !announcement.cta_button_color.startsWith('bg-')
                    ? { backgroundColor: announcement.cta_button_color }
                    : undefined
                }
              >
                {announcement.cta_text}
              </Button>
            ) : (
              <div />
            )}

            {/* Dismiss button - bottom right */}
            {announcement.is_dismissible && onDismiss && (
              <Button
                onClick={() => onDismiss(announcement.id)}
                variant="destructive"
                size="sm"
              >
                {t('announcements.dismissButton')}
              </Button>
            )}
          </div>
        )}

        {/* Non-dismissible indicator for announcements without dismiss button and without CTA */}
        {!announcement.is_dismissible && !announcement.cta_text && (
          <p className="text-xs mt-4 opacity-70">{t('announcements.nonDismissible')}</p>
        )}
      </div>

      {/* Lightbox Dialog */}
      {fullImageUrl && (
        <Dialog open={isLightboxOpen} onOpenChange={setIsLightboxOpen}>
          <DialogContent className="max-w-[90vw] max-h-[90vh] p-4">
            <DialogTitle className="sr-only">{announcement.title}</DialogTitle>
            <img
              src={fullImageUrl}
              alt={announcement.title}
              className="w-full h-full object-contain max-h-[85vh]"
            />
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
