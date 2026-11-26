import { useEffect } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { InfoIcon, ShieldAlert } from 'lucide-react'
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
  useGetSSOSettingsQuery,
  useUpdateSSOSettingsMutation,
} from '@/features/auth/ssoApi'
import { usePermission } from '@/hooks/usePermission'

const ssoSettingsSchema = z.object({
  google_enabled: z.boolean(),
  google_client_id: z.string().optional(),
  google_client_secret: z.string().optional(),
})

type SSOSettingsFormData = z.infer<typeof ssoSettingsSchema>

export function SSOSettingsPage() {
  const { canWrite } = usePermission('organization')
  const { data: settings, isLoading, error } = useGetSSOSettingsQuery()
  const [updateSettings, { isLoading: isUpdating }] = useUpdateSSOSettingsMutation()

  const form = useForm<SSOSettingsFormData>({
    resolver: zodResolver(ssoSettingsSchema),
    defaultValues: {
      google_enabled: false,
      google_client_id: '',
      google_client_secret: '',
    },
  })

  const googleEnabled = useWatch({ control: form.control, name: 'google_enabled' })

  useEffect(() => {
    if (settings) {
      form.reset({
        google_enabled: settings.google_enabled,
        google_client_id: settings.google_client_id || '',
        google_client_secret: '',
      })
    }
  }, [settings, form])

  const handleSubmit = async (data: SSOSettingsFormData) => {
    try {
      const updateData: Record<string, boolean | string | undefined> = {
        google_enabled: data.google_enabled,
      }

      if (data.google_client_id) {
        updateData.google_client_id = data.google_client_id
      }

      if (data.google_client_secret) {
        updateData.google_client_secret = data.google_client_secret
      }

      await updateSettings(updateData).unwrap()
      toast.success('SSO settings updated successfully')
      form.setValue('google_client_secret', '')
    } catch (err: unknown) {
      const apiError = err as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update SSO settings')
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  if (error) {
    const apiError = error as { status?: number; data?: { detail?: string } }
    const is404 = apiError.status === 404

    if (is404) {
      return (
        <div className="space-y-6">
          <PageHeader
            title="SSO Settings"
            description="Configure Single Sign-On providers for your organization"
          />
          <Alert>
            <InfoIcon className="h-4 w-4" />
            <AlertTitle>SSO Not Configured</AlertTitle>
            <AlertDescription>
              SSO settings have not been configured for this organization yet.
              Please contact a super administrator to enable SSO for your organization.
            </AlertDescription>
          </Alert>
        </div>
      )
    }

    return (
      <div className="space-y-6">
        <PageHeader
          title="SSO Settings"
          description="Configure Single Sign-On providers for your organization"
        />
        <Alert variant="destructive">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>
            {apiError.data?.detail || 'Failed to load SSO settings'}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  // Check if SSO is allowed by super admin
  if (!settings?.sso_allowed) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="SSO Settings"
          description="Configure Single Sign-On providers for your organization"
        />
        <Alert>
          <ShieldAlert className="h-4 w-4" />
          <AlertTitle>SSO Not Allowed</AlertTitle>
          <AlertDescription>
            Single Sign-On is not enabled for your organization.
            Please contact a super administrator to enable SSO for your organization.
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="SSO Settings"
        description="Configure Single Sign-On providers for your organization"
      />

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Google SSO Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Google SSO</CardTitle>
              <CardDescription>
                Enable Google Single Sign-On for your organization
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <FormField
                control={form.control}
                name="google_enabled"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Enable Google SSO</FormLabel>
                      <FormDescription>
                        Allow users to sign in with their Google accounts
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch checked={field.value} onCheckedChange={field.onChange} />
                    </FormControl>
                  </FormItem>
                )}
              />

              {googleEnabled && (
                <>
                  <FormField
                    control={form.control}
                    name="google_client_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Client ID</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="your-client-id.apps.googleusercontent.com"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          The OAuth 2.0 Client ID from Google Cloud Console
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="google_client_secret"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Client Secret</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            placeholder="Enter new client secret to update"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          The OAuth 2.0 Client Secret from Google Cloud Console.
                          Leave empty to keep the existing secret.
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </>
              )}
            </CardContent>
          </Card>

          {canWrite && (
            <div className="flex justify-end">
              <Button type="submit" disabled={isUpdating}>
                {isUpdating ? 'Saving...' : 'Save Settings'}
              </Button>
            </div>
          )}
        </form>
      </Form>
    </div>
  )
}
