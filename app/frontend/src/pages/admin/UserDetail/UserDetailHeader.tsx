import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { Ban, CheckCircle, Trash2 } from 'lucide-react'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { ImpersonationButton } from '@/components/ImpersonationButton'
import { toast } from '@/lib/toast'
import {
  useSuspendUserMutation,
  useUnsuspendUserMutation,
  useDeleteUserMutation,
  type UserFullDetail,
} from '@/features/users/usersApi'
import { usePermission } from '@/hooks/usePermission'

interface UserDetailHeaderProps {
  user: UserFullDetail
}

export function UserDetailHeader({ user }: UserDetailHeaderProps) {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const { canWrite, canDelete } = usePermission('users')

  const [isSuspendDialogOpen, setIsSuspendDialogOpen] = useState(false)
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)

  const [suspendUser, { isLoading: isSuspending }] = useSuspendUserMutation()
  const [unsuspendUser, { isLoading: isUnsuspending }] = useUnsuspendUserMutation()
  const [deleteUser, { isLoading: isDeleting }] = useDeleteUserMutation()

  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email
  const isSuspended = user.suspension_status === 'suspended'

  const getInitials = () => {
    const first = user.first_name?.charAt(0) || ''
    const last = user.last_name?.charAt(0) || ''
    return (first + last).toUpperCase() || user.email.charAt(0).toUpperCase()
  }

  const handleSuspendToggle = async () => {
    try {
      if (isSuspended) {
        await unsuspendUser(user.id).unwrap()
        toast.success(t('users.detail.toast.unsuspendSuccess'))
      } else {
        await suspendUser({ id: user.id, send_notification: true }).unwrap()
        toast.success(t('users.detail.toast.suspendSuccess'))
      }
      setIsSuspendDialogOpen(false)
    } catch {
      toast.error(isSuspended ? t('users.detail.toast.unsuspendError') : t('users.detail.toast.suspendError'))
    }
  }

  const handleDelete = async () => {
    try {
      await deleteUser(user.id).unwrap()
      toast.success(t('users.detail.toast.deleteSuccess'))
      navigate('/admin/users')
    } catch {
      toast.error(t('users.detail.toast.deleteError'))
    }
  }

  const getStatusBadge = () => {
    if (isSuspended) {
      return <Badge variant="destructive">{t('users.status.suspended')}</Badge>
    }
    return <Badge variant="default">{t('users.status.active')}</Badge>
  }

  return (
    <>
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row gap-6 items-start md:items-center">
            <Avatar className="h-20 w-20 text-2xl">
              {user.avatar_url && (
                <AvatarImage src={user.avatar_url} alt={fullName} />
              )}
              <AvatarFallback className="text-2xl font-medium">
                {getInitials()}
              </AvatarFallback>
            </Avatar>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-bold truncate">{fullName}</h1>
                {getStatusBadge()}
                {user.is_admin && (
                  <Badge variant="secondary">{t('users.badges.admin')}</Badge>
                )}
              </div>
              <p className="text-muted-foreground mt-1">{user.email}</p>
              {user.phone && (
                <p className="text-muted-foreground text-sm">{user.phone}</p>
              )}
            </div>

            <div className="flex flex-wrap gap-2">
              <ImpersonationButton user={user} variant="button" />

              {canWrite && (
                <Button
                  variant={isSuspended ? 'default' : 'secondary'}
                  size="sm"
                  onClick={() => setIsSuspendDialogOpen(true)}
                  disabled={isSuspending || isUnsuspending}
                >
                  {isSuspended ? (
                    <>
                      <CheckCircle className="h-4 w-4 mr-2" />
                      {t('users.actions.unsuspend')}
                    </>
                  ) : (
                    <>
                      <Ban className="h-4 w-4 mr-2" />
                      {t('users.actions.suspend')}
                    </>
                  )}
                </Button>
              )}

              {canDelete && (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setIsDeleteDialogOpen(true)}
                  disabled={isDeleting}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {t('users.actions.delete')}
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <ConfirmDialog
        open={isSuspendDialogOpen}
        onOpenChange={setIsSuspendDialogOpen}
        onConfirm={handleSuspendToggle}
        title={isSuspended ? t('users.detail.unsuspendDialog.title') : t('users.detail.suspendDialog.title')}
        description={
          isSuspended
            ? t('users.detail.unsuspendDialog.description', { name: fullName })
            : t('users.detail.suspendDialog.description', { name: fullName })
        }
        confirmLabel={isSuspended ? t('users.actions.unsuspend') : t('users.actions.suspend')}
        cancelLabel={t('common.cancel')}
        isLoading={isSuspending || isUnsuspending}
        variant={isSuspended ? 'default' : 'destructive'}
      />

      <ConfirmDialog
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        onConfirm={handleDelete}
        title={t('users.detail.deleteDialog.title')}
        description={t('users.detail.deleteDialog.description', { name: fullName })}
        confirmLabel={t('users.actions.delete')}
        cancelLabel={t('common.cancel')}
        isLoading={isDeleting}
        variant="destructive"
      />
    </>
  )
}
