import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import { DropdownMenuItem } from '@/components/ui/dropdown-menu'
import { useImpersonation } from '@/hooks/useImpersonation'
import { useAppSelector } from '@/store/hooks'

// Minimal interface for the user properties needed by this component
interface ImpersonableUser {
  id: string
  first_name?: string | null
  last_name?: string | null
  is_admin?: boolean | null
}

interface ImpersonationButtonProps {
  user: ImpersonableUser
  variant?: 'button' | 'menuItem'
}

/**
 * ImpersonationButton - Action button/menu item for starting impersonation
 * Can be rendered as a standalone button or a dropdown menu item
 * Visible only to super admins, disabled for super admin users and self
 */
export function ImpersonationButton({ user, variant = 'menuItem' }: ImpersonationButtonProps) {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const { startImpersonation, isStarting } = useImpersonation()
  const currentUser = useAppSelector((state) => state.auth.user)

  const handleStartImpersonation = async () => {
    try {
      const result = await startImpersonation(user.id)
      if ('data' in result) {
        toast.success(
          t('impersonation.button.startSuccess', {
            firstName: user.first_name,
            lastName: user.last_name,
          }),
          { category: 'auth' }
        )
        navigate('/dashboard')
      } else {
        toast.error(t('impersonation.button.startError'), { category: 'auth' })
      }
    } catch {
      toast.error(t('impersonation.button.startError'), { category: 'auth' })
    }
  }

  if (!currentUser?.is_admin) {
    return null
  }

  const isSelf = currentUser.id === user.id
  const isSuperAdmin = user.is_admin
  const isDisabled = isSelf || isSuperAdmin || isStarting

  if (variant === 'button') {
    return (
      <Button
        onClick={handleStartImpersonation}
        disabled={isDisabled}
        variant="outline"
        size="sm"
      >
        {isStarting ? t('impersonation.button.starting') : t('impersonation.button.label')}
      </Button>
    )
  }

  return (
    <DropdownMenuItem onClick={handleStartImpersonation} disabled={isDisabled}>
      {isStarting ? t('impersonation.button.starting') : t('impersonation.button.label')}
    </DropdownMenuItem>
  )
}
