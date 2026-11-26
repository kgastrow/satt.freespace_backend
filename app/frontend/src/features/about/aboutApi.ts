import { api } from '@/store/api'

export type AboutContentType = 'plain' | 'html'

export interface AboutContentResponse {
  content: string
  content_type: AboutContentType
}

export interface UpdateAboutContentRequest {
  content: string
  content_type: AboutContentType
}

export interface UpdateAboutContentResponse {
  message: string
  message_code: string
  about: AboutContentResponse
}

export const aboutApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /about - Get about page content (authenticated users)
     */
    getAboutContent: builder.query<AboutContentResponse, void>({
      query: () => '/about',
      providesTags: ['About'],
    }),

    /**
     * PUT /about - Update about page content (super admin only)
     */
    updateAboutContent: builder.mutation<UpdateAboutContentResponse, UpdateAboutContentRequest>({
      query: (body) => ({
        url: '/about',
        method: 'PUT',
        body,
      }),
      invalidatesTags: ['About'],
    }),
  }),
})

export const { useGetAboutContentQuery, useUpdateAboutContentMutation } = aboutApi
