import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, MessageSquare, FolderOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'

export function HelpCenterPage() {
  const { t } = useTranslation('admin')

  const sections = [
    {
      title: t('helpCenter.landing.articles.title'),
      description: t('helpCenter.landing.articles.description'),
      icon: FileText,
      url: '/platform-admin/help-center/articles',
      buttonLabel: t('helpCenter.landing.articles.button'),
    },
    {
      title: t('helpCenter.landing.faqs.title'),
      description: t('helpCenter.landing.faqs.description'),
      icon: MessageSquare,
      url: '/platform-admin/help-center/faqs',
      buttonLabel: t('helpCenter.landing.faqs.button'),
    },
    {
      title: t('helpCenter.landing.categories.title'),
      description: t('helpCenter.landing.categories.description'),
      icon: FolderOpen,
      url: '/platform-admin/help-center/categories',
      buttonLabel: t('helpCenter.landing.categories.button'),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('helpCenter.landing.pageTitle')}
        description={t('helpCenter.landing.pageDescription')}
      />

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {sections.map((section) => {
          const Icon = section.icon
          return (
            <Card key={section.url}>
              <CardHeader>
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                    <Icon className="h-5 w-5 text-primary" />
                  </div>
                  <CardTitle>{section.title}</CardTitle>
                </div>
                <CardDescription>{section.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <Button asChild className="w-full">
                  <Link to={section.url}>{section.buttonLabel}</Link>
                </Button>
              </CardContent>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
