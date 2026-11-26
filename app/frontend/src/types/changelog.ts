/**
 * Changelog types - TypeScript types matching backend serializers
 */

/**
 * Changelog category types
 */
export type ChangelogCategory =
  | 'feature'
  | 'improvement'
  | 'bugfix'
  | 'breaking'
  | 'other'

/**
 * Single changelog entry response
 */
export interface ChangelogEntry {
  id: string
  organization_id: string | null
  version: string
  title: string
  body: string
  category: ChangelogCategory
  release_date: string
  is_published: boolean
  created_by_id: string
  created_time: string | null
  updated_time: string | null
  is_platform_wide: boolean
  is_viewed: boolean
}

/**
 * Request schema for creating a changelog entry
 */
export interface CreateChangelogRequest {
  version: string
  title: string
  body: string
  category?: ChangelogCategory
  release_date: string
  is_published?: boolean
  is_platform_wide?: boolean
}

/**
 * Request schema for updating a changelog entry
 */
export interface UpdateChangelogRequest {
  version?: string
  title?: string
  body?: string
  category?: ChangelogCategory
  release_date?: string
  is_published?: boolean
}

/**
 * Paginated list response for changelog entries
 */
export interface ChangelogListResponse {
  items: ChangelogEntry[]
  total: number
  limit: number
  offset: number
  unread_count: number
}

/**
 * Unread count response
 */
export interface UnreadCountResponse {
  count: number
}

/**
 * Query parameters for listing changelog entries
 */
export interface ChangelogListParams {
  limit?: number
  offset?: number
  category?: ChangelogCategory
}
