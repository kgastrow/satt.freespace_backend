import { toast } from '@/lib/toast'
import { useTranslation } from 'react-i18next'
import { useAppSelector } from '@/store/hooks'
import { PageHeader } from '@/components/PageHeader'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { OrganizationDetailsForm } from '@/components/OrganizationDetailsForm'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { CardSkeleton } from '@/components/skeletons'
import { useState } from 'react'
import {
  useGetOrganizationQuery,
  useRequestOrganizationDeletionMutation,
  useCancelOrganizationDeletionRequestMutation,
} from '@/features/organizations/organizationsApi'

export function OrganizationSettingsPage() {
  const { t } = useTranslation('settings')
  const user = useAppSelector((state) => state.auth.user)
  const organizationId = user?.organization_id

  const { data: organization, isLoading, error } = useGetOrganizationQuery(organizationId!, {
    skip: !organizationId,
  })

  const [requestDeletion, { isLoading: isRequesting }] = useRequestOrganizationDeletionMutation()
  const [cancelDeletion, { isLoading: isCanceling }] = useCancelOrganizationDeletionRequestMutation()

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showCancelConfirm, setShowCancelConfirm] = useState(false)

  // Check if user is organization owner
  const isOwner = user?.roles?.includes('owner') ?? false

  const handleRequestDeletion = async () => {
    if (!organizationId) return
    try {
      await requestDeletion(organizationId).unwrap()
      toast.success(t('organization.messages.deletionRequestSuccess'))
      setShowDeleteConfirm(false)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('organization.messages.deletionRequestError'))
    }
  }

  const handleCancelDeletion = async () => {
    if (!organizationId) return
    try {
      await cancelDeletion(organizationId).unwrap()
      toast.success(t('organization.messages.deletionCancelSuccess'))
      setShowCancelConfirm(false)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('organization.messages.deletionCancelError'))
    }
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-8 w-64 mb-2" />
          <Skeleton className="h-4 w-96 mb-6" />
        </div>
        <CardSkeleton variant="default" />
        <CardSkeleton variant="default" />
      </div>
    )
  }

  // Check if user has organization and appropriate role
  // Super admins (is_admin) have access to all organization settings
  const hasOrgAccess = organizationId && (user?.is_admin || isOwner || user?.roles?.includes('admin'))

  if (!organizationId) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('organization.title')}
          description={t('organization.description')}
        />
        <Alert>
          <AlertTitle>{t('organization.alerts.notAvailable.title')}</AlertTitle>
          <AlertDescription>
            {t('organization.alerts.notAvailable.description')}{' '}
            <a href="/admin/organizations" className="font-medium underline">
              {t('organization.alerts.notAvailable.link')}
            </a>.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!hasOrgAccess) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('organization.title')}
          description={t('organization.description')}
        />
        <Alert>
          <AlertTitle>{t('organization.alerts.accessRestricted.title')}</AlertTitle>
          <AlertDescription>
            {t('organization.alerts.accessRestricted.description')}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (error) {
    const apiError = error as { status?: number; data?: { detail?: string } } | undefined
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('organization.title')}
          description={t('organization.description')}
        />
        <Alert variant="destructive">
          <AlertTitle>{t('organization.alerts.error.title')}</AlertTitle>
          <AlertDescription>
            {apiError?.data?.detail ||
             (apiError?.status === 403 ? t('organization.alerts.error.permissionDenied') :
              apiError?.status === 404 ? t('organization.alerts.error.notFound') :
              `${t('organization.alerts.error.unknownStatus')} ${apiError?.status || 'unknown'}`)}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (!organization) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={t('organization.title')}
          description={t('organization.description')}
        />
        <Alert variant="destructive">
          <AlertTitle>{t('organization.alerts.error.title')}</AlertTitle>
          <AlertDescription>
            {t('organization.alerts.error.dataNotAvailable')} {organizationId}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('organization.title')}
        description={t('organization.description')}
      />

      {/* Organization Details */}
      <Card>
        <CardHeader>
          <CardTitle>{t('organization.sections.details.title')}</CardTitle>
          <CardDescription>
            {t('organization.sections.details.description')}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <p className="text-sm font-medium text-muted-foreground">{t('organization.fields.name')}</p>
              <p className="text-lg">{organization.name}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">{t('organization.fields.slug')}</p>
              <p className="text-lg">
                <code className="rounded bg-muted px-2 py-1">{organization.slug}</code>
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">{t('organization.fields.status')}</p>
              <div className="mt-1">
                <Badge variant={organization.is_active ? 'default' : 'secondary'}>
                  {organization.is_active ? t('organization.status.active') : t('organization.status.inactive')}
                </Badge>
              </div>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">{t('organization.fields.created')}</p>
              <p className="text-lg">{formatDate(organization.created_time)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Organization Details Form - for owners and admins */}
      {hasOrgAccess && (
        <OrganizationDetailsForm
          organizationId={organizationId}
          variant="card"
        />
      )}

      {/* Deletion Request Status */}
      {organization.deletion_requested && (
        <Alert variant="destructive">
          <AlertTitle>{t('organization.deletionRequest.title')}</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>
              {t('organization.deletionRequest.submittedOn')}{' '}
              <strong>{formatDate(organization.deletion_requested_time!)}</strong>.
            </p>
            <p>
              {t('organization.deletionRequest.retentionNotice')}
            </p>
            {isOwner && (
              <Button
                variant="outline"
                size="sm"
                className="mt-2"
                onClick={() => setShowCancelConfirm(true)}
              >
                {t('organization.deletionRequest.cancelButton')}
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Danger Zone - Only for owners */}
      {isOwner && !organization.deletion_requested && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-destructive">{t('organization.sections.dangerZone.title')}</CardTitle>
            <CardDescription>
              {t('organization.sections.dangerZone.description')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between rounded-lg border border-destructive/50 p-4">
              <div className="space-y-1">
                <p className="font-medium">{t('organization.deletionRequest.requestAction.title')}</p>
                <p className="text-sm text-muted-foreground">
                  {t('organization.deletionRequest.requestAction.description')}
                </p>
              </div>
              <Button
                variant="destructive"
                onClick={() => setShowDeleteConfirm(true)}
              >
                {t('organization.deletionRequest.requestAction.button')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Not an owner message */}
      {!isOwner && !organization.deletion_requested && (
        <Card>
          <CardHeader>
            <CardTitle>{t('organization.sections.deletion.title')}</CardTitle>
            <CardDescription>
              {t('organization.sections.deletion.description')}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {t('organization.deletionRequest.ownerOnly')}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Request Deletion Confirmation */}
      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title={t('organization.dialogs.requestDeletion.title')}
        description={t('organization.dialogs.requestDeletion.description', { name: organization.name })}
        confirmLabel={t('organization.dialogs.requestDeletion.confirmLabel')}
        onConfirm={handleRequestDeletion}
        isLoading={isRequesting}
        variant="destructive"
      />

      {/* Cancel Deletion Confirmation */}
      <ConfirmDialog
        open={showCancelConfirm}
        onOpenChange={setShowCancelConfirm}
        title={t('organization.dialogs.cancelDeletion.title')}
        description={t('organization.dialogs.cancelDeletion.description', { name: organization.name })}
        confirmLabel={t('organization.dialogs.cancelDeletion.confirmLabel')}
        onConfirm={handleCancelDeletion}
        isLoading={isCanceling}
      />
    </div>
  )
}
