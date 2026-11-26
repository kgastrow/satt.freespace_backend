import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import { TableSkeleton } from '@/components/skeletons'
import { Checkbox } from '@/components/ui/checkbox'
import { useTranslation } from 'react-i18next'

export interface Column<T> {
  key: string
  header: string
  cell: (item: T) => React.ReactNode
  className?: string
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  isLoading?: boolean
  emptyMessage?: string
  pagination?: {
    page: number
    pageSize: number
    total: number
    onPageChange: (page: number) => void
  }
  // Row selection props
  selectedRows?: T[]
  onSelectionChange?: (selectedRows: T[]) => void
  getRowId?: (row: T) => string
}

/**
 * Reusable data table component with pagination support
 */
export function DataTable<T>({
  columns,
  data,
  isLoading = false,
  emptyMessage,
  pagination,
  selectedRows = [],
  onSelectionChange,
  getRowId,
}: DataTableProps<T>) {
  const { t } = useTranslation()
  const totalPages = pagination
    ? Math.ceil(pagination.total / pagination.pageSize)
    : 0
  const defaultEmptyMessage = emptyMessage || t('table.noData')

  // Selection support
  const isSelectable = !!onSelectionChange && !!getRowId
  const selectedIds = new Set(selectedRows.map(getRowId || (() => '')))

  const handleSelectAll = (checked: boolean) => {
    if (!onSelectionChange || !getRowId) return
    onSelectionChange(checked ? [...data] : [])
  }

  const handleSelectRow = (row: T, checked: boolean) => {
    if (!onSelectionChange || !getRowId) return
    const rowId = getRowId(row)
    if (checked) {
      onSelectionChange([...selectedRows, row])
    } else {
      onSelectionChange(selectedRows.filter(r => getRowId(r) !== rowId))
    }
  }

  const isAllSelected = isSelectable && data.length > 0 && data.every(row => selectedIds.has(getRowId(row)))
  const isSomeSelected = isSelectable && selectedRows.length > 0 && !isAllSelected

  if (isLoading) {
    return <TableSkeleton columns={columns} rows={5} />
  }

  if (data.length === 0) {
    return (
      <div className="rounded-md border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {isSelectable && (
                <TableHead className="w-12">
                  <Checkbox
                    checked={false}
                    disabled
                    aria-label="Select all"
                  />
                </TableHead>
              )}
              {columns.map((column) => (
                <TableHead key={column.key} className={column.className}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell
                colSpan={columns.length + (isSelectable ? 1 : 0)}
                className="h-24 text-center text-muted-foreground"
              >
                {defaultEmptyMessage}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {isSelectable && (
                <TableHead className="w-12">
                  <Checkbox
                    checked={isAllSelected}
                    onCheckedChange={handleSelectAll}
                    aria-label="Select all"
                    className={isSomeSelected ? 'data-[state=checked]:bg-muted' : ''}
                  />
                </TableHead>
              )}
              {columns.map((column) => (
                <TableHead key={column.key} className={column.className}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((item, index) => {
              const rowId = getRowId ? getRowId(item) : String(index)
              const isSelected = isSelectable && selectedIds.has(rowId)

              return (
                <TableRow key={index}>
                  {isSelectable && (
                    <TableCell className="w-12">
                      <Checkbox
                        checked={isSelected}
                        onCheckedChange={(checked) => handleSelectRow(item, !!checked)}
                        aria-label={`Select row ${index + 1}`}
                      />
                    </TableCell>
                  )}
                  {columns.map((column) => (
                    <TableCell key={column.key} className={column.className}>
                      {column.cell(item)}
                    </TableCell>
                  ))}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>

      {pagination && totalPages > 1 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-muted-foreground">
            {t('common:table.pagination.showing')} {Math.min((pagination.page - 1) * pagination.pageSize + 1, pagination.total)}-{Math.min(pagination.page * pagination.pageSize, pagination.total)} {t('common:table.pagination.of')} {pagination.total}
          </div>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() =>
                    pagination.page > 1 &&
                    pagination.onPageChange(pagination.page - 1)
                  }
                  className={
                    pagination.page <= 1
                      ? 'pointer-events-none opacity-50'
                      : 'cursor-pointer'
                  }
                />
              </PaginationItem>

            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              let pageNum: number
              if (totalPages <= 5) {
                pageNum = i + 1
              } else if (pagination.page <= 3) {
                pageNum = i + 1
              } else if (pagination.page >= totalPages - 2) {
                pageNum = totalPages - 4 + i
              } else {
                pageNum = pagination.page - 2 + i
              }

              return (
                <PaginationItem key={pageNum}>
                  <PaginationLink
                    onClick={() => pagination.onPageChange(pageNum)}
                    isActive={pagination.page === pageNum}
                    className="cursor-pointer"
                  >
                    {pageNum}
                  </PaginationLink>
                </PaginationItem>
              )
            })}

            <PaginationItem>
              <PaginationNext
                onClick={() =>
                  pagination.page < totalPages &&
                  pagination.onPageChange(pagination.page + 1)
                }
                className={
                  pagination.page >= totalPages
                    ? 'pointer-events-none opacity-50'
                    : 'cursor-pointer'
                }
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
        </div>
      )}
    </div>
  )
}
