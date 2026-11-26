/**
 * TypeScript types for the feedback feature
 */

export type FeedbackType = 'bug' | 'suggestion' | 'complaint' | 'praise' | 'other'

export type FeedbackStatus = 'new' | 'in_review' | 'resolved' | 'dismissed'

export interface FeedbackAttachment {
  id: string
  feedback_id: string
  file_path: string
  file_type: string
  file_size_bytes: number
  created_time: string | null
}

export interface FeedbackReply {
  id: string
  feedback_id: string
  user_id: string
  user_email: string | null
  message: string
  is_admin_reply: boolean
  created_time: string | null
}

export interface Feedback {
  id: string
  organization_id: string
  user_id: string
  user_email: string | null
  type: FeedbackType
  rating: number | null
  subject: string
  message: string
  page_url: string | null
  user_agent: string | null
  screen_resolution: string | null
  status: FeedbackStatus
  admin_notes: string | null
  admin_response: string | null
  responded_by: string | null
  responded_at: string | null
  resolved_by: string | null
  resolved_at: string | null
  user_last_viewed_at: string | null
  admin_last_viewed_at: string | null
  has_unread_replies: boolean
  requires_attention: boolean
  created_time: string | null
  updated_time: string | null
  attachments: FeedbackAttachment[]
  replies: FeedbackReply[]
}

export interface CreateFeedbackRequest {
  type: FeedbackType
  rating?: number | null
  subject: string
  message: string
  page_url?: string | null
  user_agent?: string | null
  screen_resolution?: string | null
}

export interface UpdateFeedbackRequest {
  status?: FeedbackStatus
  admin_notes?: string | null
  admin_response?: string | null
}

export interface FeedbackListResponse {
  items: Feedback[]
  total: number
  limit: number
  offset: number
}

export interface CreateFeedbackResponse {
  message: string
  message_code: string
  feedback: Feedback
}

export interface UpdateFeedbackResponse {
  message: string
  message_code: string
  feedback: Feedback
}

export interface DeleteFeedbackResponse {
  message: string
  message_code: string
  feedback_id: string
}

export interface FeedbackAttachmentRequest {
  file_path: string
  file_type: string
  file_size_bytes: number
}

export interface FeedbackListQueryParams {
  'filter[type]'?: FeedbackType
  'filter[status]'?: FeedbackStatus
  'filter[rating][gte]'?: number
  'filter[rating][lte]'?: number
  'filter[created_time][gte]'?: string
  'filter[created_time][lte]'?: string
  organization_id?: string
  sort?: string
  limit?: number
  offset?: number
}

export interface CreateFeedbackReplyRequest {
  message: string
}

export interface CreateFeedbackReplyResponse {
  message: string
  message_code: string
  reply: FeedbackReply
}

export interface MarkFeedbackViewedResponse {
  message: string
  message_code: string
  feedback_id: string
  viewed_at: string
}
