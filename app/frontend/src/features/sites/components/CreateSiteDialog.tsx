import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { getErrorMessage } from '@/types/api'
import { useCreateSiteMutation } from '../sitesApi'
import { createSiteCreateSchema, type SiteCreateFormValues } from '../siteSettingsSchema'

interface CreateSiteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Super admins pick the customer; others always create in their own. */
  organizations?: Array<{ id: string; name: string }>
  defaultOrganizationId?: string
  onCreated: (siteId: string) => void
}

export function CreateSiteDialog({
  open,
  onOpenChange,
  organizations,
  defaultOrganizationId = '',
  onCreated,
}: CreateSiteDialogProps) {
  const { t } = useTranslation(['sites', 'backend'])
  const [createSite, { isLoading }] = useCreateSiteMutation()

  const form = useForm<SiteCreateFormValues>({
    resolver: zodResolver(createSiteCreateSchema(t)),
    defaultValues: {
      slug: '',
      name: '',
      time_zone: '',
      fcm_topic: '',
      organization_id: defaultOrganizationId,
    },
  })

  useEffect(() => {
    if (open) {
      form.reset({
        slug: '',
        name: '',
        time_zone: '',
        fcm_topic: '',
        organization_id: defaultOrganizationId,
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const onSubmit = async (values: SiteCreateFormValues) => {
    try {
      const result = await createSite({
        slug: values.slug,
        name: values.name.trim(),
        ...(values.time_zone ? { time_zone: values.time_zone } : {}),
        ...(values.fcm_topic ? { fcm_topic: values.fcm_topic } : {}),
        ...(organizations && values.organization_id
          ? { organization_id: values.organization_id }
          : {}),
      }).unwrap()
      toast.success(t('sites:create.success'))
      onOpenChange(false)
      onCreated(result.site.id)
    } catch (error) {
      toast.error(getErrorMessage(error, t))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('sites:create.title')}</DialogTitle>
          <DialogDescription>{t('sites:create.description')}</DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {organizations && (
              <FormField
                control={form.control}
                name="organization_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('sites:fields.customer')}</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder={t('sites:fields.customerPlaceholder')} />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {organizations.map((org) => (
                          <SelectItem key={org.id} value={org.id}>
                            {org.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:fields.name')}</FormLabel>
                  <FormControl>
                    <Input {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="slug"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:fields.slug')}</FormLabel>
                  <FormControl>
                    <Input {...field} className="font-mono" />
                  </FormControl>
                  <FormDescription>{t('sites:fields.slugHelp')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="time_zone"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:fields.timeZone')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder="Africa/Johannesburg" />
                  </FormControl>
                  <FormDescription>{t('sites:fields.timeZoneHelp')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="fcm_topic"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:fields.topic')}</FormLabel>
                  <FormControl>
                    <Input {...field} className="font-mono" />
                  </FormControl>
                  <FormDescription>{t('sites:fields.topicHelp')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('sites:actions.cancel')}
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading ? t('sites:create.creating') : t('sites:create.submit')}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
