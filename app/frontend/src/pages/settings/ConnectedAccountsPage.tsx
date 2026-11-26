import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Loader2 } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConnectedAccountCard } from '@/components/connected-accounts/ConnectedAccountCard'
import { UnlinkConfirmDialog } from '@/components/connected-accounts/UnlinkConfirmDialog'
import { UnlinkWithSetupWizard } from '@/components/connected-accounts/UnlinkWithSetupWizard'
import {
  useGetUserIdentitiesQuery,
  useUnlinkIdentityMutation,
} from '@/store/api/identityApi'
import type { UserIdentityResponse } from '@/types/identity'

export function ConnectedAccountsPage() {
  const { t } = useTranslation(['settings'])
  const { data, isLoading, error, refetch } = useGetUserIdentitiesQuery()
  const [unlinkIdentity, { isLoading: isUnlinking }] = useUnlinkIdentityMutation()

  const [selectedIdentity, setSelectedIdentity] = useState<UserIdentityResponse | null>(null)
  const [showSimpleUnlink, setShowSimpleUnlink] = useState(false)
  const [showSetupWizard, setShowSetupWizard] = useState(false)

  const handleUnlinkClick = (identity: UserIdentityResponse) => {
    setSelectedIdentity(identity)

    if (data?.requires_setup_for_unlink) {
      setShowSetupWizard(true)
    } else {
      setShowSimpleUnlink(true)
    }
  }

  const handleSimpleUnlink = async () => {
    if (!selectedIdentity) return

    try {
      await unlinkIdentity({ provider: selectedIdentity.provider }).unwrap()
      const providerName = t(`settings:connectedAccounts.providers.${selectedIdentity.provider}`, {
        defaultValue: selectedIdentity.provider.charAt(0).toUpperCase() + selectedIdentity.provider.slice(1),
      })
      toast.success(t('settings:connectedAccounts.unlinkSuccess', { provider: providerName }))
      setShowSimpleUnlink(false)
      setSelectedIdentity(null)
      refetch()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('common:error'))
    }
  }

  const handleSetupComplete = () => {
    setShowSetupWizard(false)
    setSelectedIdentity(null)
    refetch()
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('settings:connectedAccounts.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:connectedAccounts.error.description')}</AlertDescription>
      </Alert>
    )
  }

  if (!data) {
    return (
      <Alert>
        <AlertTitle>{t('settings:connectedAccounts.error.title')}</AlertTitle>
        <AlertDescription>{t('settings:connectedAccounts.error.noData')}</AlertDescription>
      </Alert>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:connectedAccounts.title')}</CardTitle>
          <CardDescription>{t('settings:connectedAccounts.description')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data.identities.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {t('settings:connectedAccounts.noIdentities')}
            </p>
          ) : (
            data.identities.map((identity) => (
              <ConnectedAccountCard
                key={identity.id}
                identity={identity}
                onUnlink={handleUnlinkClick}
                isUnlinking={isUnlinking && selectedIdentity?.id === identity.id}
              />
            ))
          )}
        </CardContent>
      </Card>

      {selectedIdentity && (
        <>
          <UnlinkConfirmDialog
            open={showSimpleUnlink}
            onOpenChange={setShowSimpleUnlink}
            provider={selectedIdentity.provider}
            onConfirm={handleSimpleUnlink}
            isLoading={isUnlinking}
          />

          <UnlinkWithSetupWizard
            open={showSetupWizard}
            onOpenChange={setShowSetupWizard}
            provider={selectedIdentity.provider}
            twoFactorPolicy={data.two_factor_policy}
            onComplete={handleSetupComplete}
          />
        </>
      )}
    </>
  )
}
