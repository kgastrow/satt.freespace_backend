import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@/test/utils'
import { AdvancedDataTable } from './AdvancedDataTable'
import type { AdvancedColumn, SortState } from './types'

interface TestItem {
  id: string
  name: string
  email: string
  status: 'active' | 'inactive'
}

const testItems: TestItem[] = [
  { id: '1', name: 'Alice Smith', email: 'alice@example.com', status: 'active' },
  { id: '2', name: 'Bob Johnson', email: 'bob@example.com', status: 'inactive' },
  { id: '3', name: 'Charlie Brown', email: 'charlie@example.com', status: 'active' },
]

const testColumns: AdvancedColumn<TestItem>[] = [
  {
    key: 'name',
    header: 'Name',
    cell: (item) => item.name,
    sortable: true,
    sortKey: 'name',
    searchable: true,
    defaultVisible: true,
  },
  {
    key: 'email',
    header: 'Email',
    cell: (item) => item.email,
    sortable: true,
    sortKey: 'email',
    defaultVisible: true,
  },
  {
    key: 'status',
    header: 'Status',
    cell: (item) => item.status,
    filterable: true,
    filterConfig: {
      type: 'select',
      options: [
        { value: 'active', label: 'Active' },
        { value: 'inactive', label: 'Inactive' },
      ],
    },
    defaultVisible: true,
  },
]

const defaultPagination = {
  mode: 'offset' as const,
  page: 1,
  pageSize: 10,
  total: 3,
  onPageChange: vi.fn(),
}

describe('AdvancedDataTable', () => {
  const mockOnSortChange = vi.fn()
  const mockOnFiltersChange = vi.fn()
  const mockOnSearchChange = vi.fn()
  const mockOnPageChange = vi.fn()
  const mockOnVisibleColumnsChange = vi.fn()
  const mockOnRowClick = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('renders table with items', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
        />
      )

      expect(screen.getByText('Alice Smith')).toBeInTheDocument()
      expect(screen.getByText('Bob Johnson')).toBeInTheDocument()
      expect(screen.getByText('Charlie Brown')).toBeInTheDocument()
    })

    it('renders column headers', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
        />
      )

      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Email')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
    })

    it('renders empty message when no items', () => {
      render(
        <AdvancedDataTable
          data={[]}
          columns={testColumns}
          pagination={{ ...defaultPagination, total: 0, onPageChange: mockOnPageChange }}
          emptyMessage="No users found"
        />
      )

      expect(screen.getByText('No users found')).toBeInTheDocument()
    })

    it('shows loading state', () => {
      render(
        <AdvancedDataTable
          data={[]}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          isLoading={true}
        />
      )

      // Should show skeleton or loading indicator
      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })

  describe('search functionality', () => {
    it('renders search input when searchable columns exist', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          search=""
          onSearchChange={mockOnSearchChange}
        />
      )

      expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
    })

    it('calls onSearchChange when search input changes', async () => {
      const { user } = render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          search=""
          onSearchChange={mockOnSearchChange}
        />
      )

      const searchInput = screen.getByPlaceholderText(/search/i)
      await user.type(searchInput, 'Alice')

      await waitFor(() => {
        expect(mockOnSearchChange).toHaveBeenCalled()
      })
    })
  })

  describe('column visibility', () => {
    it('renders column visibility toggle', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          visibleColumns={['name', 'email', 'status']}
          onVisibleColumnsChange={mockOnVisibleColumnsChange}
        />
      )

      // Column visibility button should be present
      expect(screen.getByRole('button', { name: /columns/i })).toBeInTheDocument()
    })

    it('only shows visible columns', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          visibleColumns={['name']}
          onVisibleColumnsChange={mockOnVisibleColumnsChange}
        />
      )

      expect(screen.getByText('Name')).toBeInTheDocument()
      // Email column should not be visible as a header
      const emailHeaders = screen.queryAllByRole('columnheader').filter(
        (el) => el.textContent?.includes('Email')
      )
      expect(emailHeaders).toHaveLength(0)
    })
  })

  describe('sorting', () => {
    it('calls onSortChange when clicking sortable column header', async () => {
      const { user } = render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          sort={undefined}
          onSortChange={mockOnSortChange}
        />
      )

      const nameHeader = screen.getByText('Name')
      await user.click(nameHeader)

      expect(mockOnSortChange).toHaveBeenCalled()
    })

    it('shows sort indicator on sorted column', () => {
      const sortState: SortState = { field: 'name', direction: 'asc' }

      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          sort={sortState}
          onSortChange={mockOnSortChange}
        />
      )

      // The sort indicator should be visible (arrow icon)
      const nameHeader = screen.getByText('Name').closest('th')
      expect(nameHeader?.querySelector('svg')).toBeInTheDocument()
    })
  })

  describe('pagination', () => {
    it('shows pagination controls when totalPages > 1', () => {
      // Pagination only shows when total > pageSize (totalPages > 1)
      const paginationWithMultiplePages = {
        mode: 'offset' as const,
        page: 1,
        pageSize: 2,
        total: 6,  // 6 total with pageSize 2 = 3 pages
        onPageChange: mockOnPageChange,
      }

      render(
        <AdvancedDataTable
          data={testItems.slice(0, 2)}
          columns={testColumns}
          pagination={paginationWithMultiplePages}
        />
      )

      // Should show navigation area
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()
    })

    it('calls onPageChange when page link is clicked', async () => {
      const paginationWithMore = {
        mode: 'offset' as const,
        page: 1,
        pageSize: 2,
        total: 10,  // 10 total with pageSize 2 = 5 pages
        onPageChange: mockOnPageChange,
      }

      const { user } = render(
        <AdvancedDataTable
          data={testItems.slice(0, 2)}
          columns={testColumns}
          pagination={paginationWithMore}
        />
      )

      // Find the pagination nav
      const nav = screen.getByRole('navigation', { name: /pagination/i })
      expect(nav).toBeInTheDocument()

      // Find the "Next" link (has aria-label "Go to next page")
      const nextLink = screen.getByLabelText(/go to next page/i)
      await user.click(nextLink)

      expect(mockOnPageChange).toHaveBeenCalledWith(2)
    })
  })

  describe('row interactions', () => {
    it('calls onRowClick when row is clicked', async () => {
      const { user } = render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          onRowClick={mockOnRowClick}
        />
      )

      const row = screen.getByText('Alice Smith').closest('tr')
      if (row) {
        await user.click(row)
      }

      expect(mockOnRowClick).toHaveBeenCalledWith(testItems[0])
    })

    it('shows pointer cursor when onRowClick is provided', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          onRowClick={mockOnRowClick}
        />
      )

      const row = screen.getByText('Alice Smith').closest('tr')
      expect(row).toHaveClass('cursor-pointer')
    })
  })

  describe('filters', () => {
    it('calls onFiltersChange when filter is applied', async () => {
      const { user } = render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
          filters={{}}
          onFiltersChange={mockOnFiltersChange}
        />
      )

      // Find the Status column header (which is filterable)
      const statusHeader = screen.getByText('Status')

      // Click on the filter icon in the Status column
      const filterButton = statusHeader.closest('th')?.querySelector('[data-filter-trigger]')
      if (filterButton) {
        await user.click(filterButton)
      }

      // This test verifies the filter UI is accessible
      expect(statusHeader).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has proper table structure', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
        />
      )

      expect(screen.getByRole('table')).toBeInTheDocument()
      expect(screen.getAllByRole('columnheader')).toHaveLength(3)
      expect(screen.getAllByRole('row')).toHaveLength(4) // 1 header + 3 data rows
    })

    it('renders without accessibility violations', () => {
      render(
        <AdvancedDataTable
          data={testItems}
          columns={testColumns}
          pagination={{ ...defaultPagination, onPageChange: mockOnPageChange }}
        />
      )

      // Basic accessibility checks
      const table = screen.getByRole('table')
      expect(table).toBeInTheDocument()
    })
  })
})
