import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import DOMPurify from 'dompurify'
import { toast } from '@/lib/toast'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  useGetAboutContentQuery,
  useUpdateAboutContentMutation,
  type AboutContentType,
} from '@/features/about/aboutApi'
import { Info, Eye } from 'lucide-react'

const formSchema = z.object({
  content: z.string().min(1, 'Content is required'),
  content_type: z.enum(['plain', 'html']),
})

type FormData = z.infer<typeof formSchema>

export function AboutSettingsPage() {
  const { t } = useTranslation(['admin', 'common'])
  const [activeTab, setActiveTab] = useState<'edit' | 'preview'>('edit')

  const { data: aboutContent, isLoading } = useGetAboutContentQuery()
  const [updateAboutContent, { isLoading: isUpdating }] = useUpdateAboutContentMutation()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      content: '',
      content_type: 'html',
    },
  })

  // Update form when data loads
  useEffect(() => {
    if (aboutContent) {
      form.reset({
        content: aboutContent.content || '',
        content_type: aboutContent.content_type || 'html',
      })
    }
  }, [aboutContent, form])

  const watchedContent = form.watch('content')
  const watchedContentType = form.watch('content_type')
  const sanitizedPreviewHtml = useMemo(() => {
    if (!watchedContent || watchedContentType !== 'html') return ''
    return DOMPurify.sanitize(watchedContent)
  }, [watchedContent, watchedContentType])

  const handleSubmit = async (data: FormData) => {
    try {
      await updateAboutContent({
        content: data.content,
        content_type: data.content_type as AboutContentType,
      }).unwrap()
      toast.success(t('admin:about.toast.updateSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:about.toast.updateError'))
    }
  }

  if (isLoading) {
    return (
      <div className="container max-w-4xl py-8">
        <Skeleton className="h-10 w-64 mb-6" />
        <Skeleton className="h-[500px] w-full" />
      </div>
    )
  }

  return (
    <div className="container max-w-4xl py-8">
      <PageHeader
        title={t('admin:about.title')}
        description={t('admin:about.description')}
      />

      <Alert className="mb-6">
        <Info className="h-4 w-4" />
        <AlertTitle>{t('admin:about.info.title')}</AlertTitle>
        <AlertDescription>{t('admin:about.info.description')}</AlertDescription>
      </Alert>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'edit' | 'preview')}>
        <TabsList className="mb-4">
          <TabsTrigger value="edit">{t('admin:about.tabs.edit')}</TabsTrigger>
          <TabsTrigger value="preview">
            <Eye className="mr-2 h-4 w-4" />
            {t('admin:about.tabs.preview')}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="edit">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>{t('admin:about.contentSection.title')}</CardTitle>
                  <CardDescription>{t('admin:about.contentSection.description')}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <FormField
                    control={form.control}
                    name="content_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('admin:about.fields.contentType.label')}</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder={t('admin:about.fields.contentType.placeholder')} />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="html">
                              {t('admin:about.fields.contentType.options.html')}
                            </SelectItem>
                            <SelectItem value="plain">
                              {t('admin:about.fields.contentType.options.plain')}
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          {t('admin:about.fields.contentType.description')}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="content"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('admin:about.fields.content.label')}</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder={
                              watchedContentType === 'html'
                                ? t('admin:about.fields.content.placeholderHtml')
                                : t('admin:about.fields.content.placeholderPlain')
                            }
                            className="min-h-[300px] font-mono"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          {watchedContentType === 'html'
                            ? t('admin:about.fields.content.descriptionHtml')
                            : t('admin:about.fields.content.descriptionPlain')}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <div className="flex justify-end">
                <Button type="submit" disabled={isUpdating}>
                  {isUpdating ? t('common:saving') : t('admin:about.actions.save')}
                </Button>
              </div>
            </form>
          </Form>
        </TabsContent>

        <TabsContent value="preview">
          <Card>
            <CardHeader>
              <CardTitle>{t('admin:about.preview.title')}</CardTitle>
              <CardDescription>{t('admin:about.preview.description')}</CardDescription>
            </CardHeader>
            <CardContent>
              {watchedContentType === 'html' ? (
                <div
                  className="prose prose-sm dark:prose-invert max-w-none"
                  dangerouslySetInnerHTML={{ __html: sanitizedPreviewHtml }}
                />
              ) : (
                <div className="whitespace-pre-wrap">{watchedContent}</div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}

export default AboutSettingsPage
