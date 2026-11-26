import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@/test/utils'
import { ImpersonationHistorySection } from './ImpersonationHistorySection'
import type { MyImpersonationHistoryResponse, MyImpersonationHistoryItem } from '@/types/impersonation'

// Mock the API hook
const mockUseGetMyImpersonationHistoryQuery = vi.fn()

vi.mock('@/features/impersonation/impersonationApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/impersonation/impersonationApi')>()
  return {
    ...actual,
    useGetMyImpersonationHistoryQuery: () => mockUseGetMyImpersonationHistoryQuery(),
  }
})

const mockImpersonationSession: MyImpersonationHistoryItem = {
  id: 'session-1',
  created_time: '2024-01-15T10:00:00Z',
  ended_time: '2024-01-15T10:30:00Z',
  impersonator: {
    id: 'admin-user-id',
    email: 'admin@example.com',
    first_name: 'Admin',
    last_name: 'User',
  },
}

const mockSessionWithNullNames: MyImpersonationHistoryItem = {
  id: 'session-2',
  created_time: '2024-01-16T14:00:00Z',
  ended_time: '2024-01-16T14:15:00Z',
  impersonator: {
    id: 'admin-user-2',
    email: 'superadmin@example.com',
    first_name: null,
    last_name: null,
  },
}

const mockHistoryResponse: MyImpersonationHistoryResponse = {
  items: [mockImpersonationSession],
  total: 1,
  limit: 50,
  offset: 0,
}

const mockEmptyResponse: MyImpersonationHistoryResponse = {
  items: [],
  total: 0,
  limit: 50,
  offset: 0,
}

describe('ImpersonationHistorySection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('renders nothing when there is no impersonation history', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockEmptyResponse,
        isLoading: false,
      })

      const { container } = render(<ImpersonationHistorySection />)

      expect(container.firstChild).toBeNull()
    })

    it('renders nothing when data is undefined and not loading', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: undefined,
        isLoading: false,
      })

      const { container } = render(<ImpersonationHistorySection />)

      expect(container.firstChild).toBeNull()
    })

    it('renders the section when there is impersonation history', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('profile.impersonationHistory.title')).toBeInTheDocument()
      expect(screen.getByText('profile.impersonationHistory.description')).toBeInTheDocument()
    })

    it('shows loading state via DataTable when loading', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: undefined,
        isLoading: true,
      })

      render(<ImpersonationHistorySection />)

      // Loading state is rendered since we're in loading state
      // The component should render the Card because isLoading is true
      expect(screen.getByText('profile.impersonationHistory.title')).toBeInTheDocument()
    })
  })

  describe('Content Display', () => {
    it('displays impersonator name and email', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('Admin User')).toBeInTheDocument()
      expect(screen.getByText('admin@example.com')).toBeInTheDocument()
    })

    it('displays email when first_name and last_name are null', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: {
          ...mockHistoryResponse,
          items: [mockSessionWithNullNames],
        },
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      // Should show email as the name since first_name and last_name are null
      expect(screen.getAllByText('superadmin@example.com')).toHaveLength(2) // Name cell shows email as name, plus the email below
    })

    it('displays formatted start and end times', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      // Check that date/times are present (exact format depends on locale)
      const cells = screen.getAllByRole('cell')
      expect(cells.length).toBeGreaterThan(0)
    })

    it('displays duration correctly', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      // 30 minutes duration from 10:00 to 10:30
      expect(screen.getByText('30m')).toBeInTheDocument()
    })

    it('displays table headers', () => {
      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: mockHistoryResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('profile.impersonationHistory.columns.impersonator')).toBeInTheDocument()
      expect(screen.getByText('profile.impersonationHistory.columns.startTime')).toBeInTheDocument()
      expect(screen.getByText('profile.impersonationHistory.columns.endTime')).toBeInTheDocument()
      expect(screen.getByText('profile.impersonationHistory.columns.duration')).toBeInTheDocument()
    })
  })

  describe('Multiple Sessions', () => {
    it('displays multiple impersonation sessions', () => {
      const multipleSessionsResponse: MyImpersonationHistoryResponse = {
        items: [
          mockImpersonationSession,
          {
            id: 'session-3',
            created_time: '2024-01-14T09:00:00Z',
            ended_time: '2024-01-14T09:45:00Z',
            impersonator: {
              id: 'admin-user-3',
              email: 'other-admin@example.com',
              first_name: 'Other',
              last_name: 'Admin',
            },
          },
        ],
        total: 2,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: multipleSessionsResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('Admin User')).toBeInTheDocument()
      expect(screen.getByText('Other Admin')).toBeInTheDocument()
      expect(screen.getByText('admin@example.com')).toBeInTheDocument()
      expect(screen.getByText('other-admin@example.com')).toBeInTheDocument()
    })
  })

  describe('Duration Formatting', () => {
    it('formats seconds-only duration correctly', () => {
      const shortSessionResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-short',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T10:00:45Z',
            impersonator: mockImpersonationSession.impersonator,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: shortSessionResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('45s')).toBeInTheDocument()
    })

    it('formats hours duration correctly', () => {
      const longSessionResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-long',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T12:30:00Z',
            impersonator: mockImpersonationSession.impersonator,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: longSessionResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('2h 30m')).toBeInTheDocument()
    })

    it('formats exact hours duration correctly', () => {
      const exactHourResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-exact',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T12:00:00Z',
            impersonator: mockImpersonationSession.impersonator,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: exactHourResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('2h')).toBeInTheDocument()
    })

    it('formats minutes with seconds correctly', () => {
      const minutesWithSecondsResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-min-sec',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T10:05:30Z',
            impersonator: mockImpersonationSession.impersonator,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: minutesWithSecondsResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('5m 30s')).toBeInTheDocument()
    })
  })

  describe('Impersonator Name Formatting', () => {
    it('shows first name only when last name is null', () => {
      const firstNameOnlyResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-first-only',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T10:30:00Z',
            impersonator: {
              id: 'admin-id',
              email: 'admin@example.com',
              first_name: 'John',
              last_name: null,
            },
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      mockUseGetMyImpersonationHistoryQuery.mockReturnValue({
        data: firstNameOnlyResponse,
        isLoading: false,
      })

      render(<ImpersonationHistorySection />)

      expect(screen.getByText('John')).toBeInTheDocument()
    })
  })
})
