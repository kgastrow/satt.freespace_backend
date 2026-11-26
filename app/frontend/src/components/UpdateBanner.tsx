/**
 * UpdateBanner — "a new version is available" prompt.
 *
 * It appears only once the new build is fully staged on the device (see
 * `useAppUpdate`), so the CTA applies it from local cache rather than kicking
 * off a cold download the user has to sit through. Most updates never reach it
 * at all — `useAutoApplyUpdate` swaps them in while the app is backgrounded.
 * This is the exception path: a device that could not be updated quietly.
 *
 * Placement: bottom-right, out of the way of the top-of-page install banner and
 * of the toaster. A fork that adds a persistent overlay — a player, a chat
 * launcher, a cookie bar — must move this so it does not cover it.
 *
 * Dismissal is remembered per deployed commit (see `useAppUpdate`), so "Not
 * now" means not until the next deploy — not "again in five minutes".
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { RefreshCw, X } from 'lucide-react'
import { useAppUpdate } from '@/hooks/useAppUpdate'
import { useAutoApplyUpdate } from '@/hooks/useAutoApplyUpdate'
import { Button } from '@/components/ui/button'

export function UpdateBanner() {
  const { t } = useTranslation('common')
  const { updateReady, staged, applyUpdate, dismissUpdate } = useAppUpdate()
  const [isDismissed, setIsDismissed] = useState(false)

  // Mounted here rather than in its own component so the app keeps exactly one
  // `useAppUpdate` — a second instance would mean a second version-check poller.
  useAutoApplyUpdate({ staged, applyUpdate })

  const dismiss = () => {
    setIsDismissed(true)
    dismissUpdate()
  }

  if (!updateReady || isDismissed) {
    return null
  }

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-4 bottom-[calc(env(safe-area-inset-bottom)+1rem)] z-50 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[360px]"
    >
      <div className="relative rounded-lg border bg-card p-4 shadow-lg">
        <Button
          onClick={dismiss}
          size="icon-sm"
          variant="ghost"
          aria-label={t('updatePrompt.dismiss')}
          className="absolute right-2 top-2 text-muted-foreground"
        >
          <X className="size-4" />
        </Button>

        <div className="flex items-start gap-3">
          <div className="bg-primary/10 flex size-9 shrink-0 items-center justify-center rounded-md">
            <RefreshCw className="text-primary size-4" />
          </div>
          <div className="min-w-0 pr-6">
            <h2 className="text-sm font-semibold">{t('updatePrompt.title')}</h2>
            <p className="text-muted-foreground mt-1 text-xs leading-relaxed">
              {t('updatePrompt.message')}
            </p>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Button onClick={applyUpdate} size="sm" className="flex-1">
            {t('updatePrompt.apply')}
          </Button>
          <Button onClick={dismiss} size="sm" variant="ghost">
            {t('updatePrompt.later')}
          </Button>
        </div>
      </div>
    </div>
  )
}
