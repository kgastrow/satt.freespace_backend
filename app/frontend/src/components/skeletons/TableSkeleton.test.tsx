import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { TableSkeleton } from './TableSkeleton'

describe('TableSkeleton', () => {
  const mockColumns = [
    { key: 'id', header: 'ID' },
    { key: 'name', header: 'Name' },
    { key: 'email', header: 'Email' },
  ]

  it('renders table skeleton with default number of rows', () => {
    render(<TableSkeleton columns={mockColumns} />)

    // Check headers are rendered
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()

    // Check that 5 rows are rendered by default (5 rows * 3 columns = 15 skeleton cells)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(15)
  })

  it('renders custom number of rows when specified', () => {
    render(<TableSkeleton columns={mockColumns} rows={3} />)

    // Check that 3 rows are rendered (3 rows * 3 columns = 9 skeleton cells)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(9)
  })

  it('renders correct number of columns', () => {
    const twoColumns = [
      { key: 'id', header: 'ID' },
      { key: 'name', header: 'Name' },
    ]

    render(<TableSkeleton columns={twoColumns} rows={2} />)

    // Check headers
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()

    // Check that 2 rows with 2 columns = 4 skeleton cells
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(4)
  })

  it('applies custom className to columns', () => {
    const columnsWithClass = [
      { key: 'id', header: 'ID', className: 'w-20' },
      { key: 'name', header: 'Name', className: 'w-full' },
    ]

    render(<TableSkeleton columns={columnsWithClass} rows={1} />)

    // The table should render with the columns
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
  })

  it('renders table structure with border', () => {
    const { container } = render(<TableSkeleton columns={mockColumns} />)

    // Check that table container has border class
    const tableContainer = container.querySelector('.rounded-md.border')
    expect(tableContainer).toBeInTheDocument()
  })

  it('renders with single column', () => {
    const singleColumn = [{ key: 'id', header: 'ID' }]

    render(<TableSkeleton columns={singleColumn} rows={3} />)

    expect(screen.getByText('ID')).toBeInTheDocument()

    // Check that 3 rows with 1 column = 3 skeleton cells
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(3)
  })

  it('renders with many columns', () => {
    const manyColumns = [
      { key: 'col1', header: 'Column 1' },
      { key: 'col2', header: 'Column 2' },
      { key: 'col3', header: 'Column 3' },
      { key: 'col4', header: 'Column 4' },
      { key: 'col5', header: 'Column 5' },
    ]

    render(<TableSkeleton columns={manyColumns} rows={2} />)

    // Check all headers are rendered
    expect(screen.getByText('Column 1')).toBeInTheDocument()
    expect(screen.getByText('Column 5')).toBeInTheDocument()

    // Check that 2 rows with 5 columns = 10 skeleton cells
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(10)
  })

  it('renders with zero rows', () => {
    render(<TableSkeleton columns={mockColumns} rows={0} />)

    // Headers should still be rendered
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()

    // No skeleton cells should be rendered
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBe(0)
  })
})
