import { api } from '@/store/api'
import type {
  IngestKeyListResponse,
  CreateIngestKeyRequest,
  CreateIngestKeyResponse,
  RevokeIngestKeyResponse,
  AppKeyListResponse,
  CreateAppKeyRequest,
  CreateAppKeyResponse,
  RevokeAppKeyResponse,
} from '@/types/site'

/**
 * Ingest keys (per site) and app keys (deployment-wide, super admin only).
 * The plaintext key is only ever in the create response.
 */
export const keysApi = api.injectEndpoints({
  endpoints: (builder) => ({
    getIngestKeys: builder.query<IngestKeyListResponse, string>({
      query: (siteId) => `/admin/sites/${siteId}/ingest-keys`,
      providesTags: (_r, _e, siteId) => [{ type: 'IngestKey', id: siteId }],
    }),

    createIngestKey: builder.mutation<
      CreateIngestKeyResponse,
      { siteId: string; data: CreateIngestKeyRequest }
    >({
      query: ({ siteId, data }) => ({
        url: `/admin/sites/${siteId}/ingest-keys`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'IngestKey', id: siteId }],
    }),

    revokeIngestKey: builder.mutation<
      RevokeIngestKeyResponse,
      { siteId: string; keyId: string }
    >({
      query: ({ siteId, keyId }) => ({
        url: `/admin/sites/${siteId}/ingest-keys/${keyId}/revoke`,
        method: 'POST',
      }),
      invalidatesTags: (_r, _e, { siteId }) => [{ type: 'IngestKey', id: siteId }],
    }),

    getAppKeys: builder.query<AppKeyListResponse, void>({
      query: () => '/admin/app-keys',
      providesTags: [{ type: 'AppKey', id: 'LIST' }],
    }),

    createAppKey: builder.mutation<CreateAppKeyResponse, CreateAppKeyRequest>({
      query: (body) => ({ url: '/admin/app-keys', method: 'POST', body }),
      invalidatesTags: [{ type: 'AppKey', id: 'LIST' }],
    }),

    revokeAppKey: builder.mutation<RevokeAppKeyResponse, string>({
      query: (keyId) => ({ url: `/admin/app-keys/${keyId}/revoke`, method: 'POST' }),
      invalidatesTags: [{ type: 'AppKey', id: 'LIST' }],
    }),
  }),
})

export const {
  useGetIngestKeysQuery,
  useCreateIngestKeyMutation,
  useRevokeIngestKeyMutation,
  useGetAppKeysQuery,
  useCreateAppKeyMutation,
  useRevokeAppKeyMutation,
} = keysApi
