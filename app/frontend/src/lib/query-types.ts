/**
 * Query DSL Types for standardized filtering, sorting, and pagination.
 *
 * These types provide a consistent interface for working with list endpoints
 * that follow the Query DSL pattern.
 */

/**
 * Standard list response structure from backend.
 * All list endpoints should return this structure.
 */
export interface ListResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

/**
 * Supported filter operators.
 * Maps to backend FilterOperator enum.
 */
export type FilterOperator =
  | 'eq'
  | 'ne'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'in'
  | 'contains'
  | 'is_null'

/**
 * A single filter specification.
 */
export interface FilterSpec {
  /** Field name to filter on */
  field: string
  /** Filter operator (defaults to 'eq' if omitted) */
  operator?: FilterOperator
  /** Filter value - string, array for 'in' operator, or boolean for 'is_null' */
  value: string | string[] | boolean
}

/**
 * Standard pagination parameters.
 */
export interface PaginationParams {
  /** Maximum number of items to return (1-100, default 50) */
  limit?: number
  /** Number of items to skip (default 0) */
  offset?: number
}

/**
 * Sort specification.
 * Format: "field:direction" or "field1:dir1,field2:dir2"
 */
export type SortDirection = 'asc' | 'desc'

export interface SortSpec {
  field: string
  direction: SortDirection
}

/**
 * Complete query parameters for list endpoints.
 */
export interface QueryParams {
  /** Array of filter specifications */
  filters?: FilterSpec[]
  /** Sort specification (e.g., "created_at:desc") */
  sort?: string
  /** Pagination parameters */
  pagination?: PaginationParams
  /** Full-text search term */
  search?: string
}

/**
 * Helper type for building filter objects with type safety.
 *
 * @example
 * const filters: FilterBuilder = {
 *   status: 'active',
 *   created_at: { gte: '2024-01-01' },
 *   user_id: { in: ['id1', 'id2'] }
 * }
 */
export type FilterBuilder = Record<
  string,
  | string
  | { eq?: string }
  | { ne?: string }
  | { gt?: string }
  | { gte?: string }
  | { lt?: string }
  | { lte?: string }
  | { in?: string[] }
  | { contains?: string }
  | { is_null?: boolean }
>

/**
 * Convert FilterBuilder object to FilterSpec array.
 *
 * @example
 * const specs = filterBuilderToSpecs({
 *   status: 'active',
 *   created_at: { gte: '2024-01-01' }
 * })
 * // Returns: [
 * //   { field: 'status', value: 'active' },
 * //   { field: 'created_at', operator: 'gte', value: '2024-01-01' }
 * // ]
 */
export function filterBuilderToSpecs(builder: FilterBuilder): FilterSpec[] {
  const specs: FilterSpec[] = []

  for (const [field, value] of Object.entries(builder)) {
    if (value === undefined || value === null) continue

    if (typeof value === 'string') {
      // Simple equality filter
      specs.push({ field, value })
    } else if (typeof value === 'object') {
      // Operator-based filter
      const entries = Object.entries(value)
      if (entries.length > 0) {
        const [operator, filterValue] = entries[0]
        if (filterValue !== undefined) {
          specs.push({
            field,
            operator: operator as FilterOperator,
            value: filterValue,
          })
        }
      }
    }
  }

  return specs
}

/**
 * Parse a sort string into SortSpec array.
 *
 * @example
 * parseSortString('created_at:desc,name:asc')
 * // Returns: [{ field: 'created_at', direction: 'desc' }, { field: 'name', direction: 'asc' }]
 */
export function parseSortString(sort: string): SortSpec[] {
  if (!sort) return []

  return sort.split(',').map((part) => {
    const [field, direction] = part.trim().split(':')
    return {
      field,
      direction: (direction?.toLowerCase() || 'asc') as SortDirection,
    }
  })
}

/**
 * Build a sort string from SortSpec array.
 *
 * @example
 * buildSortString([{ field: 'created_at', direction: 'desc' }])
 * // Returns: 'created_at:desc'
 */
export function buildSortString(sorts: SortSpec[]): string {
  return sorts.map((s) => `${s.field}:${s.direction}`).join(',')
}
