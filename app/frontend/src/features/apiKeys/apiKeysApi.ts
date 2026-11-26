import { api } from '@/store/api'
import type { components } from '@/types/api-generated'

type ApiKeyResponse = components['schemas']['ApiKeyDetailResponse']
type ApiKeyListResponse = components['schemas']['ApiKeyListResponse']
type ApiKeyCreateRequest = components['schemas']['CreateApiKeyRequest']
type ApiKeyUpdateRequest = components['schemas']['UpdateApiKeyRequest']
type ApiKeyWithKeyResponse = components['schemas']['CreateApiKeyResponse']
type AssignablePermissionsResponse = components['schemas']['AssignablePermissionsResponse']

export const apiKeysApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getApiKeys: builder.query<ApiKeyListResponse, { limit?: number; offset?: number } | void>({
      query: (params) => {
        const { limit = 100, offset = 0 } = params || {}
        return `/api-keys?limit=${limit}&offset=${offset}`
      },
      providesTags: (result) =>
        result?.items
          ? [
              ...result.items.map(({ id }) => ({ type: 'ApiKey' as const, id })),
              { type: 'ApiKey', id: 'LIST' },
            ]
          : [{ type: 'ApiKey', id: 'LIST' }],
    }),

    getApiKey: builder.query<ApiKeyResponse, string>({
      query: (id) => `/api-keys/${id}`,
      providesTags: (_result, _error, id) => [{ type: 'ApiKey', id }],
    }),

    createApiKey: builder.mutation<ApiKeyWithKeyResponse, ApiKeyCreateRequest>({
      query: (body) => ({
        url: '/api-keys',
        method: 'POST',
        body,
      }),
      invalidatesTags: [{ type: 'ApiKey', id: 'LIST' }],
    }),

    updateApiKey: builder.mutation<ApiKeyResponse, { id: string; data: ApiKeyUpdateRequest }>({
      query: ({ id, data }) => ({
        url: `/api-keys/${id}`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: (_result, _error, { id }) => [
        { type: 'ApiKey', id },
        { type: 'ApiKey', id: 'LIST' },
      ],
    }),

    deleteApiKey: builder.mutation<{ message: string }, string>({
      query: (id) => ({
        url: `/api-keys/${id}`,
        method: 'DELETE',
      }),
      invalidatesTags: (_result, _error, id) => [
        { type: 'ApiKey', id },
        { type: 'ApiKey', id: 'LIST' },
      ],
    }),

    getAssignablePermissions: builder.query<AssignablePermissionsResponse, void>({
      query: () => '/api-keys/assignable-permissions',
      providesTags: ['Permission'],
    }),
  }),
})

export const {
  useGetApiKeysQuery,
  useGetApiKeyQuery,
  useCreateApiKeyMutation,
  useUpdateApiKeyMutation,
  useDeleteApiKeyMutation,
  useGetAssignablePermissionsQuery,
} = apiKeysApi
