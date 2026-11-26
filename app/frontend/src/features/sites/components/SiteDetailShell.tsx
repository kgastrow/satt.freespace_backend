import type { ReactNode } from 'react'
import { Link, NavLink, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import { usePermissions } from '@/hooks/usePermissions'
import { useGetSiteQuery } from '../sitesApi'
import { siteTabs, siteTabPath } from '../siteTabs'
import { getServerError } from '../errors'
import { SitePushActions } from './SitePushDialogs'
import type { Site } from '@/types/site'

interface SiteDetailShellProps {
  /** Rendered once the site is loaded. */
  children: (site: Site) => ReactNode
}

/**
 * Frame of every site page: header (name, slug, managed/shadow badge) and the
 * tab bar built from `siteTabs`. Add pages by adding a tab, not by editing
 * this component.
 */
export function SiteDetailShell({ children }: SiteDetailShellProps) {
  const { t } = useTranslation(['sites', 'backend'])
  const { siteId = '' } = useParams<{ siteId: string }>()
  const { hasAnyPermission } = usePermissions()
  const { data: site, isLoading, error } = useGetSiteQuery(siteId, { skip: !siteId })

  const visibleTabs = siteTabs.filter(
    (tab) => !tab.permissions || hasAnyPermission(tab.permissions)
  )

  if (isLoading) {
    return (
      <div className="space-y-6" data-testid="site-shell-loading">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (error || !site) {
    const { message } = getServerError(error, t)
    return (
      <div className="space-y-4">
        <Link
          to="/admin/sites"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('sites:detail.backToList')}
        </Link>
        <Alert variant="destructive">
          <AlertTitle>{t('sites:detail.loadError')}</AlertTitle>
          <AlertDescription>{message}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Link
          to="/admin/sites"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          {t('sites:detail.backToList')}
        </Link>
        <PageHeader title={site.name} description={site.slug}>
          <Badge variant={site.managed ? 'default' : 'secondary'}>
            {site.managed ? t('sites:badges.managed') : t('sites:badges.shadow')}
          </Badge>
          <SitePushActions site={site} />
        </PageHeader>
      </div>

      <nav
        aria-label={t('sites:detail.tabsLabel')}
        className="flex gap-1 overflow-x-auto border-b"
      >
        {visibleTabs.map((tab) => (
          <NavLink
            key={tab.id}
            to={siteTabPath(site.id, tab)}
            end
            className={({ isActive }) =>
              cn(
                'inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )
            }
          >
            <tab.icon className="h-4 w-4" />
            {t(tab.labelKey)}
          </NavLink>
        ))}
      </nav>

      {children(site)}
    </div>
  )
}
