import { useCallback, useEffect, useRef, useState } from 'react'

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

export function useInstallPrompt() {
  const isPWAEnabled = import.meta.env.VITE_ENABLE_PWA === 'true'
  const deferredPrompt = useRef<BeforeInstallPromptEvent | null>(null)
  const [isInstallable, setIsInstallable] = useState(false)
  const [isInstalled, setIsInstalled] = useState(
    () => isPWAEnabled && typeof window !== 'undefined' && window.matchMedia('(display-mode: standalone)').matches
  )
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches
  )

  useEffect(() => {
    if (!isPWAEnabled || isInstalled) return

    const mobileQuery = window.matchMedia('(max-width: 768px)')
    const onMobileChange = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    mobileQuery.addEventListener('change', onMobileChange)

    const onBeforeInstallPrompt = (e: Event) => {
      e.preventDefault()
      deferredPrompt.current = e as BeforeInstallPromptEvent
      setIsInstallable(true)
    }

    const onAppInstalled = () => {
      setIsInstalled(true)
      setIsInstallable(false)
      deferredPrompt.current = null
    }

    window.addEventListener('beforeinstallprompt', onBeforeInstallPrompt)
    window.addEventListener('appinstalled', onAppInstalled)

    return () => {
      mobileQuery.removeEventListener('change', onMobileChange)
      window.removeEventListener('beforeinstallprompt', onBeforeInstallPrompt)
      window.removeEventListener('appinstalled', onAppInstalled)
    }
  }, [isPWAEnabled, isInstalled])

  const promptInstall = useCallback(async () => {
    if (!deferredPrompt.current) return
    await deferredPrompt.current.prompt()
    const { outcome } = await deferredPrompt.current.userChoice
    if (outcome === 'accepted') {
      setIsInstallable(false)
    }
    deferredPrompt.current = null
  }, [])

  return { isInstallable, isInstalled, isMobile, promptInstall, isPWAEnabled }
}
