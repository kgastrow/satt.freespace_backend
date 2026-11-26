import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from '@/lib/toast'
import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { TagInput } from '@/components/TagInput'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
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
  useGetFileSettingsQuery,
  useUpdateFileSettingsMutation,
} from '@/features/files/filesApi'

const settingsSchema = z.object({
  max_file_size_mb: z.number().min(1).max(1024),
  max_video_size_mb: z.number().min(1).max(10240),
  allowed_extensions: z.array(z.string()),
  user_storage_quota_gb: z.number().min(0).nullable(),
  org_storage_quota_gb: z.number().min(0).nullable(),
  signed_url_expiry_seconds: z.number().min(60).max(86400),
  deleted_file_retention_days: z.number().min(0).max(365),
})

type SettingsFormData = z.infer<typeof settingsSchema>

const MB = 1024 * 1024
const GB = 1024 * 1024 * 1024

export function FileSettingsPage() {
  const navigate = useNavigate()
  const { data: settings, isLoading } = useGetFileSettingsQuery()
  const [updateSettings, { isLoading: isUpdating }] = useUpdateFileSettingsMutation()

  const form = useForm<SettingsFormData>({
    resolver: zodResolver(settingsSchema),
    defaultValues: {
      max_file_size_mb: 100,
      max_video_size_mb: 500,
      allowed_extensions: [],
      user_storage_quota_gb: null,
      org_storage_quota_gb: null,
      signed_url_expiry_seconds: 3600,
      deleted_file_retention_days: 30,
    },
  })

  useEffect(() => {
    if (settings) {
      form.reset({
        max_file_size_mb: Math.round(settings.max_file_size_bytes / MB),
        max_video_size_mb: Math.round(settings.max_video_size_bytes / MB),
        allowed_extensions: settings.allowed_extensions,
        user_storage_quota_gb: settings.user_storage_quota_bytes
          ? Math.round(settings.user_storage_quota_bytes / GB)
          : null,
        org_storage_quota_gb: settings.org_storage_quota_bytes
          ? Math.round(settings.org_storage_quota_bytes / GB)
          : null,
        signed_url_expiry_seconds: settings.signed_url_expiry_seconds,
        deleted_file_retention_days: settings.deleted_file_retention_days,
      })
    }
  }, [settings, form])

  const handleSubmit = async (data: SettingsFormData) => {
    try {
      await updateSettings({
        max_file_size_bytes: data.max_file_size_mb * MB,
        max_video_size_bytes: data.max_video_size_mb * MB,
        allowed_extensions: data.allowed_extensions,
        user_storage_quota_bytes: data.user_storage_quota_gb
          ? data.user_storage_quota_gb * GB
          : null,
        org_storage_quota_bytes: data.org_storage_quota_gb
          ? data.org_storage_quota_gb * GB
          : null,
        signed_url_expiry_seconds: data.signed_url_expiry_seconds,
        deleted_file_retention_days: data.deleted_file_retention_days,
      }).unwrap()
      toast.success('Settings updated successfully')
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update settings')
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader title="File Settings" description="Configure file upload and storage settings">
        <Button variant="outline" onClick={() => navigate('/admin/files')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
      </PageHeader>

      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
          {/* Size Limits */}
          <Card>
            <CardHeader>
              <CardTitle>Size Limits</CardTitle>
              <CardDescription>Configure maximum file sizes</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="max_file_size_mb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max File Size (MB)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={1024}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 1)}
                      />
                    </FormControl>
                    <FormDescription>Maximum size for regular files</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="max_video_size_mb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Video Size (MB)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={1}
                        max={10240}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 1)}
                      />
                    </FormControl>
                    <FormDescription>Maximum size for video files</FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Allowed Extensions */}
          <Card>
            <CardHeader>
              <CardTitle>Allowed File Types</CardTitle>
              <CardDescription>
                Specify which file extensions users can upload
              </CardDescription>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="allowed_extensions"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Allowed Extensions</FormLabel>
                    <FormControl>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Type extension and press Enter (e.g., pdf, jpg)"
                      />
                    </FormControl>
                    <FormDescription>
                      Enter file extensions without the dot (e.g., &quot;pdf&quot;, &quot;jpg&quot;, &quot;docx&quot;)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* Storage Quotas */}
          <Card>
            <CardHeader>
              <CardTitle>Storage Quotas</CardTitle>
              <CardDescription>
                Set storage limits for users and the organization
              </CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="user_storage_quota_gb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>User Storage Quota (GB)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        placeholder="Unlimited"
                        value={field.value ?? ''}
                        onChange={(e) => {
                          const val = e.target.value
                          field.onChange(val === '' ? null : parseInt(val))
                        }}
                      />
                    </FormControl>
                    <FormDescription>
                      Leave empty for unlimited. Per-user storage limit.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="org_storage_quota_gb"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Organization Storage Quota (GB)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        placeholder="Unlimited"
                        value={field.value ?? ''}
                        onChange={(e) => {
                          const val = e.target.value
                          field.onChange(val === '' ? null : parseInt(val))
                        }}
                      />
                    </FormControl>
                    <FormDescription>
                      Leave empty for unlimited. Total organization storage limit.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          {/* URL & Retention Settings */}
          <Card>
            <CardHeader>
              <CardTitle>URL & Retention</CardTitle>
              <CardDescription>Configure download URLs and file retention</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="signed_url_expiry_seconds"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Download URL Expiry (seconds)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={60}
                        max={86400}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 3600)}
                      />
                    </FormControl>
                    <FormDescription>
                      How long download URLs remain valid (60s - 24h)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="deleted_file_retention_days"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Deleted File Retention (days)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        max={365}
                        {...field}
                        onChange={(e) => field.onChange(parseInt(e.target.value) || 0)}
                      />
                    </FormControl>
                    <FormDescription>
                      Days to keep deleted files before permanent removal
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <div className="flex justify-end gap-4">
            <Button
              type="button"
              variant="outline"
              onClick={() => navigate('/admin/files')}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isUpdating}>
              {isUpdating ? 'Saving...' : 'Save Settings'}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  )
}
