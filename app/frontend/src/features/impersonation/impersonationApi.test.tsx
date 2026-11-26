/**
 * Impersonation API Tests
 *
 * Tests the RTK Query endpoints for impersonation features,
 * specifically the user's impersonation history endpoint.
 */

import type { ReactNode } from 'react'
import { describe, it, expect, beforeEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { Provider } from 'react-redux'
import { renderHook, waitFor } from '@testing-library/react'
import { server, setCurrentUser } from '@/test/server'
import { API_BASE } from '@/test/handlers'
import { regularUser } from '@/test/fixtures'
import { createTestStore } from '@/test/utils'
import { useGetMyImpersonationHistoryQuery } from './impersonationApi'
import type { MyImpersonationHistoryResponse, MyImpersonationHistoryItem } from '@/types/impersonation'

function createWrapper() {
  const store = createTestStore()
  return function Wrapper({ children }: { children: ReactNode }) {
    return <Provider store={store}>{children}</Provider>
  }
}

describe('impersonationApi', () => {

  const mockImpersonationHistoryItem: MyImpersonationHistoryItem = {
    id: 'session-1',
    created_time: '2024-01-15T10:00:00Z',
    ended_time: '2024-01-15T10:30:00Z',
    impersonator: {
      id: 'admin-user-id',
      email: 'admin@example.com',
      first_name: 'Admin',
      last_name: 'User',
    },
  }

  const mockEmptyResponse: MyImpersonationHistoryResponse = {
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  }

  const mockHistoryResponse: MyImpersonationHistoryResponse = {
    items: [mockImpersonationHistoryItem],
    total: 1,
    limit: 50,
    offset: 0,
  }

  beforeEach(() => {
    setCurrentUser(regularUser)
  })

  describe('useGetMyImpersonationHistoryQuery', () => {
    it('should fetch impersonation history successfully', async () => {
      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, () => {
          return HttpResponse.json(mockHistoryResponse)
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual(mockHistoryResponse)
      expect(result.current.data?.items).toHaveLength(1)
      expect(result.current.data?.items[0].impersonator.email).toBe('admin@example.com')
    })

    it('should return empty list when user has no impersonation history', async () => {
      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, () => {
          return HttpResponse.json(mockEmptyResponse)
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.items).toHaveLength(0)
      expect(result.current.data?.total).toBe(0)
    })

    it('should pass pagination parameters correctly', async () => {
      let capturedUrl = ''

      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, ({ request }) => {
          capturedUrl = request.url
          return HttpResponse.json(mockHistoryResponse)
        })
      )

      const { result } = renderHook(
        () => useGetMyImpersonationHistoryQuery({ limit: 10, offset: 20 }),
        { wrapper: createWrapper() }
      )

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(capturedUrl).toContain('limit=10')
      expect(capturedUrl).toContain('offset=20')
    })

    it('should handle 401 unauthorized error', async () => {
      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, () => {
          return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error).toBeDefined()
    })

    it('should include all impersonator details in response', async () => {
      const itemWithFullDetails: MyImpersonationHistoryItem = {
        id: 'session-2',
        created_time: '2024-01-16T09:00:00Z',
        ended_time: '2024-01-16T09:45:00Z',
        impersonator: {
          id: 'super-admin-id',
          email: 'superadmin@company.com',
          first_name: 'Super',
          last_name: 'Admin',
        },
      }

      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, () => {
          return HttpResponse.json({
            items: [itemWithFullDetails],
            total: 1,
            limit: 50,
            offset: 0,
          })
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      const session = result.current.data?.items[0]
      expect(session?.id).toBe('session-2')
      expect(session?.created_time).toBe('2024-01-16T09:00:00Z')
      expect(session?.ended_time).toBe('2024-01-16T09:45:00Z')
      expect(session?.impersonator.id).toBe('super-admin-id')
      expect(session?.impersonator.email).toBe('superadmin@company.com')
      expect(session?.impersonator.first_name).toBe('Super')
      expect(session?.impersonator.last_name).toBe('Admin')
    })

    it('should handle multiple impersonation items', async () => {
      const multipleSessions: MyImpersonationHistoryItem[] = [
        {
          id: 'session-1',
          created_time: '2024-01-17T10:00:00Z',
          ended_time: '2024-01-17T10:15:00Z',
          impersonator: {
            id: 'admin-1',
            email: 'admin1@example.com',
            first_name: 'Admin',
            last_name: 'One',
          },
        },
        {
          id: 'session-2',
          created_time: '2024-01-16T14:00:00Z',
          ended_time: '2024-01-16T14:30:00Z',
          impersonator: {
            id: 'admin-2',
            email: 'admin2@example.com',
            first_name: 'Admin',
            last_name: 'Two',
          },
        },
      ]

      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, () => {
          return HttpResponse.json({
            items: multipleSessions,
            total: 2,
            limit: 50,
            offset: 0,
          })
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.items).toHaveLength(2)
      expect(result.current.data?.total).toBe(2)
    })

    it('should work without pagination parameters', async () => {
      let capturedUrl = ''

      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, ({ request }) => {
          capturedUrl = request.url
          return HttpResponse.json(mockEmptyResponse)
        })
      )

      const { result } = renderHook(() => useGetMyImpersonationHistoryQuery(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      // Should not have query parameters when none provided
      expect(capturedUrl).not.toContain('limit=')
      expect(capturedUrl).not.toContain('offset=')
    })
  })
})
