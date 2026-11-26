/**
 * Types for AdvancedDataTable component
 */

export type FilterType = 'select' | 'multiselect' | 'boolean'

export interface FilterOption {
  value: string
  label: string
}

export interface FilterConfig {
  type: FilterType
  options?: FilterOption[]
}

export interface AdvancedColumn<T> {
  /** Unique key for the column */
  key: string
  /** Display header text */
  header: string
  /** Function to render cell content */
  cell: (item: T) => React.ReactNode
  /** Optional CSS class for the column */
  className?: string
  /** Whether column is sortable (default: false) */
  sortable?: boolean
  /** Key to use for sorting (defaults to column key) */
  sortKey?: string
  /** Whether column is filterable (default: false) */
  filterable?: boolean
  /** Filter configuration if filterable */
  filterConfig?: FilterConfig
  /** Whether column is searchable (default: false) */
  searchable?: boolean
  /** Whether column is visible by default (default: true) */
  defaultVisible?: boolean
  /** Whether column is always visible and cannot be hidden (default: false) */
  alwaysVisible?: boolean
  /** Whether column is hidden on mobile breakpoints (default: false) */
  hiddenOnMobile?: boolean
}

export interface SortState {
  field: string
  direction: 'asc' | 'desc'
}

export interface FilterState {
  [key: string]: string | string[] | boolean | undefined
}

/** Offset-based pagination (default) - supports page jumping and total count */
export interface OffsetPaginationState {
  mode?: 'offset'  // Optional, defaults to 'offset' for backwards compatibility
  page: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
}

/** Cursor-based pagination - for large datasets and real-time data */
export interface CursorPaginationState {
  mode: 'cursor'  // Required to opt-in to cursor mode
  pageSize: number
  hasMore: boolean
  nextCursor: string | null
  onLoadMore: () => void
  isLoadingMore?: boolean
}

export type PaginationState = OffsetPaginationState | CursorPaginationState

/** Configuration for virtual scrolling */
export interface VirtualScrollConfig {
  /** Enable virtual scrolling (default: false) */
  enabled: boolean
  /** Fixed height for the scrollable container in pixels */
  height: number
  /** Estimated row height in pixels (default: 48) */
  estimatedRowHeight?: number
  /** Number of rows to render outside the visible area (default: 5) */
  overscan?: number
}

export interface AdvancedDataTableProps<T> {
  /** Column definitions */
  columns: AdvancedColumn<T>[]
  /** Data to display */
  data: T[]
  /** Whether data is loading */
  isLoading?: boolean
  /** Message to show when data is empty */
  emptyMessage?: string
  /** Current sort state */
  sort?: SortState
  /** Callback when sort changes */
  onSortChange?: (sort: SortState | undefined) => void
  /** Current filter state */
  filters?: FilterState
  /** Callback when filters change */
  onFiltersChange?: (filters: FilterState) => void
  /** Current search query */
  search?: string
  /** Callback when search changes */
  onSearchChange?: (search: string) => void
  /** Pagination configuration - supports offset (default) or cursor mode */
  pagination?: PaginationState
  /** Currently visible columns (array of column keys) */
  visibleColumns?: string[]
  /** Callback when column visibility changes */
  onVisibleColumnsChange?: (columns: string[]) => void
  /** Unique ID for table (used for storing preferences) */
  tableId?: string
  /** Callback when row is clicked */
  onRowClick?: (item: T) => void
  /** Function to get unique ID for a row */
  getRowId?: (item: T) => string
  /** Custom search input placeholder text */
  searchPlaceholder?: string
  /** Virtual scrolling configuration for large datasets */
  virtualScroll?: VirtualScrollConfig
}
