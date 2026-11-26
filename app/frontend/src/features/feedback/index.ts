/**
 * Feedback feature exports
 */

// Types
export type {
  Feedback,
  FeedbackAttachment,
  FeedbackType,
  FeedbackStatus,
  CreateFeedbackRequest,
  UpdateFeedbackRequest,
  FeedbackListResponse,
  CreateFeedbackResponse,
  UpdateFeedbackResponse,
  DeleteFeedbackResponse,
  FeedbackAttachmentRequest,
  FeedbackListQueryParams,
} from './types'

// API hooks
export {
  useSubmitFeedbackMutation,
  useGetMyFeedbackQuery,
  useGetFeedbackListQuery,
  useGetFeedbackQuery,
  useUpdateFeedbackMutation,
  useDeleteFeedbackMutation,
  useUploadAttachmentMutation,
} from './feedbackApi'
