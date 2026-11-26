/**
 * Organization Management Integration Tests (Super Admin)
 *
 * Tests organization management functionality including:
 * - Soft delete → Hard delete flow
 * - Member management (add/remove members)
 * - Deletion request cancellation
 * - Organization listing and details
 */

import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@/test/utils'
import { server, setCurrentUser, API_BASE } from '@/test/server'
import {
  superAdminUser,
  adminUser,
  createAuthState,
  organizations,
  usersInOrg1,
} from '@/test/fixtures'
import {
  useGetOrganizationsQuery,
  useGetOrganizationQuery,
  useRequestOrganizationDeletionMutation,
  useCancelOrganizationDeletionRequestMutation,
  useGetOrganizationMembersQuery,
  useRemoveOrganizationMemberMutation,
} from '@/features/organizations/organizationsApi'

// Test components
function OrganizationList() {
  const { data, isLoading, error } = useGetOrganizationsQuery({})

  if (isLoading) return <div>Loading...</div>
  if (error) return <div data-testid="org-error">Error loading organizations</div>

  return (
    <div>
      <h2>Organizations</h2>
      <ul>
        {data?.items.map((org) => (
          <li key={org.id} data-testid={`org-${org.id}`}>
            <span data-testid={`org-${org.id}-name`}>{org.name}</span>
            <span data-testid={`org-${org.id}-status`}>
              {org.deletion_requested ? 'Pending Deletion' : org.is_active ? 'Active' : 'Inactive'}
            </span>
          </li>
        ))}
      </ul>
      <div data-testid="org-count">Total: {data?.total}</div>
    </div>
  )
}

function OrganizationDetails({ orgId }: { orgId: string }) {
  const { data, isLoading, error } = useGetOrganizationQuery(orgId)

  if (isLoading) return <div>Loading...</div>
  if (error) return <div data-testid="org-detail-error">Error loading organization</div>

  return (
    <div>
      <h2 data-testid="org-name">{data?.name}</h2>
      <p data-testid="org-slug">Slug: {data?.slug}</p>
      <p data-testid="org-active">Active: {data?.is_active ? 'Yes' : 'No'}</p>
      {data?.deletion_requested && (
        <p data-testid="deletion-requested">
          Deletion requested: {data.deletion_requested_time}
        </p>
      )}
    </div>
  )
}

function OrganizationMembers({ orgId }: { orgId: string }) {
  const { data, isLoading, error } = useGetOrganizationMembersQuery({ id: orgId })

  if (isLoading) return <div>Loading...</div>
  if (error) return <div data-testid="members-error">Error loading members</div>

  return (
    <div>
      <h3>Members</h3>
      <ul>
        {data?.items.map((member) => (
          <li key={member.id} data-testid={`member-${member.id}`}>
            <span data-testid={`member-${member.id}-email`}>{member.email}</span>
          </li>
        ))}
      </ul>
      <div data-testid="member-count">Total: {data?.total}</div>
    </div>
  )
}

describe('Organization Management Integration Tests', () => {
  describe('Organization Listing', () => {
    it('super admin can view all organizations', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationList />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Should show all organizations
      expect(screen.getByTestId('org-org-1')).toBeInTheDocument()
      expect(screen.getByTestId('org-org-2')).toBeInTheDocument()
      expect(screen.getByTestId('org-org-3')).toBeInTheDocument()
      expect(screen.getByTestId('org-count')).toHaveTextContent('Total: 3')
    })

    it('displays organization status correctly', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationList />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Check statuses
      expect(screen.getByTestId('org-org-1-status')).toHaveTextContent('Active')
      expect(screen.getByTestId('org-org-3-status')).toHaveTextContent('Pending Deletion')
    })

    it('regular admin cannot view organization list', async () => {
      setCurrentUser(adminUser)

      render(<OrganizationList />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Should show error
      expect(screen.getByTestId('org-error')).toBeInTheDocument()
    })
  })

  describe('Organization Details', () => {
    it('displays organization details', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationDetails orgId="org-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('org-name')).toHaveTextContent('Acme Corp')
      expect(screen.getByTestId('org-slug')).toHaveTextContent('Slug: acme')
      expect(screen.getByTestId('org-active')).toHaveTextContent('Active: Yes')
    })

    it('shows deletion request status for pending deletion orgs', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationDetails orgId="org-3" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('deletion-requested')).toBeInTheDocument()
    })
  })

  describe('Deletion Request Flow', () => {
    it('requests organization deletion', async () => {
      let deletionRequested = false
      let requestedOrgId: string | null = null

      server.use(
        http.post(`${API_BASE}/organizations/:id/request-deletion`, ({ params }) => {
          deletionRequested = true
          requestedOrgId = params.id as string
          return HttpResponse.json({
            message: 'Deletion request submitted',
            organization_id: params.id,
            deletion_requested_time: new Date().toISOString(),
          })
        })
      )

      // Component that requests deletion
      function RequestDeletion({ orgId }: { orgId: string }) {
        const [requestDeletion, { isLoading, data }] = useRequestOrganizationDeletionMutation()

        return (
          <div>
            <button
              onClick={() => requestDeletion(orgId)}
              disabled={isLoading}
            >
              Request Deletion
            </button>
            {data && <div data-testid="deletion-result">Deletion requested</div>}
          </div>
        )
      }

      setCurrentUser(superAdminUser)

      const { user } = render(<RequestDeletion orgId="org-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(deletionRequested).toBe(true)
      })

      expect(requestedOrgId).toBe('org-1')
    })

    it('cancels deletion request', async () => {
      let cancellationRequested = false
      let cancelledOrgId: string | null = null

      server.use(
        http.delete(`${API_BASE}/organizations/:id/request-deletion`, ({ params }) => {
          cancellationRequested = true
          cancelledOrgId = params.id as string
          return HttpResponse.json({
            message: 'Deletion request cancelled',
            organization_id: params.id,
          })
        })
      )

      // Component that cancels deletion
      function CancelDeletion({ orgId }: { orgId: string }) {
        const [cancelDeletion, { isLoading, data }] = useCancelOrganizationDeletionRequestMutation()

        return (
          <div>
            <button
              onClick={() => cancelDeletion(orgId)}
              disabled={isLoading}
            >
              Cancel Deletion
            </button>
            {data && <div data-testid="cancel-result">Deletion cancelled</div>}
          </div>
        )
      }

      setCurrentUser(superAdminUser)

      const { user } = render(<CancelDeletion orgId="org-3" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(cancellationRequested).toBe(true)
      })

      expect(cancelledOrgId).toBe('org-3')
    })
  })

  describe('Member Management', () => {
    it('displays organization members', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationMembers orgId="org-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Should show members
      expect(screen.getByTestId('member-user-1')).toBeInTheDocument()
      expect(screen.getByTestId('member-user-2')).toBeInTheDocument()
      expect(screen.getByTestId('member-user-3')).toBeInTheDocument()
    })

    it('shows member details', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationMembers orgId="org-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Note: first_name and last_name are not in OrganizationMemberResponse, only email
      expect(screen.getByTestId('member-user-1-email')).toHaveTextContent('user@acme.com')
    })

    it('removes member from organization', async () => {
      let removeRequested = false
      let removedUserId: string | null = null
      let removedFromOrgId: string | null = null

      server.use(
        http.delete(`${API_BASE}/organizations/:orgId/members/:userId`, ({ params }) => {
          removeRequested = true
          removedFromOrgId = params.orgId as string
          removedUserId = params.userId as string
          return HttpResponse.json({
            message: 'Member removed successfully',
          })
        })
      )

      // Component that removes members
      function RemoveMember({ orgId, userId }: { orgId: string; userId: string }) {
        const [removeMember, { isLoading, data }] = useRemoveOrganizationMemberMutation()

        return (
          <div>
            <button
              onClick={() => removeMember({ orgId, userId })}
              disabled={isLoading}
            >
              Remove Member
            </button>
            {data && <div data-testid="remove-result">Member removed</div>}
          </div>
        )
      }

      setCurrentUser(superAdminUser)

      const { user } = render(<RemoveMember orgId="org-1" userId="user-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await user.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(removeRequested).toBe(true)
      })

      expect(removedFromOrgId).toBe('org-1')
      expect(removedUserId).toBe('user-1')
    })

    it('updates member count after removal', async () => {
      let memberCount = 3

      server.use(
        http.get(`${API_BASE}/organizations/:id/members`, () => {
          const members = usersInOrg1.slice(0, memberCount)
          return HttpResponse.json({
            items: members,
            total: memberCount,
            limit: 50,
            offset: 0,
          })
        }),
        http.delete(`${API_BASE}/organizations/:orgId/members/:userId`, () => {
          memberCount--
          return HttpResponse.json({
            message: 'Member removed successfully',
          })
        })
      )

      // Component with member list and remove functionality
      function MemberManagement({ orgId }: { orgId: string }) {
        const { data, isLoading, refetch } = useGetOrganizationMembersQuery({ id: orgId })
        const [removeMember] = useRemoveOrganizationMemberMutation()

        const handleRemove = async (userId: string) => {
          await removeMember({ orgId, userId })
          refetch()
        }

        if (isLoading) return <div>Loading...</div>

        return (
          <div>
            <div data-testid="member-count">Members: {data?.total}</div>
            <button onClick={() => handleRemove('user-1')}>Remove User 1</button>
          </div>
        )
      }

      setCurrentUser(superAdminUser)

      const { user } = render(<MemberManagement orgId="org-1" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      // Initial count
      expect(screen.getByTestId('member-count')).toHaveTextContent('Members: 3')

      // Remove a member
      await user.click(screen.getByRole('button'))

      // Count should update after refetch
      await waitFor(() => {
        expect(screen.getByTestId('member-count')).toHaveTextContent('Members: 2')
      })
    })
  })

  describe('Access Control', () => {
    it('regular admin cannot access other organization details', async () => {
      server.use(
        http.get(`${API_BASE}/organizations/:id`, ({ params }) => {
          // Org-2 is not the admin's organization
          if (params.id === 'org-2') {
            return HttpResponse.json({ detail: 'Access denied' }, { status: 403 })
          }
          const org = organizations.find((o) => o.id === params.id)
          return HttpResponse.json(org)
        })
      )

      setCurrentUser(adminUser)

      render(<OrganizationDetails orgId="org-2" />, {
        preloadedState: createAuthState(adminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('org-detail-error')).toBeInTheDocument()
    })

    it('super admin can access any organization details', async () => {
      setCurrentUser(superAdminUser)

      render(<OrganizationDetails orgId="org-2" />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('org-name')).toHaveTextContent('Test Corp')
    })
  })

  describe('Pagination', () => {
    it('paginates organization list', async () => {
      // Create many organizations
      const manyOrgs = Array.from({ length: 15 }, (_, i) => ({
        id: `org-${i + 1}`,
        name: `Organization ${i + 1}`,
        slug: `org-${i + 1}`,
        is_active: true,
        created_time: new Date().toISOString(),
        updated_time: new Date().toISOString(),
        deletion_requested: false,
        deletion_requested_time: null,
      }))

      let lastOffset = 0

      server.use(
        http.get(`${API_BASE}/organizations`, ({ request }) => {
          const url = new URL(request.url)
          const offset = parseInt(url.searchParams.get('offset') || '0')
          const limit = parseInt(url.searchParams.get('limit') || '10')
          lastOffset = offset

          const paginatedOrgs = manyOrgs.slice(offset, offset + limit)

          return HttpResponse.json({
            items: paginatedOrgs,
            total: manyOrgs.length,
            limit,
            offset,
          })
        })
      )

      // Component with pagination
      function PaginatedOrgList() {
        const { data, isLoading } = useGetOrganizationsQuery({ limit: 10, offset: 0 })

        if (isLoading) return <div>Loading...</div>

        return (
          <div>
            <div data-testid="page-count">Showing {data?.items.length} of {data?.total}</div>
          </div>
        )
      }

      setCurrentUser(superAdminUser)

      render(<PaginatedOrgList />, {
        preloadedState: createAuthState(superAdminUser),
      })

      await waitFor(() => {
        expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
      })

      expect(screen.getByTestId('page-count')).toHaveTextContent('Showing 10 of 15')
      expect(lastOffset).toBe(0)
    })
  })
})
