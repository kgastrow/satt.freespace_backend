import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Shield, ShieldAlert, RefreshCw, Download, Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  useDisableTwoFactorMutation,
  useGetBackupCodesInfoQuery,
  useRegenerateBackupCodesMutation,
  type UserTwoFactorStatusResponse,
} from '@/store/api/twoFactorApi'
import { getErrorMessage } from '@/types/api'

interface TwoFactorStatusProps {
  status: UserTwoFactorStatusResponse
  onDisableComplete: () => void
}

export function TwoFactorStatus({ status, onDisableComplete }: TwoFactorStatusProps) {
  const { t } = useTranslation(['settings', 'backend'])
  const [disableTwoFactor, { isLoading: isDisabling }] = useDisableTwoFactorMutation()
  const [regenerateBackupCodes, { isLoading: isRegenerating }] = useRegenerateBackupCodesMutation()
  const [showDisableDialog, setShowDisableDialog] = useState(false)
  const [showRegenerateDialog, setShowRegenerateDialog] = useState(false)
  const [showNewCodesDialog, setShowNewCodesDialog] = useState(false)
  const [newBackupCodes, setNewBackupCodes] = useState<string[]>([])
  const [copiedCodes, setCopiedCodes] = useState(false)
  const [password, setPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const { data: backupCodesInfo, isLoading: isLoadingBackupCodes } = useGetBackupCodesInfoQuery(undefined, {
    skip: !status.is_enabled,
  })

  const handleDisable = async () => {
    if (!password) {
      setPasswordError(t('settings:twoFactor.status.disableDialog.passwordRequired'))
      return
    }

    try {
      await disableTwoFactor({ password }).unwrap()
      toast.success(t('settings:twoFactor.status.messages.disableSuccess'))
      setShowDisableDialog(false)
      setPassword('')
      setPasswordError(null)
      onDisableComplete()
    } catch (error) {
      setPasswordError(getErrorMessage(error, t))
    }
  }

  const handleDialogClose = (open: boolean) => {
    setShowDisableDialog(open)
    if (!open) {
      setPassword('')
      setPasswordError(null)
    }
  }

  const handleRegenerateBackupCodes = async () => {
    try {
      const result = await regenerateBackupCodes().unwrap()
      setNewBackupCodes(result.backup_codes)
      setShowRegenerateDialog(false)
      setShowNewCodesDialog(true)
      toast.success(t('settings:twoFactor.status.messages.regenerateSuccess'))
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    }
  }

  const handleCopyAllCodes = async () => {
    const codesText = newBackupCodes.join('\n')
    await navigator.clipboard.writeText(codesText)
    setCopiedCodes(true)
    toast.success(t('settings:twoFactor.status.messages.codesCopied'))
    setTimeout(() => setCopiedCodes(false), 2000)
  }

  const handleDownloadCodes = () => {
    const codesText = newBackupCodes.join('\n')
    const blob = new Blob([codesText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `2fa-backup-codes-${new Date().toISOString().split('T')[0]}.txt`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    toast.success(t('settings:twoFactor.status.messages.exportSuccess'))
  }

  if (!status.is_enabled) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{t('settings:twoFactor.status.disabled.title')}</CardTitle>
              <CardDescription>{t('settings:twoFactor.status.disabled.description')}</CardDescription>
            </div>
            <Badge variant="secondary" className="flex items-center gap-1">
              <ShieldAlert className="h-3 w-3" />
              {t('settings:twoFactor.status.disabled.badge')}
            </Badge>
          </div>
        </CardHeader>
      </Card>
    )
  }

  const verifiedDate = status.verified_at ? new Date(status.verified_at).toLocaleDateString() : null

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{t('settings:twoFactor.status.enabled.title')}</CardTitle>
              <CardDescription>
                {verifiedDate
                  ? t('settings:twoFactor.status.enabled.description', { date: verifiedDate })
                  : t('settings:twoFactor.status.enabled.descriptionNoDate')}
              </CardDescription>
            </div>
            <Badge variant="default" className="flex items-center gap-1 bg-green-600">
              <Shield className="h-3 w-3" />
              {t('settings:twoFactor.status.enabled.badge')}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {backupCodesInfo && (
            <div className="p-3 rounded-md bg-muted">
              <p className="text-sm">
                {t('settings:twoFactor.status.backupCodes.remaining', {
                  remaining: backupCodesInfo.remaining_codes,
                  total: backupCodesInfo.total_codes,
                })}
              </p>
              {backupCodesInfo.remaining_codes <= 2 && (
                <p className="text-sm text-destructive mt-1">
                  {t('settings:twoFactor.status.backupCodes.lowWarning')}
                </p>
              )}
            </div>
          )}
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setShowRegenerateDialog(true)}
              disabled={isLoadingBackupCodes || isRegenerating}
            >
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('settings:twoFactor.status.buttons.regenerate')}
            </Button>
            <Button variant="destructive" onClick={() => setShowDisableDialog(true)}>
              {t('settings:twoFactor.status.buttons.disable')}
            </Button>
          </div>
        </CardContent>
      </Card>

      <AlertDialog open={showDisableDialog} onOpenChange={handleDialogClose}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings:twoFactor.status.disableDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings:twoFactor.status.disableDialog.description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="py-4">
            <Label htmlFor="disable-2fa-password">
              {t('settings:twoFactor.status.disableDialog.passwordLabel')}
            </Label>
            <Input
              id="disable-2fa-password"
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                setPasswordError(null)
              }}
              className="mt-2"
              placeholder={t('settings:twoFactor.status.disableDialog.passwordPlaceholder')}
            />
            {passwordError && (
              <p className="mt-2 text-sm text-destructive">{passwordError}</p>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('settings:twoFactor.status.disableDialog.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDisable} disabled={isDisabling || !password} className="bg-destructive">
              {isDisabling
                ? t('settings:twoFactor.status.disableDialog.disabling')
                : t('settings:twoFactor.status.disableDialog.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={showRegenerateDialog} onOpenChange={setShowRegenerateDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings:twoFactor.status.regenerateDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings:twoFactor.status.regenerateDialog.description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('settings:twoFactor.status.regenerateDialog.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerateBackupCodes} disabled={isRegenerating}>
              {isRegenerating
                ? t('settings:twoFactor.status.regenerateDialog.regenerating')
                : t('settings:twoFactor.status.regenerateDialog.confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={showNewCodesDialog} onOpenChange={setShowNewCodesDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('settings:twoFactor.status.newCodesDialog.title')}</DialogTitle>
            <DialogDescription>
              {t('settings:twoFactor.status.newCodesDialog.description')}
            </DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-2 py-4">
            {newBackupCodes.map((code, index) => (
              <code key={index} className="p-2 bg-muted rounded text-center font-mono text-sm">
                {code}
              </code>
            ))}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleCopyAllCodes} className="flex-1">
              {copiedCodes ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
              {copiedCodes ? t('settings:twoFactor.status.newCodesDialog.copied') : t('settings:twoFactor.status.newCodesDialog.copy')}
            </Button>
            <Button variant="outline" onClick={handleDownloadCodes} className="flex-1">
              <Download className="mr-2 h-4 w-4" />
              {t('settings:twoFactor.status.newCodesDialog.download')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
