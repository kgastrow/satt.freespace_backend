import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import {
  X,
  UserCog,
  Loader2,
  Eye,
  RotateCcw,
  ChevronDown,
  CheckCircle,
  Clock,
  AlertCircle,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { toast } from '@/lib/toast'
import { format } from 'date-fns'
import {
  useRevokeUserTypeMutation,
  useResetUserTypeOnboardingMutation,
  type UserFullDetail,
  type UserTypeOnboardingInfo,
} from '@/features/users/usersApi'

interface UserTypesCardProps {
  user: UserFullDetail
  isSuperAdmin: boolean
}

function OnboardingStatusBadge({ status }: { status: string }) {
  const { t } = useTranslation('admin')

  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'completed':
        return {
          variant: 'default' as const,
          icon: <CheckCircle className="h-3 w-3 mr-1" />,
          className: 'bg-green-100 text-green-700 hover:bg-green-100',
        }
      case 'in_progress':
        return {
          variant: 'secondary' as const,
          icon: <Clock className="h-3 w-3 mr-1" />,
          className: 'bg-blue-100 text-blue-700 hover:bg-blue-100',
        }
      case 'pending':
        return {
          variant: 'outline' as const,
          icon: <AlertCircle className="h-3 w-3 mr-1" />,
          className: '',
        }
      default:
        return {
          variant: 'outline' as const,
          icon: null,
          className: '',
        }
    }
  }

  const config = getStatusConfig(status)

  return (
    <Badge variant={config.variant} className={config.className}>
      {config.icon}
      {t(`users.onboardingStatus.${status}`)}
    </Badge>
  )
}

function UserTypeItem({
  userType,
  userId,
  isSuperAdmin,
}: {
  userType: UserTypeOnboardingInfo
  userId: string
  isSuperAdmin: boolean
}) {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()

  const [showRevokeDialog, setShowRevokeDialog] = useState(false)
  const [showResetDialog, setShowResetDialog] = useState(false)

  const [revokeUserType, { isLoading: isRevoking }] = useRevokeUserTypeMutation()
  const [resetOnboarding, { isLoading: isResetting }] = useResetUserTypeOnboardingMutation()

  const handleViewOnboarding = () => {
    navigate(`/admin/users/${userId}/onboarding/${userType.id}`)
  }

  const handleRevoke = async () => {
    try {
      await revokeUserType({ userId, userTypeId: userType.id }).unwrap()
      toast.success(t('users.detail.userTypeRevoked'))
      setShowRevokeDialog(false)
    } catch {
      toast.error(t('users.detail.userTypeRevokeFailed'))
    }
  }

  const handleResetOnboarding = async () => {
    try {
      await resetOnboarding({ userId, userTypeId: userType.id }).unwrap()
      toast.success(t('users.detail.onboardingReset'))
      setShowResetDialog(false)
    } catch {
      toast.error(t('users.detail.onboardingResetFailed'))
    }
  }

  return (
    <>
      <div className="flex items-center justify-between p-3 rounded-md bg-muted/50">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">{userType.name}</p>
            <OnboardingStatusBadge status={userType.onboarding_status} />
          </div>
          <p className="text-xs text-muted-foreground">{userType.code}</p>
          {userType.onboarded_at && (
            <p className="text-xs text-muted-foreground mt-1">
              {t('users.detail.onboardedAt', {
                date: format(new Date(userType.onboarded_at), 'PP'),
              })}
            </p>
          )}
        </div>

        {isSuperAdmin && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm">
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleViewOnboarding}>
                <Eye className="h-4 w-4 mr-2" />
                {t('users.detail.actions.viewOnboarding')}
              </DropdownMenuItem>
              {userType.onboarding_status === 'completed' && (
                <DropdownMenuItem onClick={() => setShowResetDialog(true)}>
                  <RotateCcw className="h-4 w-4 mr-2" />
                  {t('users.detail.actions.resetOnboarding')}
                </DropdownMenuItem>
              )}
              <DropdownMenuItem
                onClick={() => setShowRevokeDialog(true)}
                className="text-destructive"
              >
                <X className="h-4 w-4 mr-2" />
                {t('users.detail.actions.revokeUserType')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      {/* Revoke Dialog */}
      <AlertDialog open={showRevokeDialog} onOpenChange={setShowRevokeDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.detail.revokeUserTypeTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.detail.revokeUserTypeDescription', { name: userType.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevoke}
              disabled={isRevoking}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isRevoking ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {t('users.detail.actions.revokeUserType')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset Onboarding Dialog */}
      <AlertDialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.detail.resetOnboardingTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.detail.resetOnboardingDescription', { name: userType.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleResetOnboarding} disabled={isResetting}>
              {isResetting ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {t('users.detail.actions.resetOnboarding')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

export function UserTypesCard({ user, isSuperAdmin }: UserTypesCardProps) {
  const { t } = useTranslation('admin')

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <UserCog className="h-5 w-5" />
          {t('users.detail.sections.userTypes')}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {user.user_types.length > 0 ? (
          <div className="space-y-2">
            {user.user_types.map((ut) => (
              <UserTypeItem
                key={ut.id}
                userType={ut}
                userId={user.id}
                isSuperAdmin={isSuperAdmin}
              />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('users.detail.noUserTypes')}</p>
        )}
      </CardContent>
    </Card>
  )
}
