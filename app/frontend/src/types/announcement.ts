/**
 * Announcement types - TypeScript types matching backend serializers
 */

/**
 * Announcement priority levels
 */
export type AnnouncementPriority = 'critical' | 'high' | 'normal' | 'low'

/**
 * Single announcement response
 */
export interface Announcement {
  id: string
  organization_id: string | null
  title: string
  body: string
  priority: AnnouncementPriority
  background_color: string | null
  text_color: string | null
  featured_image_url: string | null
  cta_text: string | null
  cta_url: string | null
  cta_dismisses: boolean
  cta_button_color: string | null
  cta_button_variant: string | null
  is_dismissible: boolean
  start_time: string | null
  end_time: string | null
  created_by_id: string
  created_time: string | null
  updated_time: string | null
  is_platform_wide: boolean
}

/**
 * Request schema for creating an announcement
 */
export interface AnnouncementCreateRequest {
  title: string
  body: string
  priority?: AnnouncementPriority
  background_color?: string | null
  text_color?: string | null
  featured_image_url?: string | null
  cta_text?: string | null
  cta_url?: string | null
  cta_dismisses?: boolean
  cta_button_color?: string | null
  cta_button_variant?: string | null
  is_dismissible?: boolean
  start_time?: string | null
  end_time?: string | null
  is_platform_wide?: boolean
}

/**
 * Request schema for updating an announcement
 */
export interface AnnouncementUpdateRequest {
  title?: string
  body?: string
  priority?: AnnouncementPriority
  background_color?: string | null
  text_color?: string | null
  featured_image_url?: string | null
  cta_text?: string | null
  cta_url?: string | null
  cta_dismisses?: boolean
  cta_button_color?: string | null
  cta_button_variant?: string | null
  is_dismissible?: boolean
  start_time?: string | null
  end_time?: string | null
}

/**
 * Paginated list response for announcements
 */
export interface AnnouncementListResponse {
  items: Announcement[]
  total: number
  limit: number
  offset: number
}

/**
 * Active announcements response
 */
export interface ActiveAnnouncementsResponse {
  announcements: Announcement[]
}

/**
 * Response after dismissing an announcement
 */
export interface DismissAnnouncementResponse {
  message: string
  announcement_id: string
}

/**
 * Query parameters for listing announcements (admin)
 */
export interface AnnouncementListParams {
  limit?: number
  offset?: number
}
