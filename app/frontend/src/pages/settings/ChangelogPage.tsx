import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useFeatureFlag } from '@/hooks/useFeatureFlag'
import {
  useGetPublishedChangelogsQuery,
  useMarkAllChangelogsViewedMutation,
} from '@/features/changelog/changelogApi'
import type { ChangelogCategory } from '@/types/changelog'

const CATEGORY_COLORS: Record<ChangelogCategory, string> = {
  feature: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  improvement:
    'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  bugfix: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  breaking:
    'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  other: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
}

export function ChangelogPage() {
  const { t } = useTranslation('common')
  const isEnabled = useFeatureFlag('changelog_enabled')
  const { data, isLoading } = useGetPublishedChangelogsQuery(undefined, {
    skip: !isEnabled,
  })
  const [markAllViewed] = useMarkAllChangelogsViewedMutation()

  const handleMarkAllRead = async () => {
    await markAllViewed()
  }

  if (!isEnabled) {
    return (
      <div className="container max-w-4xl py-8">
        <p className="text-muted-foreground">{t('changelog.empty')}</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="container max-w-4xl py-8">
        <Skeleton className="h-8 w-48 mb-2" />
        <Skeleton className="h-4 w-64 mb-6" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    )
  }

  const entries = data?.items ?? []

  return (
    <div className="container max-w-4xl py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>{t('changelog.title')}</CardTitle>
              <CardDescription>{t('changelog.description')}</CardDescription>
            </div>
            {data && data.unread_count > 0 && (
              <Button variant="outline" size="sm" onClick={handleMarkAllRead}>
                {t('changelog.markAllRead')}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {entries.length === 0 ? (
            <p className="text-center text-muted-foreground py-8">
              {t('changelog.empty')}
            </p>
          ) : (
            <div className="space-y-6">
              {entries.map((entry) => (
                <div
                  key={entry.id}
                  className="border-b pb-4 last:border-b-0 last:pb-0"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-mono text-sm font-semibold text-muted-foreground">
                      {entry.version}
                    </span>
                    <Badge
                      variant="outline"
                      className={CATEGORY_COLORS[entry.category]}
                    >
                      {t(`changelog.categories.${entry.category}`)}
                    </Badge>
                    {!entry.is_viewed && (
                      <Badge variant="default" className="text-[10px] px-1.5">
                        {t('changelog.new')}
                      </Badge>
                    )}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {new Date(entry.release_date).toLocaleDateString()}
                    </span>
                  </div>
                  <h4 className="font-semibold mb-1">{entry.title}</h4>
                  <div className="text-sm text-muted-foreground whitespace-pre-wrap">
                    {entry.body}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
