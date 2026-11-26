/**
 * RTK Query API endpoints for feedback operations
 */

import { api } from '@/store/api'
import type {
  Feedback,
  FeedbackAttachment,
  CreateFeedbackRequest,
  UpdateFeedbackRequest,
  FeedbackListResponse,
  CreateFeedbackResponse,
  UpdateFeedbackResponse,
  DeleteFeedbackResponse,
  FeedbackAttachmentRequest,
  FeedbackListQueryParams,
  CreateFeedbackReplyRequest,
  CreateFeedbackReplyResponse,
  MarkFeedbackViewedResponse,
} from './types'

export const feedbackApi = api.injectEndpoints({
  endpoints: (builder) => ({
    // Submit new feedback (authenticated users)
    submitFeedback: builder.mutation<CreateFeedbackResponse, CreateFeedbackRequest>({
      query: (body) => ({
        url: '/feedback',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'Feedback', id: 'LIST' }, { type: 'Feedback', id: 'MY_LIST' }],
    }),

    // Get current user's own feedback
    getMyFeedback: builder.query<FeedbackListResponse, { limit?: number; offset?: number }>({
      query: ({ limit = 100, offset = 0 } = {}) => ({
        url: '/feedback/me',
        params: { limit, offset },
      }),
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({ type: 'Feedback' as const, id })),
              { type: 'Feedback', id: 'MY_LIST' },
            ]
          : [{ type: 'Feedback', id: 'MY_LIST' }],
    }),

    // List all feedback (requires feedback:view permission)
    getFeedbackList: builder.query<FeedbackListResponse, FeedbackListQueryParams>({
      query: (params) => ({
        url: '/feedback',
        params,
      }),
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({ type: 'Feedback' as const, id })),
              { type: 'Feedback', id: 'LIST' },
            ]
          : [{ type: 'Feedback', id: 'LIST' }],
    }),

    // Get single feedback by ID
    getFeedback: builder.query<Feedback, string>({
      query: (id) => `/feedback/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'Feedback', id }],
    }),

    // Update feedback (requires feedback:respond permission)
    updateFeedback: builder.mutation<
      UpdateFeedbackResponse,
      { id: string; data: UpdateFeedbackRequest }
    >({
      query: ({ id, data }) => ({
        url: `/feedback/${id}`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'Feedback', id },
        { type: 'Feedback', id: 'LIST' },
        { type: 'Feedback', id: 'MY_LIST' },
      ],
    }),

    // Delete feedback (requires feedback:delete permission)
    deleteFeedback: builder.mutation<DeleteFeedbackResponse, string>({
      query: (id) => ({
        url: `/feedback/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'Feedback', id },
        { type: 'Feedback', id: 'LIST' },
        { type: 'Feedback', id: 'MY_LIST' },
      ],
    }),

    // Upload attachment to feedback
    uploadAttachment: builder.mutation<
      FeedbackAttachment,
      { feedbackId: string; data: FeedbackAttachmentRequest }
    >({
      query: ({ feedbackId, data }) => ({
        url: `/feedback/${feedbackId}/attachments`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_result, _error, { feedbackId }) => [
        { type: 'Feedback', id: feedbackId },
      ],
    }),

    // Create a reply to feedback
    createFeedbackReply: builder.mutation<
      CreateFeedbackReplyResponse,
      { feedbackId: string; data: CreateFeedbackReplyRequest }
    >({
      query: ({ feedbackId, data }) => ({
        url: `/feedback/${feedbackId}/replies`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_result, _error, { feedbackId }) => [
        { type: 'Feedback', id: feedbackId },
        { type: 'Feedback', id: 'LIST' },
        { type: 'Feedback', id: 'MY_LIST' },
      ],
    }),

    // Mark feedback as viewed (clears unread indicator)
    markFeedbackViewed: builder.mutation<MarkFeedbackViewedResponse, string>({
      query: (feedbackId) => ({
        url: `/feedback/${feedbackId}/mark-viewed`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, feedbackId) => [
        { type: 'Feedback', id: feedbackId },
        { type: 'Feedback', id: 'MY_LIST' },
      ],
    }),

    // Mark feedback as viewed by admin (clears requires_attention indicator)
    markFeedbackViewedByAdmin: builder.mutation<MarkFeedbackViewedResponse, string>({
      query: (feedbackId) => ({
        url: `/feedback/${feedbackId}/mark-viewed-admin`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, feedbackId) => [
        { type: 'Feedback', id: feedbackId },
        { type: 'Feedback', id: 'LIST' },
      ],
    }),
  }),
})

export const {
  useSubmitFeedbackMutation,
  useGetMyFeedbackQuery,
  useGetFeedbackListQuery,
  useGetFeedbackQuery,
  useUpdateFeedbackMutation,
  useDeleteFeedbackMutation,
  useUploadAttachmentMutation,
  useCreateFeedbackReplyMutation,
  useMarkFeedbackViewedMutation,
  useMarkFeedbackViewedByAdminMutation,
} = feedbackApi
