import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  useGetFeatureFlagOverridesQuery,
  useCreateFeatureFlagOverrideMutation,
  useDeleteFeatureFlagOverrideMutation,
  type FeatureFlagOverride,
} from '@/features/featureFlags/featureFlagsApi'
import { useGetOrganizationsQuery } from '@/features/organizations/organizationsApi'

interface FeatureFlagOverrideDialogProps {
  flagId: string
  flagName: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FeatureFlagOverrideDialog({
  flagId,
  flagName,
  open,
  onOpenChange,
}: FeatureFlagOverrideDialogProps) {
  const { t } = useTranslation(['admin', 'common'])
  const [selectedOrgId, setSelectedOrgId] = useState<string>('')
  const [enabled, setEnabled] = useState(true)
  const [deletingOverride, setDeletingOverride] = useState<FeatureFlagOverride | null>(null)

  const { data: overridesData, isLoading: isLoadingOverrides } =
    useGetFeatureFlagOverridesQuery(flagId, { skip: !open })

  const { data: orgsData } = useGetOrganizationsQuery(
    { limit: 100, offset: 0 },
    { skip: !open }
  )

  const [createOverride, { isLoading: isCreating }] =
    useCreateFeatureFlagOverrideMutation()

  const [deleteOverride, { isLoading: isDeleting }] =
    useDeleteFeatureFlagOverrideMutation()

  const handleCreateOverride = async () => {
    if (!selectedOrgId) {
      toast.error(t('admin:featureFlags.validation.organizationRequired'))
      return
    }

    try {
      await createOverride({
        flagId,
        data: {
          organization_id: selectedOrgId,
          enabled,
        },
      }).unwrap()
      toast.success(t('admin:featureFlags.toast.overrideCreateSuccess'))
      setSelectedOrgId('')
      setEnabled(true)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:featureFlags.toast.overrideCreateError'))
    }
  }

  const handleDeleteOverride = async () => {
    if (!deletingOverride) return

    try {
      await deleteOverride({
        flagId,
        orgId: deletingOverride.organization_id,
      }).unwrap()
      toast.success(t('admin:featureFlags.toast.overrideDeleteSuccess'))
      setDeletingOverride(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:featureFlags.toast.overrideDeleteError'))
    }
  }

  const availableOrgs = orgsData?.items.filter(
    (org) =>
      !overridesData?.items.some(
        (override) => override.organization_id === org.id
      )
  )

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin:featureFlags.overrideDialog.title', { flagName })}</DialogTitle>
            <DialogDescription>
              {t('admin:featureFlags.overrideDialog.description')}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6">
            {/* Create New Override */}
            <div className="space-y-4 p-4 border rounded-lg">
              <h4 className="font-medium">{t('admin:featureFlags.overrideDialog.addButton')}</h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>{t('admin:featureFlags.overrideDialog.organization')}</Label>
                  <Select value={selectedOrgId} onValueChange={setSelectedOrgId}>
                    <SelectTrigger>
                      <SelectValue
                        placeholder={t('admin:featureFlags.overrideDialog.organizationPlaceholder')}
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {availableOrgs?.map((org) => (
                        <SelectItem key={org.id} value={org.id}>
                          {org.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t('admin:featureFlags.overrideDialog.enabled')}</Label>
                  <div className="flex items-center space-x-2">
                    <Switch checked={enabled} onCheckedChange={setEnabled} />
                    <span className="text-sm text-muted-foreground">
                      {enabled
                        ? t('admin:featureFlags.overrideDialog.table.enabled')
                        : t('admin:featureFlags.overrideDialog.table.disabled')}
                    </span>
                  </div>
                </div>
              </div>
              <Button
                onClick={handleCreateOverride}
                disabled={!selectedOrgId || isCreating}
              >
                {isCreating
                  ? t('admin:featureFlags.overrideDialog.adding')
                  : t('admin:featureFlags.overrideDialog.addButton')}
              </Button>
            </div>

            {/* Existing Overrides */}
            <div className="space-y-4">
              <h4 className="font-medium">
                {t('admin:featureFlags.overrideDialog.table.organization')}
              </h4>
              {isLoadingOverrides ? (
                <div className="text-sm text-muted-foreground">
                  {t('common:common.loading')}
                </div>
              ) : overridesData?.items && overridesData.items.length > 0 ? (
                <div className="space-y-2">
                  {overridesData.items.map((override) => {
                    const org = orgsData?.items.find(
                      (o) => o.id === override.organization_id
                    )
                    return (
                      <div
                        key={override.id}
                        className="flex items-center justify-between p-3 border rounded-lg"
                      >
                        <div className="flex items-center gap-3">
                          <span className="font-medium">{org?.name || override.organization_id}</span>
                          <Badge variant={override.enabled ? 'default' : 'secondary'}>
                            {override.enabled
                              ? t('admin:featureFlags.overrideDialog.table.enabled')
                              : t('admin:featureFlags.overrideDialog.table.disabled')}
                          </Badge>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeletingOverride(override)}
                        >
                          {t('admin:featureFlags.overrideDialog.deleteOverride')}
                        </Button>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">
                  {t('admin:featureFlags.overrideDialog.noOverrides')}
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('common:buttons.close')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={!!deletingOverride}
        onOpenChange={() => setDeletingOverride(null)}
        title={t('common:buttons.delete')}
        description={t('admin:featureFlags.overrideDialog.deleteOverride')}
        confirmLabel={t('common:buttons.confirm')}
        onConfirm={handleDeleteOverride}
        isLoading={isDeleting}
        variant="destructive"
      />
    </>
  )
}
