import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { UserX } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { useImpersonation } from '@/hooks/useImpersonation'

/**
 * ImpersonationIndicator - Compact header indicator shown when in impersonation mode
 * Displays target user info as a pill/badge with an "End" button
 * Designed to fit in the header without obscuring other UI elements
 */
export function ImpersonationIndicator() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const { isImpersonating, targetUser, endImpersonation, isEnding } = useImpersonation()

  const handleEndImpersonation = async () => {
    try {
      const result = await endImpersonation()
      if ('data' in result) {
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
    <div className="flex items-center gap-2 rounded-full bg-yellow-500 pl-3 pr-1 py-1 text-yellow-950">
      <UserX className="h-4 w-4 shrink-0" />
      <span className="text-sm font-medium truncate max-w-[200px]">
        {targetUser.first_name} {targetUser.last_name}
      </span>
      <Button
        onClick={handleEndImpersonation}
        disabled={isEnding}
        variant="secondary"
        size="sm"
        className="h-6 rounded-full bg-yellow-950 text-yellow-50 hover:bg-yellow-900 text-xs px-2"
      >
        {isEnding ? t('impersonation.banner.ending') : t('impersonation.indicator.end')}
      </Button>
    </div>
  )
}
