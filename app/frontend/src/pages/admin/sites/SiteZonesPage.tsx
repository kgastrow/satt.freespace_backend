import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CheckCheck, Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { AdvancedDataTable, type AdvancedColumn } from '@/components/AdvancedDataTable'
import { getErrorMessage } from '@/types/api'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { ZoneDialog } from '@/features/sites/components/ZoneDialog'
import {
  useDeleteZoneMutation,
  useGetZonesQuery,
  useUpdateZoneMutation,
} from '@/features/sites/sitesApi'
import { useSitePermissions } from '@/features/sites/permissions'
import { getServerError } from '@/features/sites/errors'
import type { Site, Zone } from '@/types/site'

function YesNo({ value }: { value: boolean }) {
  const { t } = useTranslation('sites')
  return (
    <Badge variant={value ? 'default' : 'secondary'}>
      {value ? t('common.yes') : t('common.no')}
    </Badge>
  )
}

function SiteZones({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { canWrite } = useSitePermissions()
  const { data, isLoading, error } = useGetZonesQuery({ siteId: site.id })
  const [updateZone, { isLoading: isReviewing }] = useUpdateZoneMutation()
  const [deleteZone, { isLoading: isDeleting }] = useDeleteZoneMutation()
  const [dialogZone, setDialogZone] = useState<Zone | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [toDelete, setToDelete] = useState<Zone | null>(null)

  const zones = useMemo(
    () =>
      [...(data?.items ?? [])].sort(
        (a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name)
      ),
    [data]
  )
  const discoveredCount = zones.filter((z) => z.discovered).length

  const openCreate = () => {
    setDialogZone(null)
    setDialogOpen(true)
  }
  const openEdit = (zone: Zone) => {
    setDialogZone(zone)
    setDialogOpen(true)
  }

  const markReviewed = async (zone: Zone) => {
    try {
      await updateZone({
        siteId: site.id,
        zoneId: zone.id,
        data: { reviewed: true },
      }).unwrap()
      toast.success(t('backend:zone.reviewed'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    }
  }

  const confirmDelete = async () => {
    if (!toDelete) return
    try {
      await deleteZone({ siteId: site.id, zoneId: toDelete.id }).unwrap()
      toast.success(t('sites:zones.deleted'))
    } catch (err) {
      toast.error(getErrorMessage(err, t))
    } finally {
      setToDelete(null)
    }
  }

  const columns = useMemo<AdvancedColumn<Zone>[]>(
    () => [
      {
        key: 'display_order',
        header: t('sites:zones.fields.display_order'),
        cell: (zone) => zone.display_order,
      },
      {
        key: 'name',
        header: t('sites:zones.fields.name'),
        alwaysVisible: true,
        cell: (zone) => (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{zone.name}</span>
              {zone.discovered && (
                <Badge variant="outline" className="border-amber-500 text-amber-600">
                  {t('sites:zones.discovered')}
                </Badge>
              )}
            </div>
            <code className="text-xs text-muted-foreground">{zone.slug}</code>
          </div>
        ),
      },
      { key: 'enabled', header: t('sites:zones.fields.enabled'), cell: (z) => <YesNo value={z.enabled} /> },
      {
        key: 'recommendable',
        header: t('sites:zones.fields.recommendable'),
        cell: (z) => <YesNo value={z.recommendable} />,
      },
      { key: 'preferred', header: t('sites:zones.fields.preferred'), cell: (z) => <YesNo value={z.preferred} /> },
      { key: 'priority', header: t('sites:zones.fields.priority'), cell: (z) => z.priority },
      {
        key: 'thresholds',
        header: t('sites:zones.thresholds'),
        cell: (z) =>
          t('sites:zones.thresholdsValue', {
            limited: z.limited_pct,
            full: z.full_pct,
            minFree: z.full_min_free,
            unknown: z.unknown_limit_pct,
          }),
      },
      {
        key: 'advisory_pct',
        header: t('sites:zones.fields.advisory_pct'),
        cell: (z) =>
          z.advisory_pct === null ? (
            <span className="text-muted-foreground">{t('sites:zones.noAdvisory')}</span>
          ) : (
            `${z.advisory_pct}%`
          ),
      },
      {
        key: 'note',
        header: t('sites:zones.fields.note'),
        hiddenOnMobile: true,
        cell: (z) => <span className="line-clamp-2 max-w-xs text-sm">{z.note}</span>,
      },
      ...(canWrite
        ? [
            {
              key: 'actions',
              header: t('sites:actions.actions'),
              alwaysVisible: true,
              cell: (zone: Zone) => (
                <div className="flex justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                  {zone.discovered && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={isReviewing}
                      onClick={() => markReviewed(zone)}
                    >
                      <CheckCheck className="mr-1 h-4 w-4" />
                      {t('sites:zones.review')}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t('sites:zones.edit', { name: zone.name })}
                    onClick={() => openEdit(zone)}
                  >
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t('sites:zones.delete', { name: zone.name })}
                    onClick={() => setToDelete(zone)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ),
            } satisfies AdvancedColumn<Zone>,
          ]
        : []),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [t, canWrite, isReviewing]
  )

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div className="space-y-1.5">
          <CardTitle>{t('sites:zones.title')}</CardTitle>
          <CardDescription>{t('sites:zones.description')}</CardDescription>
        </div>
        {canWrite && (
          <Button onClick={openCreate}>
            <Plus className="mr-2 h-4 w-4" />
            {t('sites:zones.create')}
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {discoveredCount > 0 && (
          <Alert>
            <AlertTitle>{t('sites:zones.discoveredNotice.title', { count: discoveredCount })}</AlertTitle>
            <AlertDescription>{t('sites:zones.discoveredNotice.description')}</AlertDescription>
          </Alert>
        )}
        {error ? (
          <Alert variant="destructive">
            <AlertTitle>{t('sites:zones.loadError')}</AlertTitle>
            <AlertDescription>{getServerError(error, t).message}</AlertDescription>
          </Alert>
        ) : (
          <AdvancedDataTable
            columns={columns}
            data={zones}
            isLoading={isLoading}
            emptyMessage={t('sites:zones.empty')}
            getRowId={(zone) => zone.id}
            tableId="freespace-zones"
          />
        )}
      </CardContent>

      {canWrite && (
        <>
          <ZoneDialog
            siteId={site.id}
            zone={dialogZone}
            open={dialogOpen}
            onOpenChange={setDialogOpen}
          />
          <ConfirmDialog
            open={toDelete !== null}
            onOpenChange={(open) => !open && setToDelete(null)}
            title={t('sites:zones.deleteConfirm.title')}
            description={t('sites:zones.deleteConfirm.description', { name: toDelete?.name ?? '' })}
            confirmLabel={t('sites:zones.deleteConfirm.confirm')}
            onConfirm={confirmDelete}
            isLoading={isDeleting}
            variant="destructive"
          />
        </>
      )}
    </Card>
  )
}

export function SiteZonesPage() {
  return <SiteDetailShell>{(site) => <SiteZones site={site} />}</SiteDetailShell>
}
