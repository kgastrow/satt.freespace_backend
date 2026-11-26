import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
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
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import type { FeatureFlag } from '@/features/featureFlags/featureFlagsApi'

const createFeatureFlagSchema = (t: (key: string) => string) =>
  z.object({
    key: z
      .string()
      .min(1, t('featureFlags.validation.keyRequired'))
      .max(100)
      .regex(/^[a-z0-9_-]+$/, t('featureFlags.validation.keyFormat')),
    name: z.string().min(1, t('featureFlags.validation.nameRequired')).max(200),
    description: z.string().max(1000).optional(),
    default_enabled: z.boolean(),
  })

type FeatureFlagFormData = z.infer<ReturnType<typeof createFeatureFlagSchema>>

interface FeatureFlagFormProps {
  initialData?: FeatureFlag
  onSubmit: (data: FeatureFlagFormData) => Promise<void>
  onCancel: () => void
  isSubmitting?: boolean
}

export function FeatureFlagForm({
  initialData,
  onSubmit,
  onCancel,
  isSubmitting = false,
}: FeatureFlagFormProps) {
  const { t } = useTranslation('admin')

  const featureFlagSchema = createFeatureFlagSchema(t)

  const form = useForm<FeatureFlagFormData>({
    resolver: zodResolver(featureFlagSchema),
    defaultValues: {
      key: initialData?.key || '',
      name: initialData?.name || '',
      description: initialData?.description || '',
      default_enabled: initialData?.default_enabled ?? false,
    },
  })

  const handleSubmit = async (data: FeatureFlagFormData) => {
    try {
      await onSubmit(data)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      if (apiError.data?.detail) {
        form.setError('root', { message: apiError.data.detail })
      }
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="key"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('featureFlags.form.key')}</FormLabel>
              <FormControl>
                <Input {...field} disabled={!!initialData} />
              </FormControl>
              <FormDescription>
                {t('featureFlags.form.keyDescription')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('featureFlags.form.name')}</FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormDescription>
                {t('featureFlags.form.nameDescription')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('featureFlags.form.description')}</FormLabel>
              <FormControl>
                <Textarea {...field} rows={3} />
              </FormControl>
              <FormDescription>
                {t('featureFlags.form.descriptionDescription')}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="default_enabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
              <div className="space-y-0.5">
                <FormLabel>{t('featureFlags.form.defaultEnabled')}</FormLabel>
                <FormDescription>
                  {t('featureFlags.form.defaultEnabledDescription')}
                </FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        {form.formState.errors.root && (
          <div className="text-sm text-destructive">
            {form.formState.errors.root.message}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onCancel}>
            {t('featureFlags.form.cancel')}
          </Button>
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? t('featureFlags.form.saving') : t('featureFlags.form.save')}
          </Button>
        </div>
      </form>
    </Form>
  )
}
