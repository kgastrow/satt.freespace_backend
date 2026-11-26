import { useState, useMemo, useCallback, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Eye, EyeOff, HardDrive, Mail, Trash2 } from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { useTranslation } from 'react-i18next'
import { toast } from '@/lib/toast'
import { useAppSelector } from '@/store/hooks'
import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import { PageHeader } from '@/components/PageHeader'
import { AdvancedDataTable, type AdvancedColumn, type SortState, type FilterState } from '@/components/AdvancedDataTable'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { UserAvatar } from '@/components/ui/UserAvatar'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import {
  useGetUsersCursorQuery,
  useCreateUserMutation,
  useListInvitationsQuery,
  useCreateInvitationMutation,
  useRevokeInvitationMutation,
  type UserListItem,
  type InvitationItem,
} from '@/features/users/usersApi'
import { useGetAdminUserTypesQuery } from '@/store/api/onboardingApi'
import { usePermission } from '@/hooks/usePermission'
import { usePreferences } from '@/features/preferences/usePreferences'
import { formatBytes } from '@/lib/utils'

const TABLE_ID = 'admin-users-table'

const userSchema = z.object({
  email: z.string().email('Invalid email'),
  firstName: z.string().min(1, 'First name is required'),
  lastName: z.string().min(1, 'Last name is required'),
  phone: z.string().optional(),
  password: z.string().min(8, 'Password must be at least 8 characters').or(z.literal('')).optional(),
  isAdmin: z.boolean(),
})

const createUserSchema = userSchema.extend({
  password: z.string().min(8, 'Password must be at least 8 characters'),
})

type CreateUserFormData = z.infer<typeof createUserSchema>

// Default visible columns
const DEFAULT_VISIBLE_COLUMNS = [
  'avatar',
  'name',
  'email',
  'user_types',
  'created_time',
  'last_login',
  'suspension_status',
]

export function UsersPage() {
  const { t } = useTranslation('admin')
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user: currentUser } = useAppSelector((state) => state.auth)
  const isSuperAdmin = currentUser?.is_admin === true
  const { canWrite } = usePermission('users')
  const { getTableColumnVisibility, setTableColumnVisibility } = usePreferences()

  // Cursor pagination state
  const pageSize = 10
  const [cursor, setCursor] = useState<string | null>(null)
  const [allUsers, setAllUsers] = useState<UserListItem[]>([])
  const [isLoadingMore, setIsLoadingMore] = useState(false)

  // Search state from URL
  const search = searchParams.get('q') || ''

  // Sort state - cursor pagination uses fixed sort (created_time:desc)
  const sort: SortState | undefined = useMemo(() => {
    // Cursor pagination always sorts by created_time desc
    return { field: 'created_time', direction: 'desc' as const }
  }, [])

  // Filter state from URL
  const filters: FilterState = useMemo(() => {
    const f: FilterState = {}
    const status = searchParams.get('status')
    const userTypeId = searchParams.get('user_type_id')
    const createdVia = searchParams.get('created_via')
    const emailVerified = searchParams.get('email_verified')
    if (status) f.suspension_status = status
    if (userTypeId) f.user_types = userTypeId
    if (createdVia) f.created_via = createdVia
    if (emailVerified !== null && emailVerified !== '') {
      f.email_verified = emailVerified === 'true'
    }
    return f
  }, [searchParams])

  // Column visibility from preferences
  const visibleColumns = getTableColumnVisibility(TABLE_ID, DEFAULT_VISIBLE_COLUMNS)

  // Build fields parameter based on visible columns
  const fieldsParam = useMemo(() => {
    const fieldMap: Record<string, string[]> = {
      avatar: ['avatar_url'],
      name: ['first_name', 'last_name'],
      email: ['email'],
      phone: ['phone'],
      user_types: ['user_types'],
      created_via: ['created_via'],
      created_time: ['created_time'],
      last_login: ['last_login'],
      total_storage_bytes: ['total_storage_bytes'],
      suspension_status: ['suspension_status'],
      email_verified: ['email_verified'],
      roles: ['roles', 'is_admin'],
    }

    const fields = new Set<string>(['id'])
    visibleColumns.forEach((col) => {
      const mapping = fieldMap[col]
      if (mapping) mapping.forEach((f) => fields.add(f))
    })
    // Always need these for actions
    fields.add('suspension_status')
    fields.add('first_name')
    fields.add('last_name')
    fields.add('email')
    fields.add('is_admin')
    fields.add('phone')

    return Array.from(fields).join(',')
  }, [visibleColumns])

  // Build a key to detect when filters/search change (to reset cursor)
  const queryKey = useMemo(() => {
    return JSON.stringify({
      status: filters.suspension_status,
      userTypeId: filters.user_types,
      createdVia: filters.created_via,
      emailVerified: filters.email_verified,
      search,
    })
  }, [filters, search])

  // Reset cursor and accumulated data when filters/search change
  useEffect(() => {
    setCursor(null) // eslint-disable-line react-hooks/set-state-in-effect -- Legitimate reset of derived state when query params change
    setAllUsers([])
  }, [queryKey])

  // Fetch users data with cursor pagination
  const { data, isLoading, isFetching } = useGetUsersCursorQuery({
    limit: pageSize,
    cursor: cursor || undefined,
    fields: fieldsParam,
    'filter[status]': filters.suspension_status as string | undefined,
    'filter[user_type_id]': filters.user_types as string | undefined,
    'filter[created_via]': filters.created_via as string | undefined,
    'filter[email_verified]': typeof filters.email_verified === 'boolean' ? filters.email_verified : undefined,
    q: search || undefined,
  })

  // Accumulate users as pages are loaded
  useEffect(() => {
    if (data?.items) {
      if (cursor === null) {
        // First page - replace all
        setAllUsers(data.items) // eslint-disable-line react-hooks/set-state-in-effect -- Syncing external query data into accumulated state
      } else {
        // Subsequent pages - append
        setAllUsers((prev) => {
          // Avoid duplicates by checking IDs
          const existingIds = new Set(prev.map((u) => u.id))
          const newUsers = data.items.filter((u) => !existingIds.has(u.id))
          return [...prev, ...newUsers]
        })
      }
      setIsLoadingMore(false)
    }
  }, [data, cursor])

  // Fetch user types for filter options
  const { data: userTypesData } = useGetAdminUserTypesQuery()

  const [createUser, { isLoading: isCreating }] = useCreateUserMutation()
  const [createInvitation, { isLoading: isInviting }] = useCreateInvitationMutation()
  const [revokeInvitation] = useRevokeInvitationMutation()
  const { data: invitationsData } = useListInvitationsQuery()

  const [isCreateOpen, setIsCreateOpen] = useState(false)
  const [showCreatePassword, setShowCreatePassword] = useState(false)
  const [isInviteOpen, setIsInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteError, setInviteError] = useState<string | null>(null)
  const [revokingId, setRevokingId] = useState<string | null>(null)

  const createForm = useForm<CreateUserFormData>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      email: '',
      firstName: '',
      lastName: '',
      phone: '',
      password: '',
      isAdmin: false,
    },
  })

  // URL update helpers
  const updateSearchParams = useCallback((updates: Record<string, string | null>) => {
    const newParams = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === '') {
        newParams.delete(key)
      } else {
        newParams.set(key, value)
      }
    })
    setSearchParams(newParams, { replace: true })
  }, [searchParams, setSearchParams])

  const handleLoadMore = useCallback(() => {
    if (data?.next_cursor && !isLoadingMore) {
      setIsLoadingMore(true)
      setCursor(data.next_cursor)
    }
  }, [data, isLoadingMore])

  const handleSearchChange = useCallback((newSearch: string) => {
    updateSearchParams({ q: newSearch || null })
    // Cursor reset is handled by useEffect watching queryKey
  }, [updateSearchParams])

  // Sort is fixed for cursor pagination (created_time:desc)
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSortChange = useCallback((_: SortState | undefined) => {
    // Cursor pagination doesn't support dynamic sorting
    // Always uses created_time:desc for stable pagination
  }, [])

  const handleFiltersChange = useCallback((newFilters: FilterState) => {
    updateSearchParams({
      status: (newFilters.suspension_status as string) || null,
      user_type_id: (newFilters.user_types as string) || null,
      created_via: (newFilters.created_via as string) || null,
      email_verified: newFilters.email_verified !== undefined
        ? String(newFilters.email_verified)
        : null,
    })
    // Cursor reset is handled by useEffect watching queryKey
  }, [updateSearchParams])

  const handleVisibleColumnsChange = useCallback((columns: string[]) => {
    setTableColumnVisibility(TABLE_ID, columns)
  }, [setTableColumnVisibility])

  const handleRowClick = useCallback((user: UserListItem) => {
    navigate(`/admin/users/${user.id}`)
  }, [navigate])

  const handleCreate = async (data: CreateUserFormData) => {
    try {
      await createUser({
        email: data.email,
        first_name: data.firstName,
        last_name: data.lastName,
        phone: data.phone || undefined,
        password: data.password,
        is_admin: data.isAdmin,
      }).unwrap()
      toast.success(t('users.toast.createSuccess'))
      setIsCreateOpen(false)
      createForm.reset()
    } catch (error: unknown) {
      const apiError = error as { data?: { detail?: string | Array<{ msg: string }> } }
      let errorMessage = t('users.toast.createError')
      if (apiError.data?.detail) {
        if (typeof apiError.data.detail === 'string') {
          errorMessage = apiError.data.detail
        } else if (Array.isArray(apiError.data.detail) && apiError.data.detail.length > 0) {
          errorMessage = apiError.data.detail.map(e => e.msg).join(', ')
        }
      }
      toast.error(errorMessage)
    }
  }

  const handleInvite = async () => {
    setInviteError(null)
    if (!inviteEmail || !inviteEmail.includes('@')) {
      setInviteError(t('invitations.emailPlaceholder'))
      return
    }
    try {
      await createInvitation({ email: inviteEmail }).unwrap()
      toast.success(t('invitations.sendSuccess'))
      setIsInviteOpen(false)
      setInviteEmail('')
    } catch {
      toast.error(t('invitations.sendError'))
    }
  }

  const handleRevoke = async (id: string) => {
    setRevokingId(id)
    try {
      await revokeInvitation(id).unwrap()
      toast.success(t('invitations.revokeSuccess'))
    } catch {
      toast.error(t('invitations.revokeError'))
    } finally {
      setRevokingId(null)
    }
  }

  // Build filter options
  const userTypeOptions = useMemo(() => {
    return (userTypesData?.items || []).map((ut) => ({
      value: ut.id,
      label: ut.name,
    }))
  }, [userTypesData])

  const columns: AdvancedColumn<UserListItem>[] = useMemo(() => [
    {
      key: 'avatar',
      header: '',
      alwaysVisible: true,
      className: 'w-12',
      cell: (user) => (
        <UserAvatar
          firstName={user.first_name || ''}
          lastName={user.last_name || ''}
          avatarUrl={user.avatar_url || undefined}
          size="sm"
        />
      ),
    },
    {
      key: 'name',
      header: t('users.table.name'),
      sortable: true,
      sortKey: 'first_name',
      searchable: true,
      defaultVisible: true,
      cell: (user) => (
        <div>
          <div className="font-medium">{`${user.first_name || ''} ${user.last_name || ''}`.trim() || '-'}</div>
          {user.is_admin && (
            <Badge variant="secondary" className="text-xs mt-0.5">{t('users.table.admin')}</Badge>
          )}
        </div>
      ),
    },
    {
      key: 'email',
      header: t('users.table.email'),
      sortable: true,
      searchable: true,
      defaultVisible: true,
      cell: (user) => user.email || '-',
    },
    {
      key: 'phone',
      header: t('users.table.phone', 'Phone'),
      searchable: true,
      defaultVisible: false,
      hiddenOnMobile: true,
      cell: (user) => user.phone || '-',
    },
    {
      key: 'user_types',
      header: t('users.table.userTypes', 'User Types'),
      filterable: true,
      filterConfig: {
        type: 'select',
        options: userTypeOptions,
      },
      defaultVisible: true,
      cell: (user) => (
        <div className="flex flex-wrap gap-1">
          {user.user_types?.map((ut) => (
            <Badge key={ut.id} variant="outline" className="text-xs">
              {ut.name}
            </Badge>
          )) || '-'}
        </div>
      ),
    },
    {
      key: 'created_via',
      header: t('users.table.createdVia', 'Created Via'),
      filterable: true,
      filterConfig: {
        type: 'select',
        options: [
          { value: 'email', label: t('users.createdVia.email', 'Email') },
          { value: 'google', label: t('users.createdVia.google', 'Google') },
        ],
      },
      defaultVisible: false,
      hiddenOnMobile: true,
      cell: (user) => {
        const via = user.created_via
        if (!via) return '-'
        return (
          <Badge variant="secondary">
            {via === 'email' ? t('users.createdVia.email', 'Email') : t('users.createdVia.google', 'Google')}
          </Badge>
        )
      },
    },
    {
      key: 'created_time',
      header: t('users.table.joined', 'Joined'),
      sortable: true,
      defaultVisible: true,
      hiddenOnMobile: true,
      cell: (user) => {
        if (!user.created_time) return '-'
        return new Date(user.created_time).toLocaleDateString()
      },
    },
    {
      key: 'last_login',
      header: t('users.table.lastLogin', 'Last Login'),
      sortable: true,
      defaultVisible: true,
      hiddenOnMobile: true,
      cell: (user) => {
        if (!user.last_login) return t('users.table.never', 'Never')
        return new Date(user.last_login).toLocaleDateString()
      },
    },
    {
      key: 'total_storage_bytes',
      header: t('users.table.storage', 'Storage'),
      defaultVisible: false,
      hiddenOnMobile: true,
      cell: (user) => {
        if (user.total_storage_bytes === null || user.total_storage_bytes === undefined) return '-'
        return (
          <div className="flex items-center gap-1">
            <HardDrive className="h-3 w-3 text-muted-foreground" />
            <span>{formatBytes(user.total_storage_bytes)}</span>
          </div>
        )
      },
    },
    {
      key: 'suspension_status',
      header: t('users.table.status'),
      filterable: true,
      filterConfig: {
        type: 'select',
        options: [
          { value: 'active', label: t('users.table.active') },
          { value: 'suspended', label: t('users.table.suspended') },
        ],
      },
      defaultVisible: true,
      cell: (user) => {
        const isSuspended = user.suspension_status === 'suspended'
        return (
          <Badge variant={isSuspended ? 'destructive' : 'secondary'}>
            {isSuspended ? t('users.table.suspended') : t('users.table.active')}
          </Badge>
        )
      },
    },
    {
      key: 'email_verified',
      header: t('users.table.emailVerified', 'Verified'),
      filterable: true,
      filterConfig: {
        type: 'boolean',
      },
      defaultVisible: false,
      cell: (user) => (
        <Badge variant={user.email_verified ? 'secondary' : 'outline'}>
          {user.email_verified ? t('users.filters.yes', 'Yes') : t('users.filters.no', 'No')}
        </Badge>
      ),
    },
  ], [t, userTypeOptions])

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('users.pageTitle')}
        description={t('users.pageDescription')}
      >
        {canWrite && (
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => setIsInviteOpen(true)}>
              <Mail className="mr-2 h-4 w-4" />
              {t('invitations.invite')}
            </Button>
            <Button onClick={() => setIsCreateOpen(true)}>{t('users.createButton')}</Button>
          </div>
        )}
      </PageHeader>

      <AdvancedDataTable
        columns={columns}
        data={allUsers}
        isLoading={isLoading && allUsers.length === 0}
        emptyMessage={t('users.emptyMessage')}
        sort={sort}
        onSortChange={handleSortChange}
        filters={filters}
        onFiltersChange={handleFiltersChange}
        search={search}
        onSearchChange={handleSearchChange}
        searchPlaceholder={t('users.filters.search')}
        pagination={{
          mode: 'cursor',
          pageSize,
          hasMore: data?.has_more || false,
          nextCursor: data?.next_cursor || null,
          onLoadMore: handleLoadMore,
          isLoadingMore: isLoadingMore || isFetching,
        }}
        visibleColumns={visibleColumns}
        onVisibleColumnsChange={handleVisibleColumnsChange}
        onRowClick={handleRowClick}
        getRowId={(user) => user.id}
        tableId={TABLE_ID}
      />

      {/* Create User Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={(open) => { setIsCreateOpen(open); if (!open) setShowCreatePassword(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('users.createDialog.title')}</DialogTitle>
            <DialogDescription>{t('users.createDialog.description')}</DialogDescription>
          </DialogHeader>
          <Form {...createForm}>
            <form onSubmit={createForm.handleSubmit(handleCreate)} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormField
                  control={createForm.control}
                  name="firstName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('users.createDialog.firstName')}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={createForm.control}
                  name="lastName"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t('users.createDialog.lastName')}</FormLabel>
                      <FormControl>
                        <Input {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
              <FormField
                control={createForm.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('users.createDialog.email')}</FormLabel>
                    <FormControl>
                      <Input type="email" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={createForm.control}
                name="password"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('users.createDialog.password')}</FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input type={showCreatePassword ? 'text' : 'password'} {...field} />
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                          onClick={() => setShowCreatePassword(!showCreatePassword)}
                        >
                          {showCreatePassword ? (
                            <EyeOff className="h-4 w-4 text-muted-foreground" />
                          ) : (
                            <Eye className="h-4 w-4 text-muted-foreground" />
                          )}
                        </Button>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={createForm.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{t('users.createDialog.phone')}</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {isSuperAdmin && (
                <FormField
                  control={createForm.control}
                  name="isAdmin"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2">
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                      <FormLabel className="!mt-0">{t('users.createDialog.isAdmin')}</FormLabel>
                    </FormItem>
                  )}
                />
              )}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                >
                  {t('users.createDialog.cancel')}
                </Button>
                <Button type="submit" disabled={isCreating}>
                  {isCreating ? t('users.createDialog.creating') : t('users.createDialog.create')}
                </Button>
              </div>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
      {/* Pending Invitations Section */}
      {canWrite && invitationsData && invitationsData.items.length > 0 && (
        <div className="rounded-lg border">
          <div className="p-4 border-b">
            <h3 className="text-base font-semibold">{t('invitations.title')}</h3>
          </div>
          <div className="divide-y">
            {invitationsData.items.map((inv: InvitationItem) => (
              <div key={inv.id} className="flex items-center justify-between p-4">
                <div className="space-y-0.5">
                  <p className="text-sm font-medium">{inv.email}</p>
                  <p className="text-xs text-muted-foreground">
                    {t('invitations.invitedBy')}: {inv.invited_by_name || inv.invited_by_user_id}
                    {' · '}
                    {t('invitations.expires')}: {formatDistanceToNow(new Date(inv.expires_at), { addSuffix: true })}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={revokingId === inv.id}
                  onClick={() => handleRevoke(inv.id)}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  {t('invitations.revokeButton')}
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Invite User Dialog */}
      <Dialog open={isInviteOpen} onOpenChange={setIsInviteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('invitations.inviteTitle')}</DialogTitle>
            <DialogDescription>{t('invitations.inviteDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {inviteError && (
              <p className="text-sm text-destructive">{inviteError}</p>
            )}
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('invitations.emailLabel')}</label>
              <Input
                type="email"
                placeholder={t('invitations.emailPlaceholder')}
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleInvite(); } }}
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => { setIsInviteOpen(false); setInviteEmail(''); setInviteError(null); }}>
              {t('users.createDialog.cancel')}
            </Button>
            <Button onClick={handleInvite} disabled={isInviting}>
              {isInviting ? t('invitations.sending') : t('invitations.sendInvite')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
