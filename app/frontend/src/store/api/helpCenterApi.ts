import { api } from '@/store/api'
import type {
  HelpCategory,
  HelpCategoryListResponse,
  HelpCategoryListParams,
  HelpCategoryCreateRequest,
  HelpCategoryUpdateRequest,
  HelpArticle,
  HelpArticleListResponse,
  HelpArticleListParams,
  HelpArticleCreateRequest,
  HelpArticleUpdateRequest,
  HelpFaq,
  HelpFaqListResponse,
  HelpFaqListParams,
  HelpFaqCreateRequest,
  HelpFaqUpdateRequest,
  HelpSearchResponse,
  HelpSearchParams,
  HelpDeleteResponse,
  ReorderRequest,
  ReorderResponse,
} from '@/types/helpCenter'

export const helpCenterApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /help/categories - Get all help categories
     */
    getHelpCategories: builder.query<HelpCategoryListResponse, HelpCategoryListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/help/categories${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'HelpCategory' as const,
                id,
              })),
              { type: 'HelpCategory', id: 'LIST' },
            ]
          : [{ type: 'HelpCategory', id: 'LIST' }],
    }),

    /**
     * GET /help/articles - Get published help articles
     */
    getArticles: builder.query<HelpArticleListResponse, HelpArticleListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.category_id) {
          searchParams.append('category_id', params.category_id)
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/help/articles${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'HelpArticle' as const,
                id,
              })),
              { type: 'HelpArticle', id: 'LIST' },
            ]
          : [{ type: 'HelpArticle', id: 'LIST' }],
    }),

    /**
     * GET /help/articles/{slug} - Get a published help article by slug
     */
    getArticleBySlug: builder.query<HelpArticle, string>({
      query: (slug) => `/help/articles/${slug}`,
      providesTags: (result) =>
        result ? [{ type: 'HelpArticle', id: result.id }] : [],
    }),

    /**
     * GET /help/faqs - Get published FAQs
     */
    getFaqs: builder.query<HelpFaqListResponse, HelpFaqListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.category_id) {
          searchParams.append('category_id', params.category_id)
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/help/faqs${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'HelpFaq' as const,
                id,
              })),
              { type: 'HelpFaq', id: 'LIST' },
            ]
          : [{ type: 'HelpFaq', id: 'LIST' }],
    }),

    /**
     * GET /help/search - Search help articles and FAQs
     */
    searchHelp: builder.query<HelpSearchResponse, HelpSearchParams>({
      query: ({ q }) => `/help/search?q=${encodeURIComponent(q)}`,
      providesTags: ['HelpArticle', 'HelpFaq'],
    }),

    // ============================================================================
    // Admin endpoints
    // ============================================================================

    /**
     * POST /help/admin/categories - Create a help category
     */
    createCategory: builder.mutation<HelpCategory, HelpCategoryCreateRequest>({
      query: (body) => ({
        url: '/help/admin/categories',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'HelpCategory', id: 'LIST' }],
    }),

    /**
     * PUT /help/admin/categories/{categoryId} - Update a help category
     */
    updateCategory: builder.mutation<
      HelpCategory,
      { id: string; body: HelpCategoryUpdateRequest }
    >({
      query: ({ id, body }) => ({
        url: `/help/admin/categories/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'HelpCategory', id },
        { type: 'HelpCategory', id: 'LIST' },
      ],
    }),

    /**
     * DELETE /help/admin/categories/{categoryId} - Soft delete a help category
     */
    deleteCategory: builder.mutation<HelpDeleteResponse, string>({
      query: (id) => ({
        url: `/help/admin/categories/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'HelpCategory', id },
        { type: 'HelpCategory', id: 'LIST' },
      ],
    }),

    /**
     * GET /help/admin/articles - List all help articles (admin view)
     */
    getAdminArticles: builder.query<HelpArticleListResponse, HelpArticleListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.category_id) {
          searchParams.append('category_id', params.category_id)
        }
        if (params?.status) {
          searchParams.append('status', params.status)
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/help/admin/articles${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'HelpArticle' as const,
                id,
              })),
              { type: 'HelpArticle', id: 'ADMIN_LIST' },
            ]
          : [{ type: 'HelpArticle', id: 'ADMIN_LIST' }],
    }),

    /**
     * GET /help/admin/articles/{articleId} - Get a help article by ID (admin view)
     */
    getAdminArticle: builder.query<HelpArticle, string>({
      query: (id) => `/help/admin/articles/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'HelpArticle', id }],
    }),

    /**
     * POST /help/admin/articles - Create a help article
     */
    createArticle: builder.mutation<HelpArticle, HelpArticleCreateRequest>({
      query: (body) => ({
        url: '/help/admin/articles',
        method: 'POST',
        body,
      }),
      invalidatesTags: [
        { type: 'HelpArticle', id: 'LIST' },
        { type: 'HelpArticle', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * PUT /help/admin/articles/{articleId} - Update a help article
     */
    updateArticle: builder.mutation<
      HelpArticle,
      { id: string; body: HelpArticleUpdateRequest }
    >({
      query: ({ id, body }) => ({
        url: `/help/admin/articles/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'HelpArticle', id },
        { type: 'HelpArticle', id: 'LIST' },
        { type: 'HelpArticle', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * DELETE /help/admin/articles/{articleId} - Soft delete a help article
     */
    deleteArticle: builder.mutation<HelpDeleteResponse, string>({
      query: (id) => ({
        url: `/help/admin/articles/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'HelpArticle', id },
        { type: 'HelpArticle', id: 'LIST' },
        { type: 'HelpArticle', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * GET /help/admin/faqs - List all FAQs (admin view)
     */
    getAdminFaqs: builder.query<HelpFaqListResponse, HelpFaqListParams | void>({
      query: (params) => {
        const searchParams = new URLSearchParams()
        if (params?.category_id) {
          searchParams.append('category_id', params.category_id)
        }
        if (params?.status) {
          searchParams.append('status', params.status)
        }
        if (params?.limit) {
          searchParams.append('limit', params.limit.toString())
        }
        if (params?.offset) {
          searchParams.append('offset', params.offset.toString())
        }
        const queryString = searchParams.toString()
        return `/help/admin/faqs${queryString ? `?${queryString}` : ''}`
      },
      providesTags: (result) =>
        result
          ? [
              ...result.items.map(({ id }) => ({
                type: 'HelpFaq' as const,
                id,
              })),
              { type: 'HelpFaq', id: 'ADMIN_LIST' },
            ]
          : [{ type: 'HelpFaq', id: 'ADMIN_LIST' }],
    }),

    /**
     * GET /help/admin/faqs/{faqId} - Get a FAQ by ID (admin view)
     */
    getAdminFaq: builder.query<HelpFaq, string>({
      query: (id) => `/help/admin/faqs/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'HelpFaq', id }],
    }),

    /**
     * POST /help/admin/faqs - Create a FAQ
     */
    createFaq: builder.mutation<HelpFaq, HelpFaqCreateRequest>({
      query: (body) => ({
        url: '/help/admin/faqs',
        method: 'POST',
        body,
      }),
      invalidatesTags: [
        { type: 'HelpFaq', id: 'LIST' },
        { type: 'HelpFaq', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * PUT /help/admin/faqs/{faqId} - Update a FAQ
     */
    updateFaq: builder.mutation<HelpFaq, { id: string; body: HelpFaqUpdateRequest }>({
      query: ({ id, body }) => ({
        url: `/help/admin/faqs/${id}`,
        method: 'PUT',
        body,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'HelpFaq', id },
        { type: 'HelpFaq', id: 'LIST' },
        { type: 'HelpFaq', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * DELETE /help/admin/faqs/{faqId} - Soft delete a FAQ
     */
    deleteFaq: builder.mutation<HelpDeleteResponse, string>({
      query: (id) => ({
        url: `/help/admin/faqs/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'HelpFaq', id },
        { type: 'HelpFaq', id: 'LIST' },
        { type: 'HelpFaq', id: 'ADMIN_LIST' },
      ],
    }),

    // ============================================================================
    // Reorder endpoints
    // ============================================================================

    /**
     * PUT /help/admin/articles/reorder - Reorder help articles
     */
    reorderArticles: builder.mutation<ReorderResponse, ReorderRequest>({
      query: (body) => ({
        url: '/help/admin/articles/reorder',
        method: 'PUT',
        body,
      }),
      invalidatesTags: [
        { type: 'HelpArticle', id: 'LIST' },
        { type: 'HelpArticle', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * PUT /help/admin/faqs/reorder - Reorder FAQs
     */
    reorderFaqs: builder.mutation<ReorderResponse, ReorderRequest>({
      query: (body) => ({
        url: '/help/admin/faqs/reorder',
        method: 'PUT',
        body,
      }),
      invalidatesTags: [
        { type: 'HelpFaq', id: 'LIST' },
        { type: 'HelpFaq', id: 'ADMIN_LIST' },
      ],
    }),

    /**
     * PUT /help/admin/categories/reorder - Reorder categories
     */
    reorderCategories: builder.mutation<ReorderResponse, ReorderRequest>({
      query: (body) => ({
        url: '/help/admin/categories/reorder',
        method: 'PUT',
        body,
      }),
      invalidatesTags: [{ type: 'HelpCategory', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetHelpCategoriesQuery,
  useGetArticlesQuery,
  useGetArticleBySlugQuery,
  useGetFaqsQuery,
  useSearchHelpQuery,
  useCreateCategoryMutation,
  useUpdateCategoryMutation,
  useDeleteCategoryMutation,
  useGetAdminArticlesQuery,
  useGetAdminArticleQuery,
  useCreateArticleMutation,
  useUpdateArticleMutation,
  useDeleteArticleMutation,
  useGetAdminFaqsQuery,
  useGetAdminFaqQuery,
  useCreateFaqMutation,
  useUpdateFaqMutation,
  useDeleteFaqMutation,
  useReorderArticlesMutation,
  useReorderFaqsMutation,
  useReorderCategoriesMutation,
} = helpCenterApi
