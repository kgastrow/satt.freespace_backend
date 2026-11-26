/**
 * Query String Builder for the Query DSL.
 *
 * Builds URL query strings in the standardized format:
 * - filter[field]=value (implicit eq operator)
 * - filter[field][operator]=value (explicit operator)
 * - sort=field:direction
 * - limit=N&offset=N
 * - q=search_term
 *
 * @example
 * const queryString = buildQueryString({
 *   filters: [
 *     { field: 'status', value: 'active' },
 *     { field: 'created_at', operator: 'gte', value: '2024-01-01' }
 *   ],
 *   sort: 'created_at:desc',
 *   pagination: { limit: 20, offset: 0 },
 *   search: 'john'
 * })
 * // Returns: "filter[status]=active&filter[created_at][gte]=2024-01-01&sort=created_at:desc&limit=20&offset=0&q=john"
 */

import type { FilterSpec, QueryParams, PaginationParams } from './query-types'

/**
 * Build a complete query string from QueryParams.
 *
 * @param params - Query parameters object
 * @returns URL-encoded query string (without leading '?')
 */
export function buildQueryString(params: QueryParams): string {
  const searchParams = new URLSearchParams()

  // Add filters
  if (params.filters) {
    for (const filter of params.filters) {
      addFilterToParams(searchParams, filter)
    }
  }

  // Add sort
  if (params.sort) {
    searchParams.set('sort', params.sort)
  }

  // Add pagination
  if (params.pagination) {
    if (params.pagination.limit !== undefined) {
      searchParams.set('limit', String(params.pagination.limit))
    }
    if (params.pagination.offset !== undefined) {
      searchParams.set('offset', String(params.pagination.offset))
    }
  }

  // Add search
  if (params.search) {
    searchParams.set('q', params.search)
  }

  return searchParams.toString()
}

/**
 * Add a single filter to URLSearchParams.
 */
function addFilterToParams(
  searchParams: URLSearchParams,
  filter: FilterSpec
): void {
  const { field, operator, value } = filter

  // Build the parameter key
  let key: string
  if (!operator || operator === 'eq') {
    key = `filter[${field}]`
  } else {
    key = `filter[${field}][${operator}]`
  }

  // Handle different value types
  if (Array.isArray(value)) {
    // For 'in' operator, join with commas
    searchParams.set(key, value.join(','))
  } else if (typeof value === 'boolean') {
    // For 'is_null' operator
    searchParams.set(key, String(value))
  } else {
    searchParams.set(key, value)
  }
}

/**
 * Build query string with simple key-value filters.
 * Convenience function for endpoints that don't need operators.
 *
 * @example
 * buildSimpleQueryString({
 *   status: 'active',
 *   user_type_id: 'abc123'
 * }, { limit: 20 }, 'search term')
 * // Returns: "filter[status]=active&filter[user_type_id]=abc123&limit=20&q=search%20term"
 */
export function buildSimpleQueryString(
  filters: Record<string, string | undefined>,
  pagination?: PaginationParams,
  search?: string
): string {
  const filterSpecs: FilterSpec[] = []

  for (const [field, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') {
      filterSpecs.push({ field, value })
    }
  }

  return buildQueryString({
    filters: filterSpecs.length > 0 ? filterSpecs : undefined,
    pagination,
    search: search || undefined,
  })
}

/**
 * Append query string to a base URL path.
 *
 * @example
 * appendQueryString('/api/users', 'filter[status]=active&limit=20')
 * // Returns: "/api/users?filter[status]=active&limit=20"
 */
export function appendQueryString(basePath: string, queryString: string): string {
  if (!queryString) {
    return basePath
  }
  return `${basePath}?${queryString}`
}

/**
 * Parse query string back into QueryParams.
 * Useful for reading current filters from URL.
 *
 * @param queryString - URL query string (with or without leading '?')
 * @returns Parsed QueryParams object
 */
export function parseQueryString(queryString: string): QueryParams {
  const searchParams = new URLSearchParams(
    queryString.startsWith('?') ? queryString.slice(1) : queryString
  )

  const filters: FilterSpec[] = []
  let sort: string | undefined
  const pagination: PaginationParams = {}
  let search: string | undefined

  for (const [key, value] of searchParams.entries()) {
    // Parse filter parameters
    const filterMatch = key.match(/^filter\[(\w+)\](?:\[(\w+)\])?$/)
    if (filterMatch) {
      const [, field, operator] = filterMatch
      filters.push({
        field,
        operator: operator as FilterSpec['operator'],
        value,
      })
      continue
    }

    // Parse other parameters
    switch (key) {
      case 'sort':
        sort = value
        break
      case 'limit':
        pagination.limit = parseInt(value, 10)
        break
      case 'offset':
        pagination.offset = parseInt(value, 10)
        break
      case 'q':
        search = value
        break
    }
  }

  return {
    filters: filters.length > 0 ? filters : undefined,
    sort,
    pagination:
      pagination.limit !== undefined || pagination.offset !== undefined
        ? pagination
        : undefined,
    search,
  }
}

/**
 * Create a query builder with fluent API.
 *
 * @example
 * const query = createQueryBuilder()
 *   .filter('status', 'active')
 *   .filter('created_at', '2024-01-01', 'gte')
 *   .sort('created_at', 'desc')
 *   .paginate(20, 0)
 *   .search('john')
 *   .build()
 */
export function createQueryBuilder() {
  const filters: FilterSpec[] = []
  let sort: string | undefined
  let pagination: PaginationParams | undefined
  let search: string | undefined

  return {
    filter(
      field: string,
      value: string | string[] | boolean,
      operator?: FilterSpec['operator']
    ) {
      filters.push({ field, operator, value })
      return this
    },

    sort(field: string, direction: 'asc' | 'desc' = 'desc') {
      sort = `${field}:${direction}`
      return this
    },

    multiSort(sorts: Array<{ field: string; direction: 'asc' | 'desc' }>) {
      sort = sorts.map((s) => `${s.field}:${s.direction}`).join(',')
      return this
    },

    paginate(limit: number, offset: number = 0) {
      pagination = { limit, offset }
      return this
    },

    search(term: string) {
      search = term
      return this
    },

    build(): string {
      return buildQueryString({
        filters: filters.length > 0 ? filters : undefined,
        sort,
        pagination,
        search,
      })
    },

    toParams(): QueryParams {
      return {
        filters: filters.length > 0 ? filters : undefined,
        sort,
        pagination,
        search,
      }
    },
  }
}
