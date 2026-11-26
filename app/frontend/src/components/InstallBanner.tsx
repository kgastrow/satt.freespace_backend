import { useTranslation } from 'react-i18next'
import { Download, X } from 'lucide-react'
import { useInstallPrompt } from '@/hooks/useInstallPrompt'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { setPwaInstallDismissed } from '@/features/preferences'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function InstallBanner() {
  const { t } = useTranslation('common')
  const dispatch = useAppDispatch()
  const { isInstallable, isInstalled, isMobile, promptInstall, isPWAEnabled } = useInstallPrompt()
  const dismissed = useAppSelector((state) => state.preferences.pwaInstallDismissed)

  if (!isPWAEnabled || dismissed || isInstalled || !isInstallable || !isMobile) {
    return null
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50">
      <Alert className="rounded-none border-x-0 border-t-0 bg-primary/10 border-primary/20">
        <AlertDescription className="flex items-center justify-between w-full">
          <span className="flex items-center gap-2 text-primary">
            <Download className="size-4" />
            {t('installBanner.message')}
          </span>
          <div className="flex items-center gap-2 ml-4">
            <Button
              onClick={promptInstall}
              size="sm"
              variant="default"
              className="bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {t('installBanner.install')}
            </Button>
            <Button
              onClick={() => dispatch(setPwaInstallDismissed(true))}
              size="icon-sm"
              variant="ghost"
              className="text-primary hover:bg-primary/20"
              aria-label={t('installBanner.dismiss')}
            >
              <X className="size-4" />
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  )
}
