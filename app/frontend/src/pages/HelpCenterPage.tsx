import { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Search, BookOpen, HelpCircle, Mail, ExternalLink } from 'lucide-react'
import DOMPurify from 'dompurify'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useGetHelpCategoriesQuery,
  useGetArticlesQuery,
  useGetFaqsQuery,
  useSearchHelpQuery,
} from '@/store/api/helpCenterApi'
import type { HelpCategory } from '@/types/helpCenter'

export function HelpCenterPage() {
  const { t } = useTranslation(['common', 'helpCenter'])
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(null)

  const { data: categoriesData, isLoading: categoriesLoading } = useGetHelpCategoriesQuery()
  const { data: articlesData, isLoading: articlesLoading } = useGetArticlesQuery(
    selectedCategoryId ? { category_id: selectedCategoryId } : undefined
  )
  const { data: faqsData, isLoading: faqsLoading } = useGetFaqsQuery(
    selectedCategoryId ? { category_id: selectedCategoryId } : undefined
  )
  const { data: searchData, isLoading: searchLoading } = useSearchHelpQuery(
    { q: searchQuery },
    { skip: searchQuery.length < 2 }
  )

  const isSearching = searchQuery.length >= 2

  const displayedArticles = useMemo(
    () => (isSearching ? searchData?.articles || [] : articlesData?.items || []),
    [isSearching, searchData?.articles, articlesData?.items]
  )

  const displayedFaqs = useMemo(
    () => (isSearching ? searchData?.faqs || [] : faqsData?.items || []),
    [isSearching, searchData?.faqs, faqsData?.items]
  )

  const filteredArticlesByCategory = useMemo(() => {
    if (selectedCategoryId) {
      return displayedArticles.filter((article) => article.category_id === selectedCategoryId)
    }
    return displayedArticles
  }, [displayedArticles, selectedCategoryId])

  const filteredFaqsByCategory = useMemo(() => {
    if (selectedCategoryId) {
      return displayedFaqs.filter((faq) => faq.category_id === selectedCategoryId)
    }
    return displayedFaqs
  }, [displayedFaqs, selectedCategoryId])

  const getCategoryById = (categoryId: string): HelpCategory | undefined => {
    return categoriesData?.items.find((cat) => cat.id === categoryId)
  }

  return (
    <div className="h-full overflow-auto bg-background">
      {/* Header */}
      <div className="border-b bg-card">
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center gap-2 mb-4">
            <HelpCircle className="h-8 w-8 text-primary" />
            <h1 className="text-4xl font-bold tracking-tight">{t('helpCenter:title')}</h1>
          </div>
          <p className="text-lg text-muted-foreground mb-6">{t('helpCenter:subtitle')}</p>

          {/* Search Bar */}
          <div className="relative max-w-2xl">
            <Search className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted-foreground" />
            <Input
              type="text"
              placeholder={t('helpCenter:searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-10 h-12 text-base"
            />
          </div>

          {isSearching && (
            <div className="mt-4 text-sm text-muted-foreground">
              {searchLoading ? (
                <span>{t('helpCenter:searching')}</span>
              ) : (
                <span>
                  {t('helpCenter:searchResults', {
                    count: (searchData?.articles.length || 0) + (searchData?.faqs.length || 0),
                  })}
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8">
        {/* Category Filters */}
        {!isSearching && (
          <div className="mb-8">
            <h2 className="text-lg font-semibold mb-4">{t('helpCenter:categories.title')}</h2>
            <div className="flex flex-wrap gap-2">
              <Button
                variant={selectedCategoryId === null ? 'default' : 'outline'}
                size="sm"
                onClick={() => setSelectedCategoryId(null)}
              >
                {t('helpCenter:categories.all')}
              </Button>
              {categoriesLoading ? (
                <>
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-24" />
                  <Skeleton className="h-8 w-24" />
                </>
              ) : (
                [...(categoriesData?.items ?? [])]
                  .sort((a, b) => a.display_order - b.display_order)
                  .map((category) => (
                    <Button
                      key={category.id}
                      variant={selectedCategoryId === category.id ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setSelectedCategoryId(category.id)}
                    >
                      {category.name}
                    </Button>
                  ))
              )}
            </div>
          </div>
        )}

        <Tabs defaultValue="faqs" className="space-y-6">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="faqs" className="flex items-center gap-2">
              <HelpCircle className="h-4 w-4" />
              {t('helpCenter:tabs.faqs')}
              {displayedFaqs.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {filteredFaqsByCategory.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="articles" className="flex items-center gap-2">
              <BookOpen className="h-4 w-4" />
              {t('helpCenter:tabs.articles')}
              {displayedArticles.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {filteredArticlesByCategory.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          {/* FAQs Tab */}
          <TabsContent value="faqs" className="space-y-6">
            {faqsLoading || searchLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : filteredFaqsByCategory.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <HelpCircle className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    {isSearching
                      ? t('helpCenter:noSearchResults')
                      : t('helpCenter:faqs.noFaqs')}
                  </p>
                </CardContent>
              </Card>
            ) : (
              <Accordion type="single" collapsible className="space-y-2">
                {[...filteredFaqsByCategory]
                  .sort((a, b) => a.display_order - b.display_order)
                  .map((faq) => {
                    const category = getCategoryById(faq.category_id)
                    return (
                      <AccordionItem
                        key={faq.id}
                        value={faq.id}
                        className="border rounded-lg px-4 bg-card"
                      >
                        <AccordionTrigger className="hover:no-underline py-4">
                          <div className="flex flex-col items-start gap-2 text-left">
                            <span className="font-medium">{faq.question}</span>
                            {category && !selectedCategoryId && (
                              <Badge variant="outline" className="text-xs">
                                {category.name}
                              </Badge>
                            )}
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="pb-4 text-muted-foreground">
                          <div
                            className="prose prose-sm max-w-none dark:prose-invert"
                            dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(faq.answer) }}
                          />
                        </AccordionContent>
                      </AccordionItem>
                    )
                  })}
              </Accordion>
            )}
          </TabsContent>

          {/* Articles Tab */}
          <TabsContent value="articles" className="space-y-6">
            {articlesLoading || searchLoading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <Skeleton className="h-64 w-full" />
                <Skeleton className="h-64 w-full" />
                <Skeleton className="h-64 w-full" />
              </div>
            ) : filteredArticlesByCategory.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <BookOpen className="h-12 w-12 text-muted-foreground mb-4" />
                  <p className="text-muted-foreground">
                    {isSearching
                      ? t('helpCenter:noSearchResults')
                      : t('helpCenter:articles.noArticles')}
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredArticlesByCategory.map((article) => {
                  const category = getCategoryById(article.category_id)
                  return (
                    <Link key={article.id} to={`/help-center/${article.slug}`}>
                      <Card className="h-full transition-shadow hover:shadow-lg">
                        {article.featured_image_url && (
                          <div className="aspect-video w-full overflow-hidden rounded-t-lg">
                            <img
                              src={article.featured_image_url}
                              alt={article.title}
                              className="h-full w-full object-cover"
                            />
                          </div>
                        )}
                        <CardHeader>
                          <div className="flex items-start justify-between gap-2">
                            <CardTitle className="line-clamp-2 text-lg">
                              {article.title}
                            </CardTitle>
                            <ExternalLink className="h-4 w-4 flex-shrink-0 text-muted-foreground" />
                          </div>
                          {category && (
                            <Badge variant="outline" className="w-fit">
                              {category.name}
                            </Badge>
                          )}
                        </CardHeader>
                      </Card>
                    </Link>
                  )
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Contact Support Section */}
        <Card className="mt-12 bg-muted/50">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Mail className="h-5 w-5" />
              <CardTitle>{t('helpCenter:contactSupport.title')}</CardTitle>
            </div>
            <CardDescription>{t('helpCenter:contactSupport.description')}</CardDescription>
          </CardHeader>
          <CardContent>
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
