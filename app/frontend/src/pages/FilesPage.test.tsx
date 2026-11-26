import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@/test/utils'
import { FilesPage } from './FilesPage'
import { createAuthState, regularUser } from '@/test/fixtures'

// Mock the files API hooks
vi.mock('@/features/files/filesApi', async () => {
  const actual = await vi.importActual('@/features/files/filesApi')
  return {
    ...actual,
    useGetFilesQuery: vi.fn(() => ({
      data: { items: [], total: 0 },
      isLoading: false,
      error: null,
    })),
    useUploadFileMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
    useLazyGetDownloadUrlQuery: vi.fn(() => [vi.fn(), { isLoading: false }]),
    useDeleteFileMutation: vi.fn(() => [vi.fn(), { isLoading: false }]),
    useGetUserUsageQuery: vi.fn(() => ({
      data: {
        total_size_bytes: 0,
        user_quota_bytes: 1073741824,
        image_count: 0,
        video_count: 0,
        document_count: 0,
        other_count: 0,
      },
      isLoading: false,
    })),
  }
})

describe('FilesPage', () => {
  it('renders without crashing', () => {
    const { container } = render(<FilesPage />, {
      preloadedState: createAuthState(regularUser),
    })
    expect(container).toBeInTheDocument()
  })

  it('has tab list for category filters', () => {
    render(<FilesPage />, {
      preloadedState: createAuthState(regularUser),
    })
    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })
})
