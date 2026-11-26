import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Plus, Ban } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { AdvancedDataTable, type AdvancedColumn } from '@/components/AdvancedDataTable'
import { getErrorMessage } from '@/types/api'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { CreateKeyDialog, type CreateKeyValues } from '@/features/sites/components/CreateKeyDialog'
import { KeyRevealDialog } from '@/features/sites/components/KeyRevealDialog'
import {
  useCreateIngestKeyMutation,
  useGetIngestKeysQuery,
  useRevokeIngestKeyMutation,
} from '@/features/sites/keysApi'
import { useSitePermissions } from '@/features/sites/permissions'
import { getServerError } from '@/features/sites/errors'
import { formatDateTime, isInPast } from '@/features/sites/format'
import type { IngestKey, Site } from '@/types/site'

function SiteIngestKeys({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { canWriteKeys } = useSitePermissions()
  const { data, isLoading, error } = useGetIngestKeysQuery(site.id)
  const [createKey, { isLoading: isCreating }] = useCreateIngestKeyMutation()
  const [revokeKey, { isLoading: isRevoking }] = useRevokeIngestKeyMutation()
  const [createOpen, setCreateOpen] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [toRevoke, setToRevoke] = useState<IngestKey | null>(null)

  const handleCreate = async (values: CreateKeyValues) => {
    setCreateError(null)
    try {
      const result = await createKey({
        siteId: site.id,
        data: { name: values.name, ...(values.expires_at ? { expires_at: values.expires_at } : {}) },
      }).unwrap()
      setCreateOpen(false)
      setSecret(result.key)
    } catch (err) {
      setCreateError(getServerError(err, t).message)
    }
  }

  const handleRevoke = async () => {
    if (!toRevoke) return
    try {
      await revokeKey({ siteId: site.id, keyId: toRevoke.id }).unwrap()
      toast.success(t('sites:keys.ingest.revoked'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    } finally {
      setToRevoke(null)
    }
  }

  const never = <span className="text-muted-foreground">{t('sites:keys.never')}</span>

  const columns = useMemo<AdvancedColumn<IngestKey>[]>(
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
          ) : isInPast(k.expires_at) ? (
            <Badge variant="secondary">{t('sites:keys.status.expired')}</Badge>
          ) : (
            <Badge>{t('sites:keys.status.active')}</Badge>
          ),
      },
      { key: 'created', header: t('sites:keys.fields.created'), cell: (k) => formatDateTime(k.created_time) },
      {
        key: 'expires',
        header: t('sites:keys.fields.expires'),
        cell: (k) => formatDateTime(k.expires_at) ?? never,
      },
      {
        key: 'revoked',
        header: t('sites:keys.fields.revokedAt'),
        cell: (k) => formatDateTime(k.revoked_at) ?? <span className="text-muted-foreground">-</span>,
      },
      {
        key: 'last_used',
        header: t('sites:keys.fields.lastUsed'),
        cell: (k) => formatDateTime(k.last_used_at) ?? <span className="text-muted-foreground">{t('sites:keys.neverUsed')}</span>,
      },
      {
        key: 'last_ip',
        header: t('sites:keys.fields.lastIp'),
        hiddenOnMobile: true,
        cell: (k) => k.last_used_ip ?? <span className="text-muted-foreground">-</span>,
      },
      ...(canWriteKeys
        ? [
            {
              key: 'actions',
              header: t('sites:actions.actions'),
              alwaysVisible: true,
              cell: (k: IngestKey) =>
                k.revoked_at ? null : (
                  <div className="flex justify-end">
                    <Button variant="outline" size="sm" onClick={() => setToRevoke(k)}>
                      <Ban className="mr-1 h-4 w-4" />
                      {t('sites:keys.revoke')}
                    </Button>
                  </div>
                ),
            } satisfies AdvancedColumn<IngestKey>,
          ]
        : []),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, canWriteKeys]
  )

  return (
    <div className="space-y-6">
      <Alert>
        <AlertTitle>{t('sites:keys.ingest.rotationTitle')}</AlertTitle>
        <AlertDescription>{t('sites:keys.ingest.rotation')}</AlertDescription>
      </Alert>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between space-y-0">
          <div className="space-y-1.5">
            <CardTitle>{t('sites:keys.ingest.title')}</CardTitle>
            <CardDescription>{t('sites:keys.ingest.description')}</CardDescription>
          </div>
          {canWriteKeys && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              {t('sites:keys.create')}
            </Button>
          )}
        </CardHeader>
        <CardContent>
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
              tableId="freespace-ingest-keys"
            />
          )}
        </CardContent>
      </Card>

      {canWriteKeys && (
        <>
          <CreateKeyDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            title={t('sites:keys.ingest.createTitle')}
            description={t('sites:keys.ingest.createDescription')}
            withExpiry
            isLoading={isCreating}
            error={createError}
            onSubmit={handleCreate}
          />
          <ConfirmDialog
            open={toRevoke !== null}
            onOpenChange={(open) => !open && setToRevoke(null)}
            title={t('sites:keys.ingest.revokeConfirm.title')}
            description={t('sites:keys.ingest.revokeConfirm.description', { name: toRevoke?.name ?? '' })}
            confirmLabel={t('sites:keys.ingest.revokeConfirm.confirm')}
            onConfirm={handleRevoke}
            isLoading={isRevoking}
            variant="destructive"
          />
        </>
      )}
      <KeyRevealDialog
        secret={secret}
        onClose={() => setSecret(null)}
        title={t('sites:keys.ingest.revealTitle')}
        description={t('sites:keys.ingest.revealDescription')}
      />
    </div>
  )
}

export function SiteIngestKeysPage() {
  return <SiteDetailShell>{(site) => <SiteIngestKeys site={site} />}</SiteDetailShell>
}
