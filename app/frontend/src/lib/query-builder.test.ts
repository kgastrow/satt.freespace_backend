import { describe, it, expect } from 'vitest'
import {
  buildQueryString,
  buildSimpleQueryString,
  parseQueryString,
  createQueryBuilder,
} from './query-builder'
import {
  filterBuilderToSpecs,
  parseSortString,
  buildSortString,
} from './query-types'

describe('buildQueryString', () => {
  describe('filters', () => {
    it('builds simple filter with default operator', () => {
      const result = buildQueryString({
        filters: [{ field: 'status', value: 'active' }],
      })
      // URLSearchParams encodes brackets
      expect(result).toBe('filter%5Bstatus%5D=active')
    })

    it('builds filter with explicit operator', () => {
      const result = buildQueryString({
        filters: [{ field: 'created_at', operator: 'gte', value: '2024-01-01' }],
      })
      expect(result).toBe('filter%5Bcreated_at%5D%5Bgte%5D=2024-01-01')
    })

    it('builds filter with in operator and array value', () => {
      const result = buildQueryString({
        filters: [{ field: 'status', operator: 'in', value: ['a', 'b', 'c'] }],
      })
      expect(result).toBe('filter%5Bstatus%5D%5Bin%5D=a%2Cb%2Cc')
    })

    it('builds multiple filters', () => {
      const result = buildQueryString({
        filters: [
          { field: 'status', value: 'active' },
          { field: 'user_type', value: 'admin' },
        ],
      })
      expect(result).toContain('filter%5Bstatus%5D=active')
      expect(result).toContain('filter%5Buser_type%5D=admin')
    })

    it('handles boolean values for is_null', () => {
      const result = buildQueryString({
        filters: [{ field: 'deleted_at', operator: 'is_null', value: true }],
      })
      expect(result).toBe('filter%5Bdeleted_at%5D%5Bis_null%5D=true')
    })
  })

  describe('sorting', () => {
    it('builds single sort parameter', () => {
      const result = buildQueryString({
        sort: 'created_at:desc',
      })
      // Colon is encoded
      expect(result).toBe('sort=created_at%3Adesc')
    })

    it('builds multiple sort parameters', () => {
      const result = buildQueryString({
        sort: 'name:asc,created_at:desc',
      })
      expect(result).toContain('sort=')
      expect(result).toContain('name')
      expect(result).toContain('created_at')
    })
  })

  describe('pagination', () => {
    it('builds limit and offset', () => {
      const result = buildQueryString({
        pagination: { limit: 20, offset: 40 },
      })
      expect(result).toBe('limit=20&offset=40')
    })

    it('handles zero offset', () => {
      const result = buildQueryString({
        pagination: { limit: 10, offset: 0 },
      })
      expect(result).toBe('limit=10&offset=0')
    })

    it('omits pagination when not provided', () => {
      const result = buildQueryString({
        filters: [{ field: 'status', value: 'active' }],
      })
      expect(result).not.toContain('limit')
      expect(result).not.toContain('offset')
    })
  })

  describe('search', () => {
    it('builds search parameter', () => {
      const result = buildQueryString({
        search: 'john',
      })
      expect(result).toBe('q=john')
    })

    it('encodes special characters in search', () => {
      const result = buildQueryString({
        search: 'john doe',
      })
      expect(result).toBe('q=john+doe')
    })
  })

  describe('combined parameters', () => {
    it('builds complete query string', () => {
      const result = buildQueryString({
        filters: [{ field: 'status', value: 'pending' }],
        sort: 'created_at:desc',
        pagination: { limit: 20, offset: 0 },
        search: 'test',
      })
      expect(result).toContain('filter%5Bstatus%5D=pending')
      expect(result).toContain('sort=')
      expect(result).toContain('limit=20')
      expect(result).toContain('offset=0')
      expect(result).toContain('q=test')
    })

    it('returns empty string for empty params', () => {
      const result = buildQueryString({})
      expect(result).toBe('')
    })
  })
})

describe('buildSimpleQueryString', () => {
  it('builds filter query string from flat params', () => {
    const result = buildSimpleQueryString({
      status: 'active',
      user_type: 'admin',
    })
    // Uses filter DSL format
    expect(result).toContain('filter%5Bstatus%5D=active')
    expect(result).toContain('filter%5Buser_type%5D=admin')
  })

  it('excludes undefined values', () => {
    const result = buildSimpleQueryString({
      status: 'active',
      search: undefined,
    })
    expect(result).toContain('filter%5Bstatus%5D=active')
    expect(result).not.toContain('search')
  })

  it('handles empty object', () => {
    const result = buildSimpleQueryString({})
    expect(result).toBe('')
  })

  it('includes pagination when provided', () => {
    const result = buildSimpleQueryString(
      { status: 'active' },
      { limit: 20, offset: 0 }
    )
    expect(result).toContain('limit=20')
    expect(result).toContain('offset=0')
  })

  it('includes search when provided', () => {
    const result = buildSimpleQueryString({}, undefined, 'test')
    expect(result).toBe('q=test')
  })
})

describe('parseQueryString', () => {
  it('parses simple filters', () => {
    const result = parseQueryString('filter%5Bstatus%5D=active')
    expect(result.filters).toHaveLength(1)
    expect(result.filters![0]).toEqual({
      field: 'status',
      operator: undefined,
      value: 'active',
    })
  })

  it('parses filters with operators', () => {
    const result = parseQueryString('filter%5Bcreated_at%5D%5Bgte%5D=2024-01-01')
    expect(result.filters).toHaveLength(1)
    expect(result.filters![0]).toEqual({
      field: 'created_at',
      operator: 'gte',
      value: '2024-01-01',
    })
  })

  it('parses sort parameter', () => {
    const result = parseQueryString('sort=created_at%3Adesc')
    expect(result.sort).toBe('created_at:desc')
  })

  it('parses pagination', () => {
    const result = parseQueryString('limit=20&offset=40')
    expect(result.pagination).toEqual({ limit: 20, offset: 40 })
  })

  it('parses search parameter', () => {
    const result = parseQueryString('q=john')
    expect(result.search).toBe('john')
  })

  it('parses complete query string', () => {
    const qs = 'filter%5Bstatus%5D=pending&sort=created_at%3Adesc&limit=20&offset=0&q=test'
    const result = parseQueryString(qs)
    expect(result.filters).toHaveLength(1)
    expect(result.sort).toBe('created_at:desc')
    expect(result.pagination).toEqual({ limit: 20, offset: 0 })
    expect(result.search).toBe('test')
  })

  it('handles empty query string', () => {
    const result = parseQueryString('')
    expect(result.filters).toBeUndefined()
    expect(result.sort).toBeUndefined()
    expect(result.pagination).toBeUndefined()
    expect(result.search).toBeUndefined()
  })
})

describe('createQueryBuilder', () => {
  it('builds filters with fluent API', () => {
    const result = createQueryBuilder()
      .filter('status', 'active')
      .build()
    expect(result).toBe('filter%5Bstatus%5D=active')
  })

  it('chains multiple filters', () => {
    const result = createQueryBuilder()
      .filter('status', 'active')
      .filter('user_type', 'admin')
      .build()
    expect(result).toContain('filter%5Bstatus%5D=active')
    expect(result).toContain('filter%5Buser_type%5D=admin')
  })

  it('builds filters with operators', () => {
    const result = createQueryBuilder()
      .filter('created_at', '2024-01-01', 'gte')
      .build()
    expect(result).toBe('filter%5Bcreated_at%5D%5Bgte%5D=2024-01-01')
  })

  it('builds sort', () => {
    const result = createQueryBuilder()
      .sort('created_at', 'desc')
      .build()
    expect(result).toBe('sort=created_at%3Adesc')
  })

  it('builds pagination', () => {
    const result = createQueryBuilder()
      .paginate(20, 40)
      .build()
    expect(result).toBe('limit=20&offset=40')
  })

  it('builds search', () => {
    const result = createQueryBuilder()
      .search('john')
      .build()
    expect(result).toBe('q=john')
  })

  it('chains all methods', () => {
    const result = createQueryBuilder()
      .filter('status', 'pending')
      .sort('created_at', 'desc')
      .paginate(20, 0)
      .search('test')
      .build()
    expect(result).toContain('filter%5Bstatus%5D=pending')
    expect(result).toContain('sort=')
    expect(result).toContain('limit=20')
    expect(result).toContain('offset=0')
    expect(result).toContain('q=test')
  })

  it('returns params object with toParams()', () => {
    const params = createQueryBuilder()
      .filter('status', 'active')
      .sort('created_at', 'desc')
      .toParams()
    expect(params.filters).toHaveLength(1)
    expect(params.sort).toBe('created_at:desc')
  })
})

describe('query-types utilities', () => {
  describe('filterBuilderToSpecs', () => {
    it('converts simple string filters to specs', () => {
      const filters = { status: 'active', user_type: 'admin' }
      const specs = filterBuilderToSpecs(filters)
      expect(specs).toHaveLength(2)
      expect(specs).toContainEqual({ field: 'status', value: 'active' })
      expect(specs).toContainEqual({ field: 'user_type', value: 'admin' })
    })

    it('converts operator-based filters', () => {
      const filters = { created_at: { gte: '2024-01-01' } }
      const specs = filterBuilderToSpecs(filters)
      expect(specs).toHaveLength(1)
      expect(specs[0]).toEqual({ field: 'created_at', operator: 'gte', value: '2024-01-01' })
    })

    it('converts in operator with array', () => {
      const filters = { status: { in: ['a', 'b', 'c'] } }
      const specs = filterBuilderToSpecs(filters)
      expect(specs).toHaveLength(1)
      expect(specs[0]).toEqual({ field: 'status', operator: 'in', value: ['a', 'b', 'c'] })
    })

    it('handles empty object', () => {
      const specs = filterBuilderToSpecs({})
      expect(specs).toHaveLength(0)
    })
  })

  describe('parseSortString', () => {
    it('parses single sort', () => {
      const sorts = parseSortString('created_at:desc')
      expect(sorts).toHaveLength(1)
      expect(sorts[0]).toEqual({ field: 'created_at', direction: 'desc' })
    })

    it('parses multiple sorts', () => {
      const sorts = parseSortString('name:asc,created_at:desc')
      expect(sorts).toHaveLength(2)
      expect(sorts[0]).toEqual({ field: 'name', direction: 'asc' })
      expect(sorts[1]).toEqual({ field: 'created_at', direction: 'desc' })
    })

    it('returns empty array for empty string', () => {
      const sorts = parseSortString('')
      expect(sorts).toHaveLength(0)
    })
  })

  describe('buildSortString', () => {
    it('builds single sort string', () => {
      const result = buildSortString([{ field: 'created_at', direction: 'desc' }])
      expect(result).toBe('created_at:desc')
    })

    it('builds multiple sort string', () => {
      const result = buildSortString([
        { field: 'name', direction: 'asc' },
        { field: 'created_at', direction: 'desc' },
      ])
      expect(result).toBe('name:asc,created_at:desc')
    })

    it('returns empty string for empty array', () => {
      const result = buildSortString([])
      expect(result).toBe('')
    })
  })
})
