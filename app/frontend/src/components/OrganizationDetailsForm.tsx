import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import {
  useGetOrganizationDetailsQuery,
  useUpdateOrganizationDetailsMutation,
} from '@/store/api/organizationApi'

const organizationDetailsSchema = z.object({
  display_name: z.string().max(255).optional().or(z.literal('')),
  physical_address_line1: z.string().max(255).optional().or(z.literal('')),
  physical_address_line2: z.string().max(255).optional().or(z.literal('')),
  city: z.string().max(255).optional().or(z.literal('')),
  state_province: z.string().max(255).optional().or(z.literal('')),
  postal_code: z.string().max(255).optional().or(z.literal('')),
  country: z.string().max(255).optional().or(z.literal('')),
  contact_email: z.string().email().optional().or(z.literal('')),
  contact_phone: z.string().max(255).optional().or(z.literal('')),
})

type OrganizationDetailsFormData = z.infer<typeof organizationDetailsSchema>

interface OrganizationDetailsFormProps {
  organizationId: string
  onSuccess?: () => void
  variant?: 'card' | 'inline'
  namespace?: string
}

export function OrganizationDetailsForm({
  organizationId,
  onSuccess,
  variant = 'card',
  namespace = 'settings',
}: OrganizationDetailsFormProps) {
  const { t } = useTranslation(namespace)

  const {
    data: organization,
    isLoading,
    error,
  } = useGetOrganizationDetailsQuery(organizationId, {
    skip: !organizationId,
  })

  const [updateOrganization, { isLoading: isUpdating }] =
    useUpdateOrganizationDetailsMutation()

  const form = useForm<OrganizationDetailsFormData>({
    resolver: zodResolver(organizationDetailsSchema),
    defaultValues: {
      display_name: '',
      physical_address_line1: '',
      physical_address_line2: '',
      city: '',
      state_province: '',
      postal_code: '',
      country: '',
      contact_email: '',
      contact_phone: '',
    },
    values: organization
      ? {
          display_name: organization.display_name || '',
          physical_address_line1: organization.physical_address_line1 || '',
          physical_address_line2: organization.physical_address_line2 || '',
          city: organization.city || '',
          state_province: organization.state_province || '',
          postal_code: organization.postal_code || '',
          country: organization.country || '',
          contact_email: organization.contact_email || '',
          contact_phone: organization.contact_phone || '',
        }
      : undefined,
  })

  const handleSubmit = async (data: OrganizationDetailsFormData) => {
    if (!organizationId) return

    try {
      const payload = Object.entries(data).reduce(
        (acc, [key, value]) => {
          acc[key] = value === '' ? null : value
          return acc
        },
        {} as Record<string, string | null>
      )

      await updateOrganization({
        organizationId,
        data: payload,
      }).unwrap()

      toast.success(t('organizationDetails.messages.updateSuccess'))
      onSuccess?.()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(
        apiError.data?.detail || t('organizationDetails.messages.updateError')
      )
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertTitle>{t('organizationDetails.error.title')}</AlertTitle>
        <AlertDescription>
          {t('organizationDetails.error.description')}
        </AlertDescription>
      </Alert>
    )
  }

  const formContent = (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
        {variant === 'card' ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>
                  {t('organizationDetails.sections.basic.title')}
                </CardTitle>
                <CardDescription>
                  {t('organizationDetails.sections.basic.description')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="display_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        {t('organizationDetails.fields.displayName')}
                      </FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormDescription>
                        {t('organizationDetails.fields.displayNameHelp')}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>
                  {t('organizationDetails.sections.address.title')}
                </CardTitle>
                <CardDescription>
                  {t('organizationDetails.sections.address.description')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <AddressFields form={form} t={t} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>
                  {t('organizationDetails.sections.contact.title')}
                </CardTitle>
                <CardDescription>
                  {t('organizationDetails.sections.contact.description')}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <ContactFields form={form} t={t} />
              </CardContent>
            </Card>
          </>
        ) : (
          <div className="space-y-6">
            <div className="space-y-4">
              <h4 className="font-medium">{t('organizationDetails.sections.basic.title')}</h4>
              <FormField
                control={form.control}
                name="display_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      {t('organizationDetails.fields.displayName')}
                    </FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormDescription>
                      {t('organizationDetails.fields.displayNameHelp')}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <div className="space-y-4">
              <h4 className="font-medium">{t('organizationDetails.sections.address.title')}</h4>
              <AddressFields form={form} t={t} />
            </div>

            <div className="space-y-4">
              <h4 className="font-medium">{t('organizationDetails.sections.contact.title')}</h4>
              <ContactFields form={form} t={t} />
            </div>
          </div>
        )}

        <div className="flex justify-end">
          <Button type="submit" disabled={isUpdating}>
            {isUpdating
              ? t('organizationDetails.buttons.saving')
              : t('organizationDetails.buttons.save')}
          </Button>
        </div>
      </form>
    </Form>
  )

  return formContent
}

interface FormFieldsProps {
  form: ReturnType<typeof useForm<OrganizationDetailsFormData>>
  t: (key: string) => string
}

function AddressFields({ form, t }: FormFieldsProps) {
  return (
    <>
      <FormField
        control={form.control}
        name="physical_address_line1"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {t('organizationDetails.fields.addressLine1')}
            </FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="physical_address_line2"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {t('organizationDetails.fields.addressLine2')}
            </FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="city"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('organizationDetails.fields.city')}
              </FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="state_province"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('organizationDetails.fields.stateProvince')}
              </FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <FormField
          control={form.control}
          name="postal_code"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('organizationDetails.fields.postalCode')}
              </FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="country"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t('organizationDetails.fields.country')}
              </FormLabel>
              <FormControl>
                <Input {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>
    </>
  )
}

function ContactFields({ form, t }: FormFieldsProps) {
  return (
    <>
      <FormField
        control={form.control}
        name="contact_email"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {t('organizationDetails.fields.contactEmail')}
            </FormLabel>
            <FormControl>
              <Input type="email" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="contact_phone"
        render={({ field }) => (
          <FormItem>
            <FormLabel>
              {t('organizationDetails.fields.contactPhone')}
            </FormLabel>
            <FormControl>
              <Input {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </>
  )
}
