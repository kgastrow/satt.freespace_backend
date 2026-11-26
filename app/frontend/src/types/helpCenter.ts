/**
 * Help Center types - TypeScript types matching backend serializers
 */

/**
 * Help content status
 */
export type HelpContentStatus = 'draft' | 'published'

/**
 * Single help category response
 */
export interface HelpCategory {
  id: string
  name: string
  description: string | null
  slug: string
  display_order: number
  created_time: string | null
  updated_time: string | null
}

/**
 * Request schema for creating a help category
 */
export interface HelpCategoryCreateRequest {
  name: string
  description?: string | null
  slug: string
  display_order?: number
}

/**
 * Request schema for updating a help category
 */
export interface HelpCategoryUpdateRequest {
  name?: string
  description?: string | null
  slug?: string
  display_order?: number
}

/**
 * Paginated list response for help categories
 */
export interface HelpCategoryListResponse {
  items: HelpCategory[]
  total: number
  limit: number
  offset: number
}

/**
 * Single help article response
 */
export interface HelpArticle {
  id: string
  organization_id: string | null
  title: string
  slug: string
  content: string
  category_id: string
  status: HelpContentStatus
  published_at: string | null
  featured_image_url: string | null
  display_order: number
  created_by_id: string
  created_time: string | null
  updated_time: string | null
  is_platform_wide: boolean
}

/**
 * Request schema for creating a help article
 */
export interface HelpArticleCreateRequest {
  title: string
  slug: string
  content: string
  category_id: string
  status?: HelpContentStatus
  published_at?: string | null
  featured_image_url?: string | null
  display_order?: number
  is_platform_wide?: boolean
}

/**
 * Request schema for updating a help article
 */
export interface HelpArticleUpdateRequest {
  title?: string
  slug?: string
  content?: string
  category_id?: string
  status?: HelpContentStatus
  published_at?: string | null
  featured_image_url?: string | null
  display_order?: number
}

/**
 * Paginated list response for help articles
 */
export interface HelpArticleListResponse {
  items: HelpArticle[]
  total: number
  limit: number
  offset: number
}

/**
 * Single FAQ response
 */
export interface HelpFaq {
  id: string
  organization_id: string | null
  question: string
  answer: string
  category_id: string
  status: HelpContentStatus
  display_order: number
  created_time: string | null
  updated_time: string | null
  is_platform_wide: boolean
}

/**
 * Request schema for creating a FAQ
 */
export interface HelpFaqCreateRequest {
  question: string
  answer: string
  category_id: string
  status?: HelpContentStatus
  display_order?: number
  is_platform_wide?: boolean
}

/**
 * Request schema for updating a FAQ
 */
export interface HelpFaqUpdateRequest {
  question?: string
  answer?: string
  category_id?: string
  status?: HelpContentStatus
  display_order?: number
}

/**
 * Paginated list response for FAQs
 */
export interface HelpFaqListResponse {
  items: HelpFaq[]
  total: number
  limit: number
  offset: number
}

/**
 * Response schema for help center search
 */
export interface HelpSearchResponse {
  articles: HelpArticle[]
  faqs: HelpFaq[]
  total_results: number
}

/**
 * Response schema for delete operations
 */
export interface HelpDeleteResponse {
  message: string
  message_code: string
}

/**
 * Query parameters for listing help categories
 */
export interface HelpCategoryListParams {
  limit?: number
  offset?: number
}

/**
 * Query parameters for listing help articles
 */
export interface HelpArticleListParams {
  category_id?: string
  status?: HelpContentStatus
  limit?: number
  offset?: number
}

/**
 * Query parameters for listing FAQs
 */
export interface HelpFaqListParams {
  category_id?: string
  status?: HelpContentStatus
  limit?: number
  offset?: number
}

/**
 * Query parameters for help search
 */
export interface HelpSearchParams {
  q: string
}

/**
 * Single item in a reorder request
 */
export interface ReorderItem {
  id: string
  display_order: number
}

/**
 * Request schema for reordering items
 */
export interface ReorderRequest {
  items: ReorderItem[]
}

/**
 * Response schema for reorder operations
 */
export interface ReorderResponse {
  message: string
  message_code: string
  updated_count: number
}
