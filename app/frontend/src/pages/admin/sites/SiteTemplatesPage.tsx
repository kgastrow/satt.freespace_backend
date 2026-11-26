import { useTranslation } from 'react-i18next'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'
import { SiteDetailShell } from '@/features/sites/components/SiteDetailShell'
import { TemplateEditor } from '@/features/sites/components/TemplateEditor'
import { useGetSiteTemplatesQuery } from '@/features/sites/sitesApi'
import { useSitePermissions } from '@/features/sites/permissions'
import { getServerError } from '@/features/sites/errors'
import { ADVISORY_TYPES } from '@/features/sites/templatePreview'
import type { Site } from '@/types/site'

function SiteTemplates({ site }: { site: Site }) {
  const { t } = useTranslation(['sites', 'backend'])
  const { canWrite } = useSitePermissions()
  const { data, isLoading, error } = useGetSiteTemplatesQuery(site.id)

  if (isLoading) return <Skeleton className="h-96 w-full" />
  if (error || !data) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('sites:templates.loadError')}</AlertTitle>
        <AlertDescription>{getServerError(error, t).message}</AlertDescription>
      </Alert>
    )
  }

  const ordered = [...data.items].sort(
    (a, b) => ADVISORY_TYPES.indexOf(a.advisory_type) - ADVISORY_TYPES.indexOf(b.advisory_type)
  )

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t('sites:templates.intro')}</p>
      {!canWrite && (
        <Alert>
          <AlertDescription>{t('sites:readOnlyNotice')}</AlertDescription>
        </Alert>
      )}
      {ordered.map((template) => (
        <TemplateEditor
          key={template.advisory_type}
          site={site}
          template={template}
          canWrite={canWrite}
        />
      ))}
    </div>
  )
}

export function SiteTemplatesPage() {
  return <SiteDetailShell>{(site) => <SiteTemplates site={site} />}</SiteDetailShell>
}
