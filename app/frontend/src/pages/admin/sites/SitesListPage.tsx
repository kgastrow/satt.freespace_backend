import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Plus } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AdvancedDataTable, type AdvancedColumn } from '@/components/AdvancedDataTable'
import { useAppSelector } from '@/store/hooks'
import { selectUser } from '@/features/auth/authSelectors'
import { useGetOrganizationsQuery } from '@/features/organizations/organizationsApi'
import { useGetSitesQuery } from '@/features/sites/sitesApi'
import { useGetSitesSummaryQuery } from '@/features/sites/liveApi'
import { usePollingInterval } from '@/features/sites/usePolling'
import { useSitePermissions } from '@/features/sites/permissions'
import { siteListExtraColumns } from '@/features/sites/siteListColumns'
import { CreateSiteDialog } from '@/features/sites/components/CreateSiteDialog'
import { getServerError } from '@/features/sites/errors'
import type { Site } from '@/types/site'

const PAGE_SIZE = 25
const TABLE_ID = 'freespace-sites'

export function SitesListPage() {
  const { t } = useTranslation(['sites', 'backend'])
  const navigate = useNavigate()
  const user = useAppSelector(selectUser)
  const { canWrite, isSuperAdmin } = useSitePermissions()
  const [page, setPage] = useState(1)
  const [createOpen, setCreateOpen] = useState(false)

  const { data, isLoading, error } = useGetSitesQuery({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  })
  // Live figures (BF-76), refreshed while the tab is visible. A failure here
  // only leaves the live columns empty; the list itself still works.
  const { data: summary } = useGetSitesSummaryQuery(undefined, {
    pollingInterval: usePollingInterval(),
  })
  const summaryById = useMemo(
    () => new Map((summary?.items ?? []).map((item) => [item.id, item])),
    [summary]
  )
  // The customer column comes from the list itself (organization_name). The
  // organization list is only needed for the picker of the create dialog.
  const { data: orgData } = useGetOrganizationsQuery({ limit: 100 }, { skip: !isSuperAdmin || !createOpen })
  const organizations = useMemo<Array<{ id: string; name: string }>>(
    () => (orgData?.items ?? []).map((org: { id: string; name: string }) => ({ id: org.id, name: org.name })),
    [orgData]
  )

  const columns = useMemo<AdvancedColumn<Site>[]>(() => {
    const base: AdvancedColumn<Site>[] = [
      {
        key: 'name',
        header: t('sites:fields.name'),
        alwaysVisible: true,
        cell: (site) => (
          <Link
            to={`/admin/sites/${site.id}`}
            className="font-medium hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {site.name}
          </Link>
        ),
      },
      {
        key: 'slug',
        header: t('sites:fields.slug'),
        cell: (site) => <code className="rounded bg-muted px-2 py-1 text-sm">{site.slug}</code>,
      },
    ]
    if (isSuperAdmin) {
      base.push({
        key: 'customer',
        header: t('sites:fields.customer'),
        cell: (site) => site.organization_name ?? site.organization_id,
      })
    }
    base.push(
      {
        key: 'mode',
        header: t('sites:fields.mode'),
        cell: (site) => (
          <Badge variant={site.managed ? 'default' : 'secondary'}>
            {site.managed ? t('sites:badges.managed') : t('sites:badges.shadow')}
          </Badge>
        ),
      },
      {
        key: 'listed',
        header: t('sites:fields.listed'),
        cell: (site) => (
          <Badge variant={site.listed ? 'outline' : 'secondary'}>
            {site.listed ? t('sites:badges.listed') : t('sites:badges.unlisted')}
          </Badge>
        ),
      }
    )
    return [...base, ...siteListExtraColumns(t, summaryById)]
  }, [t, isSuperAdmin, summaryById])

  return (
    <div className="space-y-6">
      <PageHeader title={t('sites:list.title')} description={t('sites:list.description')}>
        {canWrite && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t('sites:list.create')}
          </Button>
        )}
      </PageHeader>

      {error ? (
        <Alert variant="destructive">
          <AlertTitle>{t('sites:list.loadError')}</AlertTitle>
          <AlertDescription>{getServerError(error, t).message}</AlertDescription>
        </Alert>
      ) : (
        <AdvancedDataTable
          columns={columns}
          data={data?.items ?? []}
          isLoading={isLoading}
          emptyMessage={t('sites:list.empty')}
          pagination={{
            page,
            pageSize: PAGE_SIZE,
            total: data?.total ?? 0,
            onPageChange: setPage,
          }}
          onRowClick={(site) => navigate(`/admin/sites/${site.id}`)}
          getRowId={(site) => site.id}
          tableId={TABLE_ID}
        />
      )}

      {canWrite && (
        <CreateSiteDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          organizations={isSuperAdmin ? organizations : undefined}
          defaultOrganizationId={user?.organization_id}
          onCreated={(id) => navigate(`/admin/sites/${id}`)}
        />
      )}
    </div>
  )
}
