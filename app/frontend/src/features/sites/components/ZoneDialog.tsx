import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { useCreateZoneMutation, useUpdateZoneMutation } from '../sitesApi'
import { getServerError } from '../errors'
import { createZoneSchema, type ZoneFormValues } from '../siteSettingsSchema'
import { NumberField } from './NumberField'
import type { Zone } from '@/types/site'

interface ZoneDialogProps {
  siteId: string
  /** null = create a new zone */
  zone: Zone | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CREATE_DEFAULTS: ZoneFormValues = {
  slug: '',
  name: '',
  display_order: 0,
  enabled: true,
  recommendable: true,
  preferred: false,
  priority: 100,
  limited_pct: 80,
  full_pct: 95,
  full_min_free: 5,
  unknown_limit_pct: 25,
  advisory_pct: undefined,
  note: '',
}

function fromZone(zone: Zone): ZoneFormValues {
  return {
    slug: zone.slug,
    name: zone.name,
    display_order: zone.display_order,
    enabled: zone.enabled,
    recommendable: zone.recommendable,
    preferred: zone.preferred,
    priority: zone.priority,
    limited_pct: zone.limited_pct,
    full_pct: zone.full_pct,
    full_min_free: zone.full_min_free,
    unknown_limit_pct: zone.unknown_limit_pct,
    advisory_pct: zone.advisory_pct ?? undefined,
    note: zone.note,
  }
}

type ToggleName = 'enabled' | 'recommendable' | 'preferred'

/** Create or edit a zone. Saving an edit of a discovered zone also marks it reviewed. */
export function ZoneDialog({ siteId, zone, open, onOpenChange }: ZoneDialogProps) {
  const { t } = useTranslation(['sites', 'backend'])
  const isEdit = zone !== null
  const [createZone, { isLoading: isCreating }] = useCreateZoneMutation()
  const [updateZone, { isLoading: isUpdating }] = useUpdateZoneMutation()
  const [serverError, setServerError] = useState<{ message: string; detail: string | null } | null>(
    null
  )
  const schema = useMemo(() => createZoneSchema(t, isEdit ? 'edit' : 'create'), [t, isEdit])

  const form = useForm<ZoneFormValues>({
    resolver: zodResolver(schema),
    defaultValues: zone ? fromZone(zone) : CREATE_DEFAULTS,
  })

  useEffect(() => {
    if (open) {
      setServerError(null)
      form.reset(zone ? fromZone(zone) : CREATE_DEFAULTS)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, zone])

  const onSubmit = async (values: ZoneFormValues) => {
    setServerError(null)
    try {
      if (zone) {
        await updateZone({
          siteId,
          zoneId: zone.id,
          data: {
            name: values.name.trim(),
            display_order: values.display_order,
            enabled: values.enabled,
            recommendable: values.recommendable,
            preferred: values.preferred,
            priority: values.priority,
            limited_pct: values.limited_pct,
            full_pct: values.full_pct,
            full_min_free: values.full_min_free,
            unknown_limit_pct: values.unknown_limit_pct,
            advisory_pct: values.advisory_pct ?? null,
            note: values.note,
            ...(zone.discovered ? { reviewed: true } : {}),
          },
        }).unwrap()
        toast.success(t('sites:zones.updated'))
      } else {
        await createZone({
          siteId,
          data: {
            slug: values.slug,
            name: values.name.trim(),
            display_order: values.display_order,
            enabled: values.enabled,
            recommendable: values.recommendable,
            preferred: values.preferred,
            priority: values.priority,
            limited_pct: values.limited_pct,
            full_pct: values.full_pct,
            full_min_free: values.full_min_free,
            unknown_limit_pct: values.unknown_limit_pct,
            advisory_pct: values.advisory_pct ?? null,
            note: values.note,
          },
        }).unwrap()
        toast.success(t('sites:zones.created'))
      }
      onOpenChange(false)
    } catch (error) {
      setServerError(getServerError(error, t))
    }
  }

  const toggles: ToggleName[] = ['enabled', 'recommendable', 'preferred']

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? t('sites:zones.editTitle') : t('sites:zones.createTitle')}</DialogTitle>
          <DialogDescription>
            {isEdit ? t('sites:zones.editDescription') : t('sites:zones.createDescription')}
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {serverError && (
              <Alert variant="destructive" role="alert">
                <AlertTitle>{serverError.message}</AlertTitle>
                {serverError.detail && <AlertDescription>{serverError.detail}</AlertDescription>}
              </Alert>
            )}
            {isEdit && zone?.discovered && (
              <Alert>
                <AlertDescription>{t('sites:zones.saveMarksReviewed')}</AlertDescription>
              </Alert>
            )}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('sites:zones.fields.name')}</FormLabel>
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
                    <FormLabel>{t('sites:zones.fields.slug')}</FormLabel>
                    <FormControl>
                      <Input {...field} readOnly={isEdit} className="font-mono" />
                    </FormControl>
                    <FormDescription>
                      {isEdit ? t('sites:zones.fields.slugReadOnly') : t('sites:zones.fields.slugHelp')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <NumberField control={form.control} name="display_order"
                label={t('sites:zones.fields.display_order')}
                description={t('sites:zones.fields.display_orderHelp')} />
              <NumberField control={form.control} name="priority"
                label={t('sites:zones.fields.priority')}
                description={t('sites:zones.fields.priorityHelp')} />
            </div>

            <div className="space-y-3">
              {toggles.map((name) => (
                <FormField
                  key={name}
                  control={form.control}
                  name={name}
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between gap-4 space-y-0">
                      <div className="space-y-1">
                        <FormLabel>{t(`sites:zones.fields.${name}`)}</FormLabel>
                        <FormDescription>{t(`sites:zones.fields.${name}Help`)}</FormDescription>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              ))}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <NumberField control={form.control} name="limited_pct" suffix="%"
                label={t('sites:zones.fields.limited_pct')}
                description={t('sites:zones.fields.limited_pctHelp')} />
              <NumberField control={form.control} name="full_pct" suffix="%"
                label={t('sites:zones.fields.full_pct')}
                description={t('sites:zones.fields.full_pctHelp')} />
              <NumberField control={form.control} name="full_min_free" suffix={t('sites:units.bays')}
                label={t('sites:zones.fields.full_min_free')}
                description={t('sites:zones.fields.full_min_freeHelp')} />
              <NumberField control={form.control} name="unknown_limit_pct" suffix="%"
                label={t('sites:zones.fields.unknown_limit_pct')}
                description={t('sites:zones.fields.unknown_limit_pctHelp')} />
              <NumberField control={form.control} name="advisory_pct" suffix="%"
                label={t('sites:zones.fields.advisory_pct')}
                description={t('sites:zones.fields.advisory_pctHelp')} />
            </div>

            <FormField
              control={form.control}
              name="note"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t('sites:zones.fields.note')}</FormLabel>
                  <FormControl>
                    <Textarea {...field} rows={3} />
                  </FormControl>
                  <FormDescription>{t('sites:zones.fields.noteHelp')}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t('sites:actions.cancel')}
              </Button>
              <Button type="submit" disabled={isCreating || isUpdating}>
                {isCreating || isUpdating ? t('sites:actions.saving') : t('sites:actions.save')}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
