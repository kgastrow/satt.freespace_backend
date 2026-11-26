import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Ban, Plus } from 'lucide-react'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { AdvancedDataTable, type AdvancedColumn } from '@/components/AdvancedDataTable'
import { getErrorMessage } from '@/types/api'
import { CreateKeyDialog, type CreateKeyValues } from '@/features/sites/components/CreateKeyDialog'
import { KeyRevealDialog } from '@/features/sites/components/KeyRevealDialog'
import {
  useCreateAppKeyMutation,
  useGetAppKeysQuery,
  useRevokeAppKeyMutation,
} from '@/features/sites/keysApi'
import { getServerError } from '@/features/sites/errors'
import { formatDateTime } from '@/features/sites/format'
import type { AppKey } from '@/types/site'

/**
 * Deployment-wide app keys (super admin only: lives in the platform admin hub,
 * whose layout guards it, and the API refuses everyone else).
 */
export function AppKeysPage() {
  const { t } = useTranslation(['sites', 'backend'])
  const { data, isLoading, error } = useGetAppKeysQuery()
  const [createKey, { isLoading: isCreating }] = useCreateAppKeyMutation()
  const [revokeKey, { isLoading: isRevoking }] = useRevokeAppKeyMutation()
  const [createOpen, setCreateOpen] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [toRevoke, setToRevoke] = useState<AppKey | null>(null)

  const handleCreate = async (values: CreateKeyValues) => {
    setCreateError(null)
    try {
      const result = await createKey({ name: values.name }).unwrap()
      setCreateOpen(false)
      setSecret(result.key)
    } catch (err) {
      setCreateError(getServerError(err, t).message)
    }
  }

  const handleRevoke = async () => {
    if (!toRevoke) return
    try {
      await revokeKey(toRevoke.id).unwrap()
      toast.success(t('sites:keys.app.revoked'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    } finally {
      setToRevoke(null)
    }
  }

  const columns = useMemo<AdvancedColumn<AppKey>[]>(
    () => [
      {
        key: 'name',
        header: t('sites:keys.fields.name'),
        alwaysVisible: true,
        cell: (k) => <span className="font-medium">{k.name}</span>,
      },
      {
        key: 'hint',
        header: t('sites:keys.fields.hint'),
        cell: (k) => <code className="rounded bg-muted px-2 py-1 text-sm">{k.key_hint}</code>,
      },
      {
        key: 'status',
        header: t('sites:keys.fields.status'),
        cell: (k) =>
          k.revoked_at ? (
            <Badge variant="destructive">{t('sites:keys.status.revoked')}</Badge>
          ) : (
            <Badge>{t('sites:keys.status.active')}</Badge>
          ),
      },
      { key: 'created', header: t('sites:keys.fields.created'), cell: (k) => formatDateTime(k.created_time) },
      {
        key: 'revoked',
        header: t('sites:keys.fields.revokedAt'),
        cell: (k) => formatDateTime(k.revoked_at) ?? <span className="text-muted-foreground">-</span>,
      },
      {
        key: 'actions',
        header: t('sites:actions.actions'),
        alwaysVisible: true,
        cell: (k) =>
          k.revoked_at ? null : (
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={() => setToRevoke(k)}>
                <Ban className="mr-1 h-4 w-4" />
                {t('sites:keys.revoke')}
              </Button>
            </div>
          ),
      },
    ],
    [t]
  )

  return (
    <div className="space-y-6">
      <PageHeader title={t('sites:keys.app.title')} description={t('sites:keys.app.description')}>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t('sites:keys.create')}
        </Button>
      </PageHeader>

      <Alert>
        <AlertTitle>{t('sites:keys.app.rotationTitle')}</AlertTitle>
        <AlertDescription>{t('sites:keys.app.rotation')}</AlertDescription>
      </Alert>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t('sites:keys.loadError')}</AlertTitle>
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      ) : (
        <AdvancedDataTable
          columns={columns}
          data={data?.items ?? []}
          isLoading={isLoading}
          emptyMessage={t('sites:keys.empty')}
          getRowId={(k) => k.id}
          tableId="freespace-app-keys"
        />
      )}

      <CreateKeyDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title={t('sites:keys.app.createTitle')}
        description={t('sites:keys.app.createDescription')}
        isLoading={isCreating}
        error={createError}
        onSubmit={handleCreate}
      />
      <ConfirmDialog
        open={toRevoke !== null}
        onOpenChange={(open) => !open && setToRevoke(null)}
        title={t('sites:keys.app.revokeConfirm.title')}
        description={t('sites:keys.app.revokeConfirm.description', { name: toRevoke?.name ?? '' })}
        confirmLabel={t('sites:keys.app.revokeConfirm.confirm')}
        onConfirm={handleRevoke}
        isLoading={isRevoking}
        variant="destructive"
      />
      <KeyRevealDialog
        secret={secret}
        onClose={() => setSecret(null)}
        title={t('sites:keys.app.revealTitle')}
        description={t('sites:keys.app.revealDescription')}
      />
    </div>
  )
}
