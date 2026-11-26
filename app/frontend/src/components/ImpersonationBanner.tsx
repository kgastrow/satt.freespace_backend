import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { useImpersonation } from '@/hooks/useImpersonation'

/**
 * ImpersonationBanner - Fixed banner shown at top of viewport when in impersonation mode
 * Displays target user info and provides "End Impersonation" button
 * Uses distinctive warning colors to clearly indicate impersonation mode
 */
export function ImpersonationBanner() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const { isImpersonating, targetUser, endImpersonation, isEnding } = useImpersonation()

  const handleEndImpersonation = async () => {
    try {
      const result = await endImpersonation()
      if (result.data) {
        toast.success(t('impersonation.banner.endSuccess'), { category: 'auth' })
        navigate('/dashboard')
      } else {
        toast.error(t('impersonation.banner.endError'), { category: 'auth' })
      }
    } catch {
      toast.error(t('impersonation.banner.endError'), { category: 'auth' })
    }
  }

  if (!isImpersonating || !targetUser) {
    return null
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-yellow-500 text-yellow-950 border-b-2 border-yellow-600">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-1">
          <span className="font-semibold">{t('impersonation.banner.viewing')}</span>
          <span className="font-medium">
            {targetUser.first_name} {targetUser.last_name} ({targetUser.email})
          </span>
        </div>
        <Button
          onClick={handleEndImpersonation}
          disabled={isEnding}
          variant="secondary"
          size="sm"
          className="bg-yellow-950 text-yellow-50 hover:bg-yellow-900"
        >
          {isEnding ? t('impersonation.banner.ending') : t('impersonation.banner.endButton')}
        </Button>
      </div>
    </div>
  )
}
