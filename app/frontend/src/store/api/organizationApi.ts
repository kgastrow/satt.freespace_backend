import { api } from '@/store/api'

export interface GetOrganizationDetailsResponse {
  id: string
  name: string
  slug: string
  display_name: string | null
  physical_address_line1: string | null
  physical_address_line2: string | null
  city: string | null
  state_province: string | null
  postal_code: string | null
  country: string | null
  contact_email: string | null
  contact_phone: string | null
  logo_file_id: string | null
}

export interface UpdateOrganizationDetailsRequest {
  display_name?: string | null
  physical_address_line1?: string | null
  physical_address_line2?: string | null
  city?: string | null
  state_province?: string | null
  postal_code?: string | null
  country?: string | null
  contact_email?: string | null
  contact_phone?: string | null
  logo_file_id?: string | null
}

export const organizationApi = api.injectEndpoints({
  endpoints: (builder) => ({
    /**
     * GET /organizations/{organization_id}/details - Get organization details
     */
    getOrganizationDetails: builder.query<
      GetOrganizationDetailsResponse,
      string
    >({
      query: (organizationId) => `/organizations/${organizationId}/details`,
      providesTags: (_result, _error, organizationId) => [
        { type: 'Organization', id: organizationId },
      ],
    }),

    /**
     * PATCH /organizations/{organization_id}/details - Update organization details
     */
    updateOrganizationDetails: builder.mutation<
      GetOrganizationDetailsResponse,
      { organizationId: string; data: UpdateOrganizationDetailsRequest }
    >({
      query: ({ organizationId, data }) => ({
        url: `/organizations/${organizationId}/details`,
        method: 'PATCH',
        body: data,
      }),
      invalidatesTags: (_result, _error, { organizationId }) => [
        { type: 'Organization', id: organizationId },
      ],
    }),
  }),
})

export const {
  useGetOrganizationDetailsQuery,
  useUpdateOrganizationDetailsMutation,
} = organizationApi
