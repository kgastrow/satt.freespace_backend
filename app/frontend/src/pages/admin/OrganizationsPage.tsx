import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { DataTable, type Column } from '@/components/DataTable'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  useGetOrganizationsQuery,
  useCreateOrganizationMutation,
  useUpdateOrganizationMutation,
  useDeleteOrganizationMutation,
  useCancelOrganizationDeletionRequestMutation,
  useLazyGetHardDeleteStatusQuery,
  useHardDeleteOrganizationMutation,
  useLazyGetOrg2FASettingsQuery,
  useSetOrg2FAAllowedMutation,
  type Organization,
} from '@/features/organizations/organizationsApi'
import {
  useGetOrganizationDetailsQuery,
  useUpdateOrganizationDetailsMutation,
} from '@/store/api/organizationApi'
import {
  useLazyGetOrgSSOSettingsQuery,
  useSetSSOAllowedMutation,
} from '@/features/auth/ssoApi'

const organizationSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  slug: z
    .string()
    .min(1, 'Slug is required')
    .regex(/^[a-z0-9-]+$/, 'Slug must be lowercase letters, numbers, and hyphens only'),
  isActive: z.boolean(),
  // Organization details fields
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

type OrganizationFormData = z.infer<typeof organizationSchema>

export function OrganizationsPage() {
  const { t } = useTranslation(['admin'])
  const [page, setPage] = useState(1)
  const pageSize = 10

  const { data, isLoading } = useGetOrganizationsQuery({
    limit: pageSize,
    offset: (page - 1) * pageSize,
  })

  const [createOrg, { isLoading: isCreating }] = useCreateOrganizationMutation()
  const [updateOrg, { isLoading: isUpdating }] = useUpdateOrganizationMutation()
  const [deleteOrg, { isLoading: isDeleting }] = useDeleteOrganizationMutation()
  const [cancelDeletion, { isLoading: isCanceling }] = useCancelOrganizationDeletionRequestMutation()
  const [getHardDeleteStatus] = useLazyGetHardDeleteStatusQuery()
  const [hardDeleteOrg, { isLoading: isHardDeleting }] = useHardDeleteOrganizationMutation()
  const [getOrgSSOSettings] = useLazyGetOrgSSOSettingsQuery()
  const [setSSOAllowed] = useSetSSOAllowedMutation()
  const [getOrg2FASettings] = useLazyGetOrg2FASettingsQuery()
  const [setOrg2FAAllowed] = useSetOrg2FAAllowedMutation()
  const [updateOrgDetails, { isLoading: isUpdatingDetails }] = useUpdateOrganizationDetailsMutation()

  // Track SSO allowed status per organization
  const [ssoAllowedMap, setSsoAllowedMap] = useState<Record<string, boolean>>({})
  const [ssoLoadingMap, setSsoLoadingMap] = useState<Record<string, boolean>>({})

  // Track 2FA allowed status per organization
  const [twoFaAllowedMap, setTwoFaAllowedMap] = useState<Record<string, boolean>>({})
  const [twoFaLoadingMap, setTwoFaLoadingMap] = useState<Record<string, boolean>>({})

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [editingOrg, setEditingOrg] = useState<Organization | null>(null)
  const [deletingOrg, setDeletingOrg] = useState<Organization | null>(null)
  const [cancelingOrg, setCancelingOrg] = useState<Organization | null>(null)
  const [hardDeletingOrg, setHardDeletingOrg] = useState<Organization | null>(null)
  const [hardDeleteInfo, setHardDeleteInfo] = useState<{
    canDelete: boolean
    daysRemaining: number
  } | null>(null)

  const form = useForm<OrganizationFormData>({
    resolver: zodResolver(organizationSchema),
    defaultValues: {
      name: '',
      slug: '',
      isActive: true,
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
  })

  // Fetch organization details when editing
  const { data: orgDetails, isLoading: isLoadingDetails } = useGetOrganizationDetailsQuery(
    editingOrg?.id || '',
    { skip: !editingOrg }
  )

  // Update form with organization details when they load
  useEffect(() => {
    if (orgDetails && editingOrg) {
      form.setValue('display_name', orgDetails.display_name || '')
      form.setValue('physical_address_line1', orgDetails.physical_address_line1 || '')
      form.setValue('physical_address_line2', orgDetails.physical_address_line2 || '')
      form.setValue('city', orgDetails.city || '')
      form.setValue('state_province', orgDetails.state_province || '')
      form.setValue('postal_code', orgDetails.postal_code || '')
      form.setValue('country', orgDetails.country || '')
      form.setValue('contact_email', orgDetails.contact_email || '')
      form.setValue('contact_phone', orgDetails.contact_phone || '')
    }
  }, [orgDetails, editingOrg, form])

  // Load SSO settings for each organization
  const loadSSOSettings = useCallback(async (orgId: string) => {
    try {
      const result = await getOrgSSOSettings({ organizationId: orgId }).unwrap()
      setSsoAllowedMap((prev) => ({ ...prev, [orgId]: result.sso_allowed }))
    } catch {
      // SSO settings don't exist yet - default to false
      setSsoAllowedMap((prev) => ({ ...prev, [orgId]: false }))
    }
  }, [getOrgSSOSettings])

  // Load 2FA settings for each organization
  const load2FASettings = useCallback(async (orgId: string) => {
    try {
      const result = await getOrg2FASettings(orgId).unwrap()
      setTwoFaAllowedMap((prev) => ({ ...prev, [orgId]: result.two_factor_allowed }))
    } catch {
      // 2FA settings don't exist yet - default to false
      setTwoFaAllowedMap((prev) => ({ ...prev, [orgId]: false }))
    }
  }, [getOrg2FASettings])

  useEffect(() => {
    if (data?.items) {
      data.items.forEach((org: Organization) => {
        if (!(org.id in ssoAllowedMap)) {
          loadSSOSettings(org.id)
        }
        if (!(org.id in twoFaAllowedMap)) {
          load2FASettings(org.id)
        }
      })
    }
  }, [data?.items, ssoAllowedMap, twoFaAllowedMap, loadSSOSettings, load2FASettings])

  const handleToggleSSO = async (orgId: string, currentValue: boolean) => {
    setSsoLoadingMap((prev) => ({ ...prev, [orgId]: true }))
    try {
      const result = await setSSOAllowed({ organizationId: orgId, ssoAllowed: !currentValue }).unwrap()
      setSsoAllowedMap((prev) => ({ ...prev, [orgId]: result.sso_allowed }))
      toast.success(`SSO ${result.sso_allowed ? 'enabled' : 'disabled'} for organization`)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to update SSO settings')
    } finally {
      setSsoLoadingMap((prev) => ({ ...prev, [orgId]: false }))
    }
  }

  const handleToggle2FA = async (orgId: string, currentValue: boolean) => {
    setTwoFaLoadingMap((prev) => ({ ...prev, [orgId]: true }))
    try {
      const result = await setOrg2FAAllowed({ organizationId: orgId, twoFaAllowed: !currentValue }).unwrap()
      setTwoFaAllowedMap((prev) => ({ ...prev, [orgId]: result.two_factor_allowed }))
      toast.success(t(result.two_factor_allowed ? 'admin:organizations.twoFactor.toast.enableSuccess' : 'admin:organizations.twoFactor.toast.disableSuccess'))
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:organizations.twoFactor.toast.updateError'))
    } finally {
      setTwoFaLoadingMap((prev) => ({ ...prev, [orgId]: false }))
    }
  }

  const handleCreate = async (data: OrganizationFormData) => {
    try {
      await createOrg({
        name: data.name,
        slug: data.slug,
      }).unwrap()
      toast.success('Organization created successfully')
      setIsCreateOpen(false)
      form.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to create organization')
    }
  }

  const handleEdit = async (data: OrganizationFormData) => {
    if (!editingOrg) return
    try {
      // Update basic organization info
      await updateOrg({
        id: editingOrg.id,
        data: {
          name: data.name,
          slug: data.slug,
          is_active: data.isActive,
        },
      }).unwrap()

      // Update organization details
      const detailsPayload = {
        display_name: data.display_name || null,
        physical_address_line1: data.physical_address_line1 || null,
        physical_address_line2: data.physical_address_line2 || null,
        city: data.city || null,
        state_province: data.state_province || null,
        postal_code: data.postal_code || null,
        country: data.country || null,
        contact_email: data.contact_email || null,
        contact_phone: data.contact_phone || null,
      }

      await updateOrgDetails({
        organizationId: editingOrg.id,
        data: detailsPayload,
      }).unwrap()

      toast.success(t('admin:organizations.toast.updateSuccess', 'Organization updated successfully'))
      setEditingOrg(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || t('admin:organizations.toast.updateError', 'Failed to update organization'))
    }
  }

  const handleDelete = async () => {
    if (!deletingOrg) return
    try {
      await deleteOrg(deletingOrg.id).unwrap()
      toast.success('Organization soft-deleted successfully')
      setDeletingOrg(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to delete organization')
    }
  }

  const handleCancelDeletion = async () => {
    if (!cancelingOrg) return
    try {
      await cancelDeletion(cancelingOrg.id).unwrap()
      toast.success('Deletion request cancelled')
      setCancelingOrg(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to cancel deletion request')
    }
  }

  const handleHardDeleteClick = async (org: Organization) => {
    try {
      const status = await getHardDeleteStatus(org.id).unwrap()
      setHardDeleteInfo({
        canDelete: status.can_hard_delete,
        daysRemaining: status.days_remaining,
      })
      setHardDeletingOrg(org)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to check hard-delete status')
    }
  }

  const handleHardDelete = async () => {
    if (!hardDeletingOrg) return
    try {
      const result = await hardDeleteOrg(hardDeletingOrg.id).unwrap()
      toast.success(`Organization permanently deleted. ${result.s3_files_deleted} files removed.`)
      setHardDeletingOrg(null)
      setHardDeleteInfo(null)
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string } }
      toast.error(apiError.data?.detail || 'Failed to hard-delete organization')
    }
  }

  const openEditDialog = (org: Organization) => {
    form.reset({
      name: org.name,
      slug: org.slug,
      isActive: org.is_active,
      // Reset details fields - they'll be populated by useEffect when orgDetails loads
      display_name: '',
      physical_address_line1: '',
      physical_address_line2: '',
      city: '',
      state_province: '',
      postal_code: '',
      country: '',
      contact_email: '',
      contact_phone: '',
    })
    setEditingOrg(org)
  }

  const openCreateDialog = () => {
    form.reset({
      name: '',
      slug: '',
      isActive: true,
    })
    setIsCreateOpen(true)
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString()
  }

  const columns: Column<Organization>[] = [
    {
      key: 'name',
      header: 'Name',
      cell: (org) => org.name,
    },
    {
      key: 'slug',
      header: 'Slug',
      cell: (org) => <code className="text-sm">{org.slug}</code>,
    },
    {
      key: 'status',
      header: 'Status',
      cell: (org) => (
        <div className="flex flex-wrap gap-1">
          <Badge variant={org.is_active ? 'default' : 'secondary'}>
            {org.is_active ? 'Active' : 'Inactive'}
          </Badge>
          {org.deletion_requested && (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant="destructive">
                    Deletion Requested
                  </Badge>
                </TooltipTrigger>
                <TooltipContent>
                  <p>Requested on {formatDate(org.deletion_requested_time!)}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
      ),
    },
    {
      key: 'sso',
      header: 'SSO Allowed',
      cell: (org) => (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <Switch
                  checked={ssoAllowedMap[org.id] ?? false}
                  onCheckedChange={() => handleToggleSSO(org.id, ssoAllowedMap[org.id] ?? false)}
                  disabled={ssoLoadingMap[org.id]}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>{ssoAllowedMap[org.id] ? 'SSO is allowed for this organization' : 'SSO is not allowed'}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ),
    },
    {
      key: 'twoFactor',
      header: t('admin:organizations.twoFactor.columnHeader'),
      cell: (org) => (
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div>
                <Switch
                  checked={twoFaAllowedMap[org.id] ?? false}
                  onCheckedChange={() => handleToggle2FA(org.id, twoFaAllowedMap[org.id] ?? false)}
                  disabled={twoFaLoadingMap[org.id]}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent>
              <p>{t(twoFaAllowedMap[org.id] ? 'admin:organizations.twoFactor.tooltip.enabled' : 'admin:organizations.twoFactor.tooltip.disabled')}</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      ),
    },
    {
      key: 'created',
      header: 'Created',
      cell: (org) => formatDate(org.created_time),
    },
    {
      key: 'actions',
      header: '',
      className: 'w-[80px]',
      cell: (org) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm">
              ...
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => openEditDialog(org)}>
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link to={`/platform-admin/organizations/${org.id}/members`}>
                View Members
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {org.deletion_requested ? (
              <>
                <DropdownMenuItem
                  onClick={() => setCancelingOrg(org)}
                  className="text-orange-500/90 dark:text-orange-400/90"
                >
                  Cancel Deletion Request
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => handleHardDeleteClick(org)}
                  className="text-destructive"
                >
                  Permanently Delete
                </DropdownMenuItem>
              </>
            ) : (
              <DropdownMenuItem
                onClick={() => setDeletingOrg(org)}
                className="text-destructive"
              >
                Delete
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Organization Management"
        description="Manage all organizations in the system"
      >
        <Button onClick={openCreateDialog}>Create Organization</Button>
      </PageHeader>

      <DataTable
        columns={columns}
        data={data?.items || []}
        isLoading={isLoading}
        emptyMessage="No organizations found"
        pagination={{
          page,
          pageSize,
          total: data?.total || 0,
          onPageChange: setPage,
        }}
      />

      {/* Create Organization Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Organization</DialogTitle>
            <DialogDescription>Add a new organization to the system</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleCreate)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
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
                    <FormLabel>Slug</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="my-organization"
                        onChange={(e) =>
                          field.onChange(e.target.value.toLowerCase().replace(/\s+/g, '-'))
                        }
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? 'Creating...' : 'Create'}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Edit Organization Dialog */}
      <Dialog open={!!editingOrg} onOpenChange={() => setEditingOrg(null)}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('admin:organizations.editDialog.title', 'Edit Organization')}</DialogTitle>
            <DialogDescription>{t('admin:organizations.editDialog.description', 'Update organization information')}</DialogDescription>
          </DialogHeader>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(handleEdit)} className="space-y-4">
              <Tabs defaultValue="basic" className="w-full">
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="basic">{t('admin:organizations.editDialog.basicTab', 'Basic Info')}</TabsTrigger>
                  <TabsTrigger value="details">{t('admin:organizations.editDialog.detailsTab', 'Details')}</TabsTrigger>
                </TabsList>
                <TabsContent value="basic" className="space-y-4 mt-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>{t('admin:organizations.editDialog.fields.name', 'Name')}</FormLabel>
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
                        <FormLabel>{t('admin:organizations.editDialog.fields.slug', 'Slug')}</FormLabel>
                        <FormControl>
                          <Input {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="isActive"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2">
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                        <FormLabel className="!mt-0">{t('admin:organizations.editDialog.fields.active', 'Active')}</FormLabel>
                      </FormItem>
                    )}
                  />
                </TabsContent>
                <TabsContent value="details" className="space-y-4 mt-4">
                  {isLoadingDetails ? (
                    <div className="space-y-4">
                      <div className="h-10 bg-muted animate-pulse rounded" />
                      <div className="h-10 bg-muted animate-pulse rounded" />
                      <div className="h-10 bg-muted animate-pulse rounded" />
                    </div>
                  ) : (
                    <>
                      <FormField
                        control={form.control}
                        name="display_name"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>{t('admin:organizations.editDialog.fields.displayName', 'Display Name')}</FormLabel>
                            <FormControl>
                              <Input {...field} />
                            </FormControl>
                            <FormDescription>{t('admin:organizations.editDialog.fields.displayNameHelp', 'Optional friendly name for the organization')}</FormDescription>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <div className="grid grid-cols-2 gap-4">
                        <FormField
                          control={form.control}
                          name="physical_address_line1"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('admin:organizations.editDialog.fields.addressLine1', 'Address Line 1')}</FormLabel>
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
                              <FormLabel>{t('admin:organizations.editDialog.fields.addressLine2', 'Address Line 2')}</FormLabel>
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
                          name="city"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('admin:organizations.editDialog.fields.city', 'City')}</FormLabel>
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
                              <FormLabel>{t('admin:organizations.editDialog.fields.stateProvince', 'State/Province')}</FormLabel>
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
                              <FormLabel>{t('admin:organizations.editDialog.fields.postalCode', 'Postal Code')}</FormLabel>
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
                              <FormLabel>{t('admin:organizations.editDialog.fields.country', 'Country')}</FormLabel>
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
                          name="contact_email"
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>{t('admin:organizations.editDialog.fields.contactEmail', 'Contact Email')}</FormLabel>
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
                              <FormLabel>{t('admin:organizations.editDialog.fields.contactPhone', 'Contact Phone')}</FormLabel>
                              <FormControl>
                                <Input {...field} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </>
                  )}
                </TabsContent>
              </Tabs>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setEditingOrg(null)}
                >
                  {t('admin:organizations.editDialog.cancel', 'Cancel')}
                </Button>
                <Button type="submit" disabled={isUpdating || isUpdatingDetails}>
                  {(isUpdating || isUpdatingDetails) ? t('admin:organizations.editDialog.saving', 'Saving...') : t('admin:organizations.editDialog.save', 'Save')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>

      {/* Soft Delete Confirmation */}
      <ConfirmDialog
        open={!!deletingOrg}
        onOpenChange={() => setDeletingOrg(null)}
        title="Delete Organization"
        description={`Are you sure you want to delete "${deletingOrg?.name}"? This will soft-delete the organization and all its data. The data will be retained for the configured retention period before it can be permanently deleted.`}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        isLoading={isDeleting}
        variant="destructive"
      />

      {/* Cancel Deletion Request Confirmation */}
      <ConfirmDialog
        open={!!cancelingOrg}
        onOpenChange={() => setCancelingOrg(null)}
        title="Cancel Deletion Request"
        description={`Are you sure you want to cancel the deletion request for "${cancelingOrg?.name}"? The organization will remain active.`}
        confirmLabel="Cancel Request"
        onConfirm={handleCancelDeletion}
        isLoading={isCanceling}
      />

      {/* Hard Delete Confirmation */}
      <ConfirmDialog
        open={!!hardDeletingOrg}
        onOpenChange={() => {
          setHardDeletingOrg(null)
          setHardDeleteInfo(null)
        }}
        title="Permanently Delete Organization"
        description={
          hardDeleteInfo?.canDelete
            ? `WARNING: This action is IRREVERSIBLE. You are about to permanently delete "${hardDeletingOrg?.name}" and ALL associated data including users, files, notifications, and audit logs. S3 files will also be permanently deleted.`
            : `Cannot permanently delete "${hardDeletingOrg?.name}" yet. ${hardDeleteInfo?.daysRemaining} days remaining in the retention period.`
        }
        confirmLabel={hardDeleteInfo?.canDelete ? "Permanently Delete" : "Close"}
        onConfirm={hardDeleteInfo?.canDelete ? handleHardDelete : () => {
          setHardDeletingOrg(null)
          setHardDeleteInfo(null)
        }}
        isLoading={isHardDeleting}
        variant={hardDeleteInfo?.canDelete ? "destructive" : "default"}
      />
    </div>
  )
}
