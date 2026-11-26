import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { format } from 'date-fns'
import { ShieldCheck, ShieldX, Key, Link2, Mail, Loader2, ShieldOff, KeyRound } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import {
  useAdminDisable2FAMutation,
  useAdminSendPasswordResetMutation,
  type UserFullDetail,
} from '@/features/users/usersApi'

interface UserSecuritySectionProps {
  user: UserFullDetail
  isSuperAdmin?: boolean
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function getProviderIcon(_provider: string) {
  // You could add specific icons for different providers
  return Link2
}

function getProviderDisplayName(provider: string) {
  const displayNames: Record<string, string> = {
    google: 'Google',
    microsoft: 'Microsoft',
    apple: 'Apple',
    github: 'GitHub',
  }
  return displayNames[provider.toLowerCase()] || provider
}

export function UserSecuritySection({ user, isSuperAdmin = false }: UserSecuritySectionProps) {
  const { t } = useTranslation('admin')

  const [showDisable2FADialog, setShowDisable2FADialog] = useState(false)
  const [showPasswordResetDialog, setShowPasswordResetDialog] = useState(false)
  const [adminDisable2FA, { isLoading: isDisabling2FA }] = useAdminDisable2FAMutation()
  const [adminSendPasswordReset, { isLoading: isSendingPasswordReset }] =
    useAdminSendPasswordResetMutation()

  const formatDate = (dateString?: string | null) => {
    if (!dateString) return '-'
    return format(new Date(dateString), 'PPp')
  }

  const handleDisable2FA = async () => {
    try {
      await adminDisable2FA(user.id).unwrap()
      toast.success(t('users.detail.twoFactor.disabled'))
      setShowDisable2FADialog(false)
    } catch {
      toast.error(t('users.detail.twoFactor.disableFailed'))
    }
  }

  const handleSendPasswordReset = async () => {
    try {
      await adminSendPasswordReset(user.id).unwrap()
      toast.success(t('users.detail.passwordReset.sent'))
      setShowPasswordResetDialog(false)
    } catch {
      toast.error(t('users.detail.passwordReset.failed'))
    }
  }

  // Check if user has password-based login (created via email)
  const hasEmailLogin = user.created_via?.toLowerCase() === 'email'

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* 2FA Status */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            {user.two_factor.is_enabled ? (
              <ShieldCheck className="h-5 w-5 text-green-600" />
            ) : (
              <ShieldX className="h-5 w-5 text-muted-foreground" />
            )}
            {t('users.detail.sections.twoFactor')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm">{t('users.detail.twoFactor.status')}</span>
            <Badge variant={user.two_factor.is_enabled ? 'default' : 'secondary'}>
              {user.two_factor.is_enabled
                ? t('users.detail.twoFactor.enabled')
                : t('users.detail.twoFactor.disabled')}
            </Badge>
          </div>

          {user.two_factor.is_enabled && (
            <>
              <div className="flex items-center justify-between">
                <span className="text-sm">{t('users.detail.twoFactor.verifiedAt')}</span>
                <span className="text-sm text-muted-foreground">
                  {formatDate(user.two_factor.verified_at)}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-sm">{t('users.detail.twoFactor.backupCodes')}</span>
                <Badge
                  variant={user.two_factor.backup_codes_remaining > 2 ? 'outline' : 'destructive'}
                >
                  {user.two_factor.backup_codes_remaining} {t('users.detail.twoFactor.remaining')}
                </Badge>
              </div>

              {/* Admin 2FA Disable Button */}
              {isSuperAdmin && (
                <div className="pt-2 border-t">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => setShowDisable2FADialog(true)}
                    className="w-full"
                  >
                    <ShieldOff className="h-4 w-4 mr-2" />
                    {t('users.detail.actions.disable2FA')}
                  </Button>
                  <p className="text-xs text-muted-foreground mt-2">
                    {t('users.detail.twoFactor.disableHelp')}
                  </p>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Disable 2FA Confirmation Dialog */}
      <AlertDialog open={showDisable2FADialog} onOpenChange={setShowDisable2FADialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.detail.disable2FATitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.detail.disable2FADescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDisable2FA}
              disabled={isDisabling2FA}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDisabling2FA ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {t('users.detail.actions.disable2FA')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Login Methods / Identity Providers */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Key className="h-5 w-5" />
            {t('users.detail.sections.loginMethods')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {/* Email/Password Login */}
            {hasEmailLogin && (
              <div className="p-3 rounded-lg bg-muted/50 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Mail className="h-5 w-5" />
                    <div>
                      <p className="text-sm font-medium">
                        {t('users.detail.identityProviders.email')}
                      </p>
                      <p className="text-xs text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <Badge
                    variant="outline"
                    className={
                      user.email_verified
                        ? 'text-green-600 border-green-600'
                        : 'text-amber-600 border-amber-600'
                    }
                  >
                    {user.email_verified
                      ? t('users.detail.verified')
                      : t('users.detail.unverified')}
                  </Badge>
                </div>
                {/* Password Reset Button */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowPasswordResetDialog(true)}
                  className="w-full"
                >
                  <KeyRound className="h-4 w-4 mr-2" />
                  {t('users.detail.actions.sendPasswordReset')}
                </Button>
              </div>
            )}

            {/* OAuth Identity Providers */}
            {user.identity_providers.map((idp) => {
              const ProviderIcon = getProviderIcon(idp.provider)
              return (
                <div
                  key={idp.id}
                  className="flex items-center justify-between p-3 rounded-lg bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <ProviderIcon className="h-5 w-5" />
                    <div>
                      <p className="text-sm font-medium">
                        {getProviderDisplayName(idp.provider)}
                      </p>
                      {idp.provider_email && (
                        <p className="text-xs text-muted-foreground">{idp.provider_email}</p>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {t('users.detail.linkedOn')} {format(new Date(idp.created_time), 'PP')}
                  </span>
                </div>
              )
            })}

            {/* No login methods */}
            {!hasEmailLogin && user.identity_providers.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">
                {t('users.detail.noIdentityProviders')}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Password Reset Confirmation Dialog */}
      <AlertDialog open={showPasswordResetDialog} onOpenChange={setShowPasswordResetDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('users.detail.passwordReset.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('users.detail.passwordReset.description', { email: user.email })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleSendPasswordReset}
              disabled={isSendingPasswordReset}
            >
              {isSendingPasswordReset ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : null}
              {t('users.detail.actions.sendPasswordReset')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
