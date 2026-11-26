import { useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Calendar, ArrowLeft, Mail, MessageCircle } from 'lucide-react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { useGetArticleBySlugQuery, useGetHelpCategoriesQuery } from '@/store/api/helpCenterApi'

// Validate slug format matches backend pattern: ^[a-z0-9]+(?:-[a-z0-9]+)*$
const isValidSlug = (slug: string): boolean => {
  return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)
}

export function HelpArticlePage() {
  const { t } = useTranslation(['common', 'helpCenter'])
  const { slug } = useParams<{ slug: string }>()

  // Validate slug format before making API call
  const validSlug = slug && isValidSlug(slug)

  const { data: article, isLoading, error } = useGetArticleBySlugQuery(slug || '', {
    skip: !validSlug,
  })
  const { data: categoriesData } = useGetHelpCategoriesQuery()

  const category = categoriesData?.items.find((cat) => cat.id === article?.category_id)

  // Parse markdown content to HTML
  const articleContent = article?.content
  const htmlContent = useMemo(() => {
    if (!articleContent) return ''
    // Convert markdown to HTML, then sanitize
    // SEC-F-006: Use strict DOMPurify config - no iframes or dangerous attributes
    // If embedded content is needed, use a dedicated embed component with allowlist
    const rawHtml = marked.parse(articleContent, { async: false }) as string

    // Add hook to enforce noopener noreferrer on external links
    DOMPurify.addHook('afterSanitizeAttributes', (node) => {
      if (node.tagName === 'A' && node.getAttribute('target') === '_blank') {
        node.setAttribute('rel', 'noopener noreferrer')
      }
    })

    const sanitized = DOMPurify.sanitize(rawHtml, {
      // Only allow safe attributes for links
      ADD_ATTR: ['target'],
      ALLOW_DATA_ATTR: false,
    })

    // Remove hook after use to avoid memory leaks
    DOMPurify.removeHook('afterSanitizeAttributes')

    return sanitized
  }, [articleContent])

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-4 py-8 max-w-4xl">
          <Skeleton className="h-8 w-64 mb-8" />
          <Skeleton className="h-12 w-full mb-4" />
          <Skeleton className="h-6 w-32 mb-8" />
          <Skeleton className="h-64 w-full mb-4" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    )
  }

  // Show not found for invalid slugs or API errors
  if (!validSlug || error || !article) {
    return (
      <div className="min-h-screen bg-background">
        <div className="container mx-auto px-4 py-8 max-w-4xl">
          <Link to="/help-center">
            <Button variant="ghost" size="sm" className="mb-8">
              <ArrowLeft className="h-4 w-4 mr-2" />
              {t('helpCenter:backToHelpCenter')}
            </Button>
          </Link>
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <h2 className="text-2xl font-bold mb-2">{t('helpCenter:article.notFound')}</h2>
              <p className="text-muted-foreground mb-6">
                {t('helpCenter:article.notFoundDescription')}
              </p>
              <Link to="/help-center">
                <Button>{t('helpCenter:article.backButton')}</Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full overflow-auto bg-background">
      {/* Header with Breadcrumbs */}
      <div className="border-b bg-card">
        <div className="container mx-auto px-4 py-4 max-w-4xl">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link to="/help-center">{t('helpCenter:title')}</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              {category && (
                <>
                  <BreadcrumbItem>
                    <BreadcrumbLink asChild>
                      <Link to={`/help-center?category=${category.id}`}>{category.name}</Link>
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                </>
              )}
              <BreadcrumbItem>
                <BreadcrumbPage>{article.title}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </div>
      </div>

      {/* Article Content */}
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Link to="/help-center">
          <Button variant="ghost" size="sm" className="mb-6">
            <ArrowLeft className="h-4 w-4 mr-2" />
            {t('helpCenter:backToHelpCenter')}
          </Button>
        </Link>

        <article>
          {/* Article Header */}
          <div className="mb-8">
            <div className="flex items-center gap-2 mb-4">
              {category && <Badge variant="outline">{category.name}</Badge>}
            </div>

            <h1 className="text-4xl font-bold tracking-tight mb-4">{article.title}</h1>

            {/* Metadata */}
            <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
              {article.published_at && (
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  <time dateTime={article.published_at}>
                    {new Date(article.published_at).toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                    })}
                  </time>
                </div>
              )}
            </div>
          </div>

          {/* Featured Image */}
          {article.featured_image_url && (
            <div className="mb-8 rounded-lg overflow-hidden">
              <img
                src={article.featured_image_url}
                alt={article.title}
                className="w-full h-auto"
              />
            </div>
          )}

          {/* Article Content */}
          <Card>
            <CardContent className="pt-6">
              <div
                className="prose prose-gray max-w-none dark:prose-invert prose-headings:font-semibold prose-h1:text-3xl prose-h2:text-2xl prose-h3:text-xl prose-a:text-primary prose-img:rounded-lg prose-pre:bg-muted"
                dangerouslySetInnerHTML={{ __html: htmlContent }}
              />
            </CardContent>
          </Card>

          {/* Footer - Was this helpful */}
          <div className="mt-12 pt-8 border-t">
            <p className="text-sm text-muted-foreground mb-4">
              {t('helpCenter:article.helpful')}
            </p>
            <Link to="/help-center">
              <Button variant="outline">
                <ArrowLeft className="h-4 w-4 mr-2" />
                {t('helpCenter:backToHelpCenter')}
              </Button>
            </Link>
          </div>
        </article>

        {/* Need More Help Section */}
        <Card className="mt-8 bg-muted/50">
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 mb-2">
              <MessageCircle className="h-5 w-5 text-primary" />
              <h3 className="text-lg font-semibold">{t('helpCenter:contactSupport.title')}</h3>
            </div>
            <p className="text-muted-foreground mb-4">
              {t('helpCenter:contactSupport.description')}
            </p>
            <Button asChild>
              <a href="mailto:support@example.com">
                <Mail className="h-4 w-4 mr-2" />
                {t('helpCenter:contactSupport.button')}
              </a>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
