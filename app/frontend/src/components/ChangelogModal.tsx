import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
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

interface ChangelogModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ChangelogModal({ open, onOpenChange }: ChangelogModalProps) {
  const { t } = useTranslation('common')
  const isEnabled = useFeatureFlag('changelog_enabled')
  const { data } = useGetPublishedChangelogsQuery(undefined, {
    skip: !isEnabled || !open,
  })
  const [markAllViewed] = useMarkAllChangelogsViewedMutation()

  const handleMarkAllRead = async () => {
    await markAllViewed()
  }

  if (!isEnabled) return null

  const entries = data?.items ?? []

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle>{t('changelog.title')}</DialogTitle>
          <DialogDescription>{t('changelog.description')}</DialogDescription>
        </DialogHeader>
        <ScrollArea className="max-h-[60vh] pr-4">
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
        </ScrollArea>
        <DialogFooter>
          {data && data.unread_count > 0 && (
            <Button variant="outline" onClick={handleMarkAllRead}>
              {t('changelog.markAllRead')}
            </Button>
          )}
          <Button onClick={() => onOpenChange(false)}>
            {t('buttons.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
