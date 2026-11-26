import { api } from '@/store/api'

export interface UserType {
  id: string
  name: string
  code: string
  description: string | null
  is_active: boolean
  requires_onboarding: boolean
  requires_manual_review: boolean
  is_default: boolean
  display_order: number
  created_time: string
}

export interface OnboardingStep {
  id: string
  user_type_id: string
  name: string
  code: string
  description: string | null
  step_order: number
  required_fields: Record<string, unknown>
  validation_rules: Record<string, unknown>
  requires_verification: boolean
  is_active: boolean
}

export interface UserOnboardingProgress {
  id: string
  user_id: string
  user_user_type_id: string
  onboarding_step_id: string
  organization_id: string
  submitted_data: Record<string, unknown>
  completed_time: string | null
  created_time: string
}

export interface UserUserTypeInfo {
  user_user_type_id: string
  user_type_id: string
  user_type_name: string
  user_type_code: string
  onboarding_status: 'pending' | 'in_progress' | 'pending_review' | 'change_requested' | 'approved' | 'rejected'
  onboarded_at: string | null
}

export interface OnboardingStatusResponse {
  status: 'not_started' | 'in_progress' | 'pending_review' | 'change_requested' | 'approved' | 'rejected'
  user_user_type_id: string | null
  current_step: OnboardingStep | null
  progress: UserOnboardingProgress[]
  steps: OnboardingStep[]
  user_type: UserType | null
  completed_steps_count: number
  total_steps_count: number
  all_user_types: UserUserTypeInfo[]
  can_add_more_types: boolean
}

export interface MyUserTypesResponse {
  user_types: Array<UserUserTypeInfo & { user_type_description: string | null; created_time: string | null }>
  total: number
}

export interface StartOnboardingRequest {
  user_type_id: string
}

export interface StartOnboardingResponse {
  user_user_type_id: string
  status: string
  message: string
}

export interface SubmitStepRequest {
  submitted_data: Record<string, unknown>
}

export interface SubmitStepResponse {
  progress_id: string
  completed: boolean
  next_step: OnboardingStep | null
  message: string
}

export interface SendOtpRequest {
  phone: string
}

export interface SendOtpResponse {
  message: string
  expires_at: string
}

export interface VerifyOtpRequest {
  phone: string
  otp: string
}

export interface VerifyOtpResponse {
  verified: boolean
  message: string
}

export interface PendingReviewSubmission {
  id: string
  user_id: string
  user_first_name: string
  user_last_name: string
  user_email: string
  user_type_id: string
  user_type_name: string
  submitted_at: string
  status: string
  requires_admin_attention: boolean
}

export interface PendingReviewsResponse {
  items: PendingReviewSubmission[]
  total: number
  limit: number
  offset: number
}

export interface SubmissionsResponse {
  items: PendingReviewSubmission[]
  total: number
  limit: number
  offset: number
}

export interface SubmissionsQueryParams {
  status?: 'pending_review' | 'change_requested' | 'approved' | 'rejected'
  search?: string
  user_type_id?: string
  requires_attention?: boolean
  limit?: number
  offset?: number
}

export interface SubmissionProgress {
  onboarding_step_id: string
  step_name: string
  submitted_data: Record<string, unknown>
  completed_time: string
}

export interface SubmissionDetailsResponse {
  id: string
  user_id: string
  user_first_name: string
  user_last_name: string
  user_email: string
  user_type_id: string
  user_type_name: string
  submitted_at: string
  onboarding_status: string
  requires_admin_attention: boolean
  steps_data: SubmissionProgress[]
}

export interface RejectSubmissionRequest {
  user_user_type_id: string
  reason: string
}

export interface ApproveSubmissionRequest {
  expires_at?: string | null
}

export interface ApproveRejectResponse {
  message: string
  status: string
  expires_at?: string | null
}

// Admin API types
export interface UserTypeListResponse {
  items: UserType[]
  total: number
  limit: number
  offset: number
}

export interface CreateUserTypeRequest {
  name: string
  code: string
  description?: string
  is_active?: boolean
  requires_onboarding?: boolean
  requires_manual_review?: boolean
  is_default?: boolean
  display_order?: number
}

export interface UpdateUserTypeRequest {
  name?: string
  code?: string
  description?: string | null
  is_active?: boolean
  requires_onboarding?: boolean
  requires_manual_review?: boolean
  is_default?: boolean
  display_order?: number
}

export interface OnboardingStepListResponse {
  items: OnboardingStep[]
  total: number
  limit: number
  offset: number
}

export interface CreateOnboardingStepRequest {
  user_type_id: string
  name: string
  code: string
  description?: string
  step_order: number
  required_fields: Record<string, unknown>
  validation_rules?: Record<string, unknown>
  requires_verification?: boolean
  is_active?: boolean
}

export interface UpdateOnboardingStepRequest {
  name?: string
  code?: string
  description?: string | null
  step_order?: number
  required_fields?: Record<string, unknown>
  validation_rules?: Record<string, unknown>
  requires_verification?: boolean
  is_active?: boolean
}

export interface ReorderStepsRequest {
  steps: Array<{ step_id: string; step_order: number }>
}

// Review Comment Types
export interface ReviewComment {
  id: string
  author_id: string
  author_name: string
  author_type: 'admin' | 'user'
  comment: string
  created_time: string
}

export interface ReviewCommentsResponse {
  comments: ReviewComment[]
}

export interface RequestChangeRequest {
  comment: string
}

export interface RespondToChangeRequest {
  comment: string
}

export const onboardingApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /onboarding/status - Get current user's onboarding status
     */
    getOnboardingStatus: builder.query<OnboardingStatusResponse, void>({
      query: () => '/onboarding/status',
      providesTags: [{ type: 'UserOnboarding', id: 'STATUS' }],
    }),

    /**
     * GET /onboarding/my-user-types - Get all user types the current user has onboarded as
     */
    getMyUserTypes: builder.query<MyUserTypesResponse, void>({
      query: () => '/onboarding/my-user-types',
      providesTags: [{ type: 'UserOnboarding', id: 'MY_USER_TYPES' }],
    }),

    /**
     * POST /onboarding/start/{user_type_id} - Start onboarding for a user type
     */
    startOnboarding: builder.mutation<StartOnboardingResponse, string>({
      query: (userTypeId) => ({
        url: `/onboarding/start/${userTypeId}`,
        method: 'POST',
      }),
      invalidatesTags: [{ type: 'UserOnboarding', id: 'STATUS' }, { type: 'UserOnboarding', id: 'MY_USER_TYPES' }],
    }),

    /**
     * POST /onboarding/steps/{step_id}/submit - Submit step data
     */
    submitOnboardingStep: builder.mutation<SubmitStepResponse, { stepId: string; data: SubmitStepRequest }>({
      query: ({ stepId, data }) => ({
        url: `/onboarding/steps/${stepId}/submit`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: [{ type: 'UserOnboarding', id: 'STATUS' }],
    }),

    /**
     * POST /onboarding/phone/send-otp - Send OTP to phone
     */
    sendPhoneOtp: builder.mutation<SendOtpResponse, SendOtpRequest>({
      query: (body) => ({
        url: '/onboarding/phone/send-otp',
        method: 'POST',
        body,
      }),
    }),

    /**
     * POST /onboarding/phone/verify - Verify OTP
     */
    verifyPhoneOtp: builder.mutation<VerifyOtpResponse, VerifyOtpRequest>({
      query: (body) => ({
        url: '/onboarding/phone/verify',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'UserOnboarding', id: 'STATUS' }],
    }),

    /**
     * GET /user-types - Get all active user types
     */
    getActiveUserTypes: builder.query<UserType[], void>({
      query: () => '/user-types',
      transformResponse: (response: UserTypeListResponse) => response.items,
      providesTags: (result) =>
        result
          ? [...result.map(({ id }) => ({ type: 'UserType' as const, id })), { type: 'UserType', id: 'LIST' }]
          : [{ type: 'UserType', id: 'LIST' }],
    }),

    /**
     * GET /onboarding/review/submissions - Get onboarding submissions with filtering
     */
    /**
     * GET /onboarding/review/submissions - Get onboarding submissions with filtering
     *
     * Response follows standard ListResponse format with 'items' key.
     * Note: This endpoint uses legacy flat params; will migrate to filter[field] DSL format.
     */
    getSubmissions: builder.query<SubmissionsResponse, SubmissionsQueryParams>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params.status) searchParams.set('status', params.status)
        if (params.search) searchParams.set('search', params.search)
        if (params.user_type_id) searchParams.set('user_type_id', params.user_type_id)
        if (params.requires_attention !== undefined) searchParams.set('requires_attention', params.requires_attention.toString())
        if (params.limit) searchParams.set('limit', params.limit.toString())
        if (params.offset !== undefined) searchParams.set('offset', params.offset.toString())
        const queryString = searchParams.toString()
        return `/onboarding/review/submissions${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result, _error, params) =>
        result
          ? [
              // Tag for each individual submission
              ...result.items.map(({ id }) => ({ type: 'UserOnboarding' as const, id })),
              // Tag for this specific status filter
              { type: 'UserOnboarding', id: `SUBMISSIONS_${params.status || 'ALL'}` },
              // General submissions tag
              { type: 'UserOnboarding', id: 'SUBMISSIONS' },
            ]
          : [{ type: 'UserOnboarding', id: 'SUBMISSIONS' }],
    }),

    /**
     * GET /onboarding/review/pending - Get pending onboarding submissions for review
     */
    getPendingReviews: builder.query<PendingReviewsResponse, { limit: number; offset: number }>({
      query: ({ limit, offset }) => `/onboarding/review/pending?limit=${limit}&offset=${offset}`,
      providesTags: [{ type: 'UserOnboarding', id: 'PENDING_REVIEWS' }],
    }),

    /**
     * GET /onboarding/review/{user_user_type_id} - Get submission details for review
     */
    getSubmissionDetails: builder.query<SubmissionDetailsResponse, string>({
      query: (userUserTypeId) => `/onboarding/review/${userUserTypeId}`,
      providesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: userUserTypeId },
      ],
    }),

    /**
     * POST /onboarding/review/{user_user_type_id}/approve - Approve onboarding submission
     */
    approveSubmission: builder.mutation<ApproveRejectResponse, { userUserTypeId: string; body?: ApproveSubmissionRequest }>({
      query: ({ userUserTypeId, body }) => ({
        url: `/onboarding/review/${userUserTypeId}/approve`,
        method: 'POST',
        body: body,
      }),
      invalidatesTags: (_result, _error, { userUserTypeId }) => [
        { type: 'UserOnboarding', id: 'PENDING_REVIEWS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_approved' },
        { type: 'UserOnboarding', id: userUserTypeId },
      ],
    }),

    /**
     * POST /onboarding/review/{user_user_type_id}/reject - Reject onboarding submission
     */
    rejectSubmission: builder.mutation<ApproveRejectResponse, RejectSubmissionRequest>({
      query: ({ user_user_type_id, reason }) => ({
        url: `/onboarding/review/${user_user_type_id}/reject`,
        method: 'POST',
        body: { reason },
      }),
      invalidatesTags: (_result, _error, { user_user_type_id }) => [
        { type: 'UserOnboarding', id: 'PENDING_REVIEWS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_rejected' },
        { type: 'UserOnboarding', id: user_user_type_id },
      ],
    }),

    /**
     * POST /onboarding/review/{user_user_type_id}/request-change - Request changes from user
     */
    requestChange: builder.mutation<ApproveRejectResponse, { user_user_type_id: string; comment: string }>({
      query: ({ user_user_type_id, comment }) => ({
        url: `/onboarding/review/${user_user_type_id}/request-change`,
        method: 'POST',
        body: { comment },
      }),
      invalidatesTags: (_result, _error, { user_user_type_id }) => [
        { type: 'UserOnboarding', id: 'PENDING_REVIEWS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: user_user_type_id },
      ],
    }),

    /**
     * GET /onboarding/review/{user_user_type_id}/comments - Get review comments (admin)
     */
    getReviewComments: builder.query<ReviewCommentsResponse, string>({
      query: (userUserTypeId) => `/onboarding/review/${userUserTypeId}/comments`,
      providesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: `COMMENTS_${userUserTypeId}` },
      ],
    }),

    /**
     * POST /onboarding/review/{user_user_type_id}/comments - Admin adds a comment
     */
    addReviewComment: builder.mutation<{ message: string }, { user_user_type_id: string; comment: string }>({
      query: ({ user_user_type_id, comment }) => ({
        url: `/onboarding/review/${user_user_type_id}/comments`,
        method: 'POST',
        body: { comment },
      }),
      invalidatesTags: (_result, _error, { user_user_type_id }) => [
        { type: 'UserOnboarding', id: `COMMENTS_${user_user_type_id}` },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: user_user_type_id },
      ],
    }),

    /**
     * POST /onboarding/submissions/{user_user_type_id}/respond - User responds to change request
     */
    respondToChangeRequest: builder.mutation<{ message: string }, { user_user_type_id: string; comment: string }>({
      query: ({ user_user_type_id, comment }) => ({
        url: `/onboarding/submissions/${user_user_type_id}/respond`,
        method: 'POST',
        body: { comment },
      }),
      invalidatesTags: (_result, _error, { user_user_type_id }) => [
        { type: 'UserOnboarding', id: 'STATUS' },
        { type: 'UserOnboarding', id: `COMMENTS_${user_user_type_id}` },
      ],
    }),

    /**
     * POST /onboarding/submissions/{user_user_type_id}/resubmit - User resubmits for review
     */
    resubmitForReview: builder.mutation<{ message: string; status: string }, string>({
      query: (userUserTypeId) => ({
        url: `/onboarding/submissions/${userUserTypeId}/resubmit`,
        method: 'POST',
      }),
      invalidatesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: 'STATUS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: userUserTypeId },
      ],
    }),

    /**
     * DELETE /onboarding/submissions/{user_user_type_id} - User withdraws from in-flight onboarding
     */
    withdrawOnboarding: builder.mutation<
      { message: string; user_user_type_id: string; prior_status: string },
      string
    >({
      query: (userUserTypeId) => ({
        url: `/onboarding/submissions/${userUserTypeId}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: 'STATUS' },
        { type: 'UserOnboarding', id: 'MY_USER_TYPES' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_pending_review' },
        { type: 'UserOnboarding', id: 'SUBMISSIONS_change_requested' },
        { type: 'UserOnboarding', id: 'PENDING_REVIEWS' },
        { type: 'UserOnboarding', id: userUserTypeId },
      ],
    }),

    /**
     * GET /onboarding/submissions/{user_user_type_id}/comments - Get review comments (user)
     */
    getMyReviewComments: builder.query<ReviewCommentsResponse, string>({
      query: (userUserTypeId) => `/onboarding/submissions/${userUserTypeId}/comments`,
      providesTags: (_result, _error, userUserTypeId) => [
        { type: 'UserOnboarding', id: `COMMENTS_${userUserTypeId}` },
      ],
    }),

    // ==================== Admin User Type Endpoints ====================

    /**
     * GET /admin/user-types - Get all user types (super admin only)
     */
    getAdminUserTypes: builder.query<UserTypeListResponse, void>({
      query: () => '/admin/user-types',
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({ type: 'UserType' as const, id })),
              { type: 'UserType', id: 'ADMIN_LIST' },
            ]
          : [{ type: 'UserType', id: 'ADMIN_LIST' }],
    }),

    /**
     * GET /admin/user-types/{id} - Get a user type by ID (super admin only)
     */
    getAdminUserType: builder.query<UserType, string>({
      query: (id) => `/admin/user-types/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'UserType', id }],
    }),

    /**
     * POST /admin/user-types - Create a new user type (super admin only)
     */
    createUserType: builder.mutation<UserType, CreateUserTypeRequest>({
      query: (body) => ({
        url: '/admin/user-types',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'UserType', id: 'ADMIN_LIST' }, { type: 'UserType', id: 'LIST' }],
    }),

    /**
     * PUT /admin/user-types/{id} - Update a user type (super admin only)
     */
    updateUserType: builder.mutation<UserType, { id: string; data: UpdateUserTypeRequest }>({
      query: ({ id, data }) => ({
        url: `/admin/user-types/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'UserType', id },
        { type: 'UserType', id: 'ADMIN_LIST' },
        { type: 'UserType', id: 'LIST' },
      ],
    }),

    /**
     * DELETE /admin/user-types/{id} - Delete a user type (super admin only)
     */
    deleteUserType: builder.mutation<void, string>({
      query: (id) => ({
        url: `/admin/user-types/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: [{ type: 'UserType', id: 'ADMIN_LIST' }, { type: 'UserType', id: 'LIST' }],
    }),

    // ==================== Admin Onboarding Step Endpoints ====================

    /**
     * GET /admin/onboarding-steps/user-type/{user_type_id} - Get steps for a user type
     */
    getAdminOnboardingSteps: builder.query<OnboardingStepListResponse, string>({
      query: (userTypeId) => `/admin/onboarding-steps/user-type/${userTypeId}`,
      providesTags: (result, _error, userTypeId) =>
        result
          ? [
              ...result.items.map(({ id }) => ({ type: 'OnboardingStep' as const, id })),
              { type: 'OnboardingStep', id: `USER_TYPE_${userTypeId}` },
            ]
          : [{ type: 'OnboardingStep', id: `USER_TYPE_${userTypeId}` }],
    }),

    /**
     * GET /admin/onboarding-steps/{id} - Get a step by ID
     */
    getAdminOnboardingStep: builder.query<OnboardingStep, string>({
      query: (id) => `/admin/onboarding-steps/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'OnboardingStep', id }],
    }),

    /**
     * POST /admin/onboarding-steps - Create a new onboarding step
     */
    createOnboardingStep: builder.mutation<OnboardingStep, CreateOnboardingStepRequest>({
      query: (body) => ({
        url: '/admin/onboarding-steps',
        method: 'POST',
        body,
      }),
      invalidatesTags: (_result, _error, { user_type_id }) => [
        { type: 'OnboardingStep', id: `USER_TYPE_${user_type_id}` },
      ],
    }),

    /**
     * PUT /admin/onboarding-steps/{id} - Update an onboarding step
     */
    updateOnboardingStep: builder.mutation<
      OnboardingStep,
      { id: string; data: UpdateOnboardingStepRequest; userTypeId: string }
    >({
      query: ({ id, data }) => ({
        url: `/admin/onboarding-steps/${id}`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id, userTypeId }) => [
        { type: 'OnboardingStep', id },
        { type: 'OnboardingStep', id: `USER_TYPE_${userTypeId}` },
      ],
    }),

    /**
     * DELETE /admin/onboarding-steps/{id} - Delete an onboarding step
     */
    deleteOnboardingStep: builder.mutation<void, { id: string; userTypeId: string }>({
      query: ({ id }) => ({
        url: `/admin/onboarding-steps/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, { userTypeId }) => [
        { type: 'OnboardingStep', id: `USER_TYPE_${userTypeId}` },
      ],
    }),

    /**
     * POST /admin/onboarding-steps/user-type/{user_type_id}/reorder - Reorder steps
     */
    reorderOnboardingSteps: builder.mutation<void, { userTypeId: string; steps: ReorderStepsRequest['steps'] }>({
      query: ({ userTypeId, steps }) => ({
        url: `/admin/onboarding-steps/user-type/${userTypeId}/reorder`,
        method: 'POST',
        body: { steps },
      }),
      invalidatesTags: (_result, _error, { userTypeId }) => [
        { type: 'OnboardingStep', id: `USER_TYPE_${userTypeId}` },
      ],
    }),
  }),
})

export const {
  useGetOnboardingStatusQuery,
  useGetMyUserTypesQuery,
  useStartOnboardingMutation,
  useSubmitOnboardingStepMutation,
  useSendPhoneOtpMutation,
  useVerifyPhoneOtpMutation,
  useGetActiveUserTypesQuery,
  useGetSubmissionsQuery,
  useGetPendingReviewsQuery,
  useGetSubmissionDetailsQuery,
  useApproveSubmissionMutation,
  useRejectSubmissionMutation,
  // Change request hooks
  useRequestChangeMutation,
  useGetReviewCommentsQuery,
  useAddReviewCommentMutation,
  useRespondToChangeRequestMutation,
  useResubmitForReviewMutation,
  useWithdrawOnboardingMutation,
  useGetMyReviewCommentsQuery,
  // Admin hooks
  useGetAdminUserTypesQuery,
  useGetAdminUserTypeQuery,
  useCreateUserTypeMutation,
  useUpdateUserTypeMutation,
  useDeleteUserTypeMutation,
  useGetAdminOnboardingStepsQuery,
  useGetAdminOnboardingStepQuery,
  useCreateOnboardingStepMutation,
  useUpdateOnboardingStepMutation,
  useDeleteOnboardingStepMutation,
  useReorderOnboardingStepsMutation,
} = onboardingApi
