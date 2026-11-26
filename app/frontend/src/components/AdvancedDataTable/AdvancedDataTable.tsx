import { useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
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
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-react'
import { ColumnHeader } from './ColumnHeader'
import { ColumnVisibilityToggle } from './ColumnVisibilityToggle'
import { SearchInput } from './SearchInput'
import type { AdvancedDataTableProps, AdvancedColumn, OffsetPaginationState } from './types'

/**
 * Advanced data table with sorting, filtering, search, and column visibility
 */
export function AdvancedDataTable<T>({
  columns,
  data,
  isLoading = false,
  emptyMessage,
  sort,
  onSortChange,
  filters,
  onFiltersChange,
  search,
  onSearchChange,
  pagination,
  visibleColumns: externalVisibleColumns,
  onVisibleColumnsChange,
  onRowClick,
  getRowId,
  searchPlaceholder,
  virtualScroll,
}: AdvancedDataTableProps<T>) {
  const { t } = useTranslation()

  // Ref for virtual scrolling container
  const parentRef = useRef<HTMLDivElement>(null)

  // Virtual scrolling setup
  const isVirtualized = virtualScroll?.enabled && data.length > 0
  const rowVirtualizer = useVirtualizer({
    count: data.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => virtualScroll?.estimatedRowHeight ?? 48,
    overscan: virtualScroll?.overscan ?? 5,
    enabled: isVirtualized,
  })

  // Determine visible columns
  const defaultVisibleColumns = useMemo(() => {
    return columns
      .filter((col) => col.alwaysVisible || col.defaultVisible !== false)
      .map((col) => col.key)
  }, [columns])

  const visibleColumns = externalVisibleColumns || defaultVisibleColumns

  // Filter columns to only show visible ones
  const displayColumns = useMemo(() => {
    return columns.filter(
      (col) => col.alwaysVisible || visibleColumns.includes(col.key)
    )
  }, [columns, visibleColumns])

  // Check if any column is searchable
  const hasSearchableColumns = columns.some((col) => col.searchable)

  // Pagination helpers - defaults to offset mode for backwards compatibility
  const isCursorMode = pagination?.mode === 'cursor'
  const isOffsetMode = pagination && !isCursorMode
  const offsetPagination = isOffsetMode ? (pagination as OffsetPaginationState) : null
  const totalPages = offsetPagination
    ? Math.ceil(offsetPagination.total / offsetPagination.pageSize)
    : 0
  const defaultEmptyMessage = emptyMessage || t('table.noData')

  // Render skeleton for loading state
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          {hasSearchableColumns && onSearchChange && (
            <div className="h-9 w-64 bg-muted animate-pulse rounded-md" />
          )}
          <div className="ml-auto h-8 w-24 bg-muted animate-pulse rounded-md" />
        </div>
        <TableSkeleton columns={displayColumns as AdvancedColumn<unknown>[]} rows={5} />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-4">
        {hasSearchableColumns && onSearchChange && (
          <SearchInput
            value={search || ''}
            onChange={onSearchChange}
            placeholder={searchPlaceholder}
          />
        )}
        {onVisibleColumnsChange && (
          <ColumnVisibilityToggle
            columns={columns}
            visibleColumns={visibleColumns}
            onVisibleColumnsChange={onVisibleColumnsChange}
          />
        )}
      </div>

      {/* Table */}
      <div className="rounded-md border">
        {isVirtualized ? (
          // Virtualized table for large datasets
          <div
            ref={parentRef}
            className="overflow-auto"
            style={{ height: virtualScroll?.height ?? 400 }}
          >
            <Table>
              <TableHeader className="sticky top-0 z-10 bg-background">
                <TableRow>
                  {displayColumns.map((column) => (
                    <TableHead key={column.key} className={cn(column.className, column.hiddenOnMobile && 'hidden md:table-cell')}>
                      <ColumnHeader
                        column={column}
                        sort={sort}
                        onSortChange={onSortChange}
                        filters={filters}
                        onFiltersChange={onFiltersChange}
                      />
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={displayColumns.length}
                      className="h-24 text-center text-muted-foreground"
                    >
                      {defaultEmptyMessage}
                    </TableCell>
                  </TableRow>
                ) : (
                  <>
                    {/* Spacer for rows before visible area */}
                    {rowVirtualizer.getVirtualItems()[0]?.start > 0 && (
                      <tr style={{ height: rowVirtualizer.getVirtualItems()[0].start }} />
                    )}
                    {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                      const item = data[virtualRow.index]
                      const rowId = getRowId ? getRowId(item) : String(virtualRow.index)
                      const isClickable = !!onRowClick

                      return (
                        <TableRow
                          key={rowId}
                          data-index={virtualRow.index}
                          className={cn(isClickable && 'cursor-pointer hover:bg-muted/50')}
                          onClick={isClickable ? () => onRowClick(item) : undefined}
                          style={{ height: virtualRow.size }}
                        >
                          {displayColumns.map((column) => (
                            <TableCell key={column.key} className={cn(column.className, column.hiddenOnMobile && 'hidden md:table-cell')}>
                              {column.cell(item)}
                            </TableCell>
                          ))}
                        </TableRow>
                      )
                    })}
                    {/* Spacer for rows after visible area */}
                    {rowVirtualizer.getVirtualItems().length > 0 && (
                      <tr
                        style={{
                          height:
                            rowVirtualizer.getTotalSize() -
                            (rowVirtualizer.getVirtualItems()[
                              rowVirtualizer.getVirtualItems().length - 1
                            ]?.end ?? 0),
                        }}
                      />
                    )}
                  </>
                )}
              </TableBody>
            </Table>
          </div>
        ) : (
          // Standard table rendering
          <Table>
            <TableHeader>
              <TableRow>
                {displayColumns.map((column) => (
                  <TableHead key={column.key} className={cn(column.className, column.hiddenOnMobile && 'hidden md:table-cell')}>
                    <ColumnHeader
                      column={column}
                      sort={sort}
                      onSortChange={onSortChange}
                      filters={filters}
                      onFiltersChange={onFiltersChange}
                    />
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={displayColumns.length}
                    className="h-24 text-center text-muted-foreground"
                  >
                    {defaultEmptyMessage}
                  </TableCell>
                </TableRow>
              ) : (
                data.map((item, index) => {
                  const rowId = getRowId ? getRowId(item) : String(index)
                  const isClickable = !!onRowClick

                  return (
                    <TableRow
                      key={rowId}
                      className={cn(isClickable && 'cursor-pointer hover:bg-muted/50')}
                      onClick={isClickable ? () => onRowClick(item) : undefined}
                    >
                      {displayColumns.map((column) => (
                        <TableCell key={column.key} className={cn(column.className, column.hiddenOnMobile && 'hidden md:table-cell')}>
                          {column.cell(item)}
                        </TableCell>
                      ))}
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </Table>
        )}
      </div>

      {/* Offset Pagination - page numbers */}
      {offsetPagination && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            {t('common:table.pagination.showing')}{' '}
            {Math.min((offsetPagination.page - 1) * offsetPagination.pageSize + 1, offsetPagination.total)}-
            {Math.min(offsetPagination.page * offsetPagination.pageSize, offsetPagination.total)}{' '}
            {t('common:table.pagination.of')} {offsetPagination.total}
          </div>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() =>
                    offsetPagination.page > 1 &&
                    offsetPagination.onPageChange(offsetPagination.page - 1)
                  }
                  className={
                    offsetPagination.page <= 1
                      ? 'pointer-events-none opacity-50'
                      : 'cursor-pointer'
                  }
                />
              </PaginationItem>

              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let pageNum: number
                if (totalPages <= 5) {
                  pageNum = i + 1
                } else if (offsetPagination.page <= 3) {
                  pageNum = i + 1
                } else if (offsetPagination.page >= totalPages - 2) {
                  pageNum = totalPages - 4 + i
                } else {
                  pageNum = offsetPagination.page - 2 + i
                }

                return (
                  <PaginationItem key={pageNum}>
                    <PaginationLink
                      onClick={() => offsetPagination.onPageChange(pageNum)}
                      isActive={offsetPagination.page === pageNum}
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
                    offsetPagination.page < totalPages &&
                    offsetPagination.onPageChange(offsetPagination.page + 1)
                  }
                  className={
                    offsetPagination.page >= totalPages
                      ? 'pointer-events-none opacity-50'
                      : 'cursor-pointer'
                  }
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}

      {/* Cursor Pagination - load more button */}
      {isCursorMode && pagination.hasMore && (
        <div className="flex justify-center pt-4">
          <Button
            variant="outline"
            onClick={pagination.onLoadMore}
            disabled={pagination.isLoadingMore}
          >
            {pagination.isLoadingMore ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('common:table.pagination.loading')}
              </>
            ) : (
              t('common:table.pagination.loadMore')
            )}
          </Button>
        </div>
      )}
    </div>
  )
}
