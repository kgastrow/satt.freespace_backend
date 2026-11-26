import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import DOMPurify from 'dompurify'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useGetAboutContentQuery } from '@/features/about/aboutApi'
import { AlertCircle } from 'lucide-react'

export function AboutPage() {
  const { t } = useTranslation(['settings', 'common'])
  const { data: aboutContent, isLoading, error } = useGetAboutContentQuery()

  // Sanitize HTML content to prevent XSS attacks
  const content = aboutContent?.content
  const contentType = aboutContent?.content_type
  const sanitizedHtml = useMemo(() => {
    if (!content || contentType !== 'html') return ''
    return DOMPurify.sanitize(content)
  }, [content, contentType])

  if (isLoading) {
    return (
      <div className="container max-w-4xl py-8">
        <Skeleton className="h-8 w-48 mb-2" />
        <Skeleton className="h-4 w-64 mb-6" />
        <Skeleton className="h-[300px] w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="container max-w-4xl py-8">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('common:error')}</AlertTitle>
          <AlertDescription>{t('settings:pages.about.error')}</AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="container max-w-4xl py-8">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings:pages.about.title')}</CardTitle>
          <CardDescription>{t('settings:pages.about.description')}</CardDescription>
        </CardHeader>
        <CardContent>
          {aboutContent?.content ? (
            aboutContent.content_type === 'html' ? (
              <div
                className="prose prose-sm dark:prose-invert max-w-none"
                dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
              />
            ) : (
              <div className="whitespace-pre-wrap">{aboutContent.content}</div>
            )
          ) : (
            <p className="text-muted-foreground">{t('settings:pages.about.noContent')}</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
