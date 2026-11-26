import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { UserDetailPage } from './UserDetailPage'
import * as usersApi from '@/features/users/usersApi'

// Mock react-router-dom
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ id: 'test-user-id' }),
    useNavigate: () => vi.fn(),
  }
})

// Mock the usersApi hooks
vi.mock('@/features/users/usersApi', () => ({
  useGetUserDetailQuery: vi.fn(),
  useSuspendUserMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useUnsuspendUserMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useDeleteUserMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useUpdateUserMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useInvalidateUserSessionMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useUpdateUserNotificationPreferencesMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useAssignUserTypeMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useRevokeUserTypeMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useResetUserTypeOnboardingMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useAdminDisable2FAMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useAdminSendPasswordResetMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useGetUserLoginHistoryQuery: vi.fn(() => ({ data: { items: [], total: 0 }, isLoading: false })),
}))

// Mock rolesApi hooks
vi.mock('@/features/roles/rolesApi', () => ({
  useGetRolesQuery: vi.fn(() => ({
    data: {
      items: [{ id: 'role-1', name: 'Member', description: 'Basic member role' }],
      total: 1,
      limit: 50,
      offset: 0,
    },
    isLoading: false,
  })),
  useGetUserRolesQuery: vi.fn(() => ({
    data: { items: [{ role_id: 'role-1', user_id: 'test-user-id' }], total: 1, limit: 50, offset: 0 },
    isLoading: false,
  })),
  useAssignRoleMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
  useRevokeRoleMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
}))

// Mock usePermission hook
vi.mock('@/hooks/usePermission', () => ({
  usePermission: () => ({
    canRead: true,
    canWrite: true,
    canDelete: true,
    hasPermission: () => true,
  }),
}))

// Mock useAuth hook
vi.mock('@/hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 'admin-user-id' },
    isSuperAdmin: true,
  }),
}))

const mockUser: usersApi.UserFullDetail = {
  id: 'test-user-id',
  email: 'test@example.com',
  email_verified: true,
  email_deliverable: true,
  phone: '+1234567890',
  phone_verified: true,
  first_name: 'Test',
  last_name: 'User',
  is_admin: false,
  created_time: '2024-01-01T00:00:00Z',
  updated_time: '2024-01-15T00:00:00Z',
  created_via: 'EMAIL',
  avatar_url: null,
  suspension_status: 'active',
  suspension_info: null,
  roles: [{ id: 'role-1', name: 'Member' }],
  user_types: [
    {
      id: 'ut-1',
      name: 'Standard User',
      code: 'standard',
      onboarding_status: 'completed',
      onboarded_at: '2024-01-02T00:00:00Z',
    },
  ],
  sessions: [
    {
      id: 'session-1',
      created_time: '2024-01-10T00:00:00Z',
      expires_at: '2024-02-10T00:00:00Z',
      auth_provider: 'email',
      ip_address: '192.168.1.1',
      user_agent: 'Mozilla/5.0 Chrome',
      city: 'New York',
      country: 'USA',
      country_code: 'US',
      is_current: false,
    },
  ],
  two_factor: {
    is_enabled: false,
    verified_at: null,
    backup_codes_remaining: 0,
  },
  identity_providers: [],
  file_usage: {
    total_files: 10,
    total_size_bytes: 1024000,
    image_count: 5,
    image_size_bytes: 512000,
    video_count: 2,
    video_size_bytes: 256000,
    document_count: 2,
    document_size_bytes: 128000,
    audio_count: 1,
    audio_size_bytes: 64000,
    other_count: 0,
    other_size_bytes: 0,
  },
  feedback: [],
  data_exports: [],
  impersonation_history: [],
  notification_preferences: {
    email_enabled: true,
    sms_enabled: false,
    push_enabled: true,
    in_app_enabled: true,
  },
}

describe('UserDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('loading state', () => {
    it('shows loading skeleton when data is loading', () => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)

      render(<UserDetailPage />)

      // Should show back button even while loading
      expect(screen.getByText(/back/i)).toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('shows error message when user not found', () => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: { status: 404 },
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)

      render(<UserDetailPage />)

      // Translation key: users.detail.notFound - multiple elements may match
      expect(screen.getAllByText(/notFound/).length).toBeGreaterThan(0)
    })
  })

  describe('successful render', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('displays user name and email', () => {
      render(<UserDetailPage />)

      expect(screen.getByText('Test User')).toBeInTheDocument()
      // Email may appear multiple times, so check that at least one exists
      expect(screen.getAllByText('test@example.com').length).toBeGreaterThan(0)
    })

    it('shows back to users link', () => {
      render(<UserDetailPage />)

      // Look for the back link in the navigation area
      expect(screen.getAllByText(/back/i).length).toBeGreaterThan(0)
    })

    it('displays user status badge', () => {
      render(<UserDetailPage />)

      // Active status
      expect(screen.getByText(/active/i)).toBeInTheDocument()
    })

    it('renders all tabs', () => {
      render(<UserDetailPage />)

      expect(screen.getByText(/overview/i)).toBeInTheDocument()
      expect(screen.getByText(/sessions/i)).toBeInTheDocument()
      expect(screen.getByText(/security/i)).toBeInTheDocument()
      expect(screen.getByText(/files/i)).toBeInTheDocument()
      expect(screen.getByText(/activity/i)).toBeInTheDocument()
    })

    it('shows overview tab by default', () => {
      render(<UserDetailPage />)

      // Overview section content should be visible (translation key: users.detail.sections.basicInfo)
      expect(screen.getByText(/basicInfo/i)).toBeInTheDocument()
    })

    it('shows user roles', () => {
      render(<UserDetailPage />)

      expect(screen.getByText('Member')).toBeInTheDocument()
    })

    it('shows user types with onboarding status', () => {
      render(<UserDetailPage />)

      expect(screen.getByText('Standard User')).toBeInTheDocument()
      expect(screen.getByText(/completed/i)).toBeInTheDocument()
    })
  })

  describe('tabs navigation', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('switches to sessions tab when clicked', async () => {
      const { user } = render(<UserDetailPage />)

      const sessionsTab = screen.getByRole('tab', { name: /sessions/i })
      await user.click(sessionsTab)

      await waitFor(() => {
        // Translation mock returns keys, so we look for the key pattern
        expect(screen.getByText(/lastActive/i)).toBeInTheDocument()
      })
    })

    it('switches to security tab when clicked', async () => {
      const { user } = render(<UserDetailPage />)

      const securityTab = screen.getByRole('tab', { name: /security/i })
      await user.click(securityTab)

      await waitFor(() => {
        // Translation mock returns keys like 'users.detail.sections.twoFactor'
        // Multiple elements may contain twoFactor, so check at least one exists
        expect(screen.getAllByText(/twoFactor/i).length).toBeGreaterThan(0)
      })
    })

    it('switches to files tab when clicked', async () => {
      const { user } = render(<UserDetailPage />)

      const filesTab = screen.getByRole('tab', { name: /files/i })
      await user.click(filesTab)

      await waitFor(() => {
        // Files section shows storage info
        expect(screen.getByText(/storageUsage|totalFiles/i)).toBeInTheDocument()
      })
    })

    it('switches to activity tab when clicked', async () => {
      const { user } = render(<UserDetailPage />)

      const activityTab = screen.getByRole('tab', { name: /activity/i })
      await user.click(activityTab)

      await waitFor(() => {
        // Mock user has empty feedback/exports/impersonation, so noActivity message shows
        // Translation key: users.detail.noActivity - multiple elements may match
        expect(screen.getAllByText(/noActivity/).length).toBeGreaterThan(0)
      })
    })
  })

  describe('suspended user', () => {
    it('shows suspension info when user is suspended', () => {
      const suspendedUser: usersApi.UserFullDetail = {
        ...mockUser,
        suspension_status: 'suspended',
        suspension_info: {
          suspended_time: '2024-01-15T00:00:00Z',
          suspended_by: 'admin-id',
          suspended_by_name: 'Admin User',
          suspension_reason: 'Policy violation',
        },
      }

      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: suspendedUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)

      render(<UserDetailPage />)

      // Multiple elements may show "suspended", so check at least one exists
      expect(screen.getAllByText(/suspended/i).length).toBeGreaterThan(0)
      expect(screen.getByText(/policy violation/i)).toBeInTheDocument()
    })
  })

  describe('action buttons', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('shows suspend button for active user', () => {
      render(<UserDetailPage />)

      expect(screen.getByRole('button', { name: /suspend/i })).toBeInTheDocument()
    })

    it('shows unsuspend button for suspended user', () => {
      const suspendedUser: usersApi.UserFullDetail = {
        ...mockUser,
        suspension_status: 'suspended',
      }

      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: suspendedUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)

      render(<UserDetailPage />)

      expect(screen.getByRole('button', { name: /unsuspend/i })).toBeInTheDocument()
    })

    it('shows delete button', () => {
      render(<UserDetailPage />)

      expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument()
    })
  })

  describe('sessions section', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('shows session details', async () => {
      const { user } = render(<UserDetailPage />)

      const sessionsTab = screen.getByRole('tab', { name: /sessions/i })
      await user.click(sessionsTab)

      await waitFor(() => {
        expect(screen.getByText('Chrome')).toBeInTheDocument()
        expect(screen.getByText(/new york/i)).toBeInTheDocument()
      })
    })

    it('shows revoke session button', async () => {
      const { user } = render(<UserDetailPage />)

      const sessionsTab = screen.getByRole('tab', { name: /sessions/i })
      await user.click(sessionsTab)

      await waitFor(() => {
        // Translation key: users.detail.invalidateSession
        expect(screen.getByRole('button', { name: /invalidateSession/i })).toBeInTheDocument()
      })
    })
  })

  describe('2FA section', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('shows 2FA disabled status', async () => {
      const { user } = render(<UserDetailPage />)

      const securityTab = screen.getByRole('tab', { name: /security/i })
      await user.click(securityTab)

      await waitFor(() => {
        expect(screen.getByText(/disabled/i)).toBeInTheDocument()
      })
    })

    it('shows 2FA enabled status when enabled', async () => {
      const userWith2FA: usersApi.UserFullDetail = {
        ...mockUser,
        two_factor: {
          is_enabled: true,
          verified_at: '2024-01-05T00:00:00Z',
          backup_codes_remaining: 8,
        },
      }

      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: userWith2FA,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)

      const { user } = render(<UserDetailPage />)

      const securityTab = screen.getByRole('tab', { name: /security/i })
      await user.click(securityTab)

      await waitFor(() => {
        // Multiple elements may show "enabled", check at least one exists
        expect(screen.getAllByText(/enabled/i).length).toBeGreaterThan(0)
        // Backup codes - text contains "8" in context of remaining codes
        expect(screen.getAllByText(/8/).length).toBeGreaterThan(0)
      })
    })
  })

  describe('files section', () => {
    beforeEach(() => {
      vi.mocked(usersApi.useGetUserDetailQuery).mockReturnValue({
        data: mockUser,
        isLoading: false,
        error: undefined,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof usersApi.useGetUserDetailQuery>)
    })

    it('shows storage usage', async () => {
      const { user } = render(<UserDetailPage />)

      const filesTab = screen.getByRole('tab', { name: /files/i })
      await user.click(filesTab)

      await waitFor(() => {
        // Should show file counts and sizes - multiple elements may have "10"
        expect(screen.getAllByText(/10/).length).toBeGreaterThan(0)
      })
    })

    it('shows file type breakdown', async () => {
      const { user } = render(<UserDetailPage />)

      const filesTab = screen.getByRole('tab', { name: /files/i })
      await user.click(filesTab)

      await waitFor(() => {
        expect(screen.getByText(/images/i)).toBeInTheDocument()
        expect(screen.getByText(/videos/i)).toBeInTheDocument()
        expect(screen.getByText(/documents/i)).toBeInTheDocument()
      })
    })
  })
})
