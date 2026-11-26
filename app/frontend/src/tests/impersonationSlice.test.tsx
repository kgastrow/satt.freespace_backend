/**
 * Impersonation Slice Unit Tests
 *
 * Tests the impersonation Redux slice and API endpoints
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'
import { createTestStore, type TestStore } from '@/test/utils'
import { Provider } from 'react-redux'
import {
  useStartImpersonationMutation,
  useEndImpersonationMutation,
} from '@/features/impersonation/impersonationApi'
import { clearImpersonation } from '@/features/impersonation/impersonationSlice'
import { tokens } from '@/test/fixtures'
import type { ReactNode } from 'react'

describe('Impersonation Slice Tests', () => {
  let store: TestStore

  beforeEach(() => {
    // Clear storage before each test
    sessionStorage.clear()
    localStorage.clear()

    // Create store with authenticated admin user
    store = createTestStore({
      auth: {
        user: {
          id: 'admin-123',
          email: 'admin@example.com',
          first_name: 'Admin',
          last_name: 'User',
          organization_id: 'org-123',
          is_admin: true,
        },
        token: tokens.validAccessToken,
        isAuthenticated: true,
        isLoading: false,
        sso: {
          isLoading: false,
          error: null,
          selectedProvider: null,
        },
      twoFactor: { required: false, token: null },
      twoFactorSetupRequired: false,
      enforcementActive: false,
      },
    })

    // Set tokens in storage
    sessionStorage.setItem('access_token', tokens.validAccessToken)
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>{children}</Provider>
  )

  describe('useStartImpersonationMutation', () => {
    it('starts impersonation successfully', async () => {
      const impersonationToken = 'impersonation-token-123'

      server.use(
        http.post(`${API_BASE}/admin/impersonate/user-456`, () => {
          return HttpResponse.json({
            impersonation_token: impersonationToken,
            session: {
              id: 'session-123',
              created_time: '2024-01-01T00:00:00Z',
              impersonator_id: 'admin-123',
              target_user_id: 'user-456',
              target_organization_id: 'org-456',
              ended_time: null,
              ip_address: '127.0.0.1',
              user_agent: 'test-agent',
            },
            message: 'Impersonation started successfully',
          })
        })
      )

      const { result } = renderHook(() => useStartImpersonationMutation(), {
        wrapper,
      })

      const [startImpersonation] = result.current

      const response = await startImpersonation('user-456')

      expect(response.data).toBeDefined()
      expect(response.data?.impersonation_token).toBe(impersonationToken)
      expect(response.data?.session.id).toBe('session-123')

      // Verify impersonation state
      await waitFor(() => {
        const state = store.getState()
        expect(state.impersonation.isImpersonating).toBe(true)
        expect(state.impersonation.sessionId).toBe('session-123')
        // targetUser is null in state - it comes from auth state after token swap
        expect(state.impersonation.targetUser).toBeNull()
        // Original tokens are no longer stored (in-memory only, no persistence)
        expect(state.impersonation.originalToken).toBeNull()
        expect(state.impersonation.originalRefreshToken).toBeNull()
      })
    })

    it('handles error when impersonation fails', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/user-456`, () => {
          return HttpResponse.json(
            { detail: 'Cannot impersonate super admin users' },
            { status: 403 }
          )
        })
      )

      const { result } = renderHook(() => useStartImpersonationMutation(), {
        wrapper,
      })

      const [startImpersonation] = result.current

      const response = await startImpersonation('user-456')

      expect(response.error).toBeDefined()

      // Verify impersonation state remains unchanged
      const state = store.getState()
      expect(state.impersonation.isImpersonating).toBe(false)
    })

    it('does not persist tokens to storage (in-memory only)', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/user-456`, () => {
          return HttpResponse.json({
            impersonation_token: 'impersonation-token',
            session: {
              id: 'session-123',
              created_time: '2024-01-01T00:00:00Z',
              impersonator_id: 'admin-123',
              target_user_id: 'user-456',
              target_organization_id: 'org-456',
              ended_time: null,
              ip_address: '127.0.0.1',
              user_agent: 'test-agent',
            },
            message: 'Impersonation started successfully',
          })
        })
      )

      const { result } = renderHook(() => useStartImpersonationMutation(), {
        wrapper,
      })

      const [startImpersonation] = result.current

      await startImpersonation('user-456')

      await waitFor(() => {
        // Tokens should NOT be in storage (cookie-based auth, in-memory only)
        expect(sessionStorage.getItem('original_token')).toBeNull()
      })
    })
  })

  describe('useEndImpersonationMutation', () => {
    beforeEach(() => {
      // Set up impersonation state
      store = createTestStore({
        auth: {
          user: {
            id: 'user-456',
            email: 'user@example.com',
            first_name: 'Target',
            last_name: 'User',
            organization_id: 'org-456',
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: {
            isLoading: false,
            error: null,
            selectedProvider: null,
          },
        twoFactor: { required: false, token: null },
        twoFactorSetupRequired: false,
        enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: {
            id: 'admin-123',
            email: 'admin@example.com',
            first_name: 'Admin',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: true,
          },
          targetUser: {
            id: 'user-456',
            email: 'user@example.com',
            first_name: 'Target',
            last_name: 'User',
            organization_id: 'org-456',
            is_admin: false,
          },
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T00:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

    })

    it('ends impersonation successfully', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            session: {
              id: 'session-123',
              created_time: '2024-01-01T00:00:00Z',
              impersonator_id: 'admin-123',
              target_user_id: 'user-456',
              target_organization_id: 'org-456',
              ended_time: '2024-01-01T01:00:00Z',
              ip_address: '127.0.0.1',
              user_agent: 'test-agent',
            },
            message: 'Impersonation ended successfully',
          })
        })
      )

      const { result } = renderHook(() => useEndImpersonationMutation(), {
        wrapper,
      })

      const [endImpersonation] = result.current

      const response = await endImpersonation()

      expect(response.data).toBeDefined()
      expect(response.data?.access_token).toBe(tokens.validAccessToken)

      // Verify impersonation state is cleared
      await waitFor(() => {
        const state = store.getState()
        expect(state.impersonation.isImpersonating).toBe(false)
        expect(state.impersonation.sessionId).toBeNull()
        expect(state.impersonation.targetUser).toBeNull()
        expect(state.impersonation.originalUser).toBeNull()
        expect(state.impersonation.originalToken).toBeNull()
        expect(state.impersonation.originalRefreshToken).toBeNull()
      })
    })

    it('clears impersonation state from storage', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            session: {
              id: 'session-123',
              created_time: '2024-01-01T00:00:00Z',
              impersonator_id: 'admin-123',
              target_user_id: 'user-456',
              target_organization_id: 'org-456',
              ended_time: '2024-01-01T01:00:00Z',
              ip_address: '127.0.0.1',
              user_agent: 'test-agent',
            },
            message: 'Impersonation ended successfully',
          })
        })
      )

      const { result } = renderHook(() => useEndImpersonationMutation(), {
        wrapper,
      })

      const [endImpersonation] = result.current

      await endImpersonation()

      await waitFor(() => {
        expect(sessionStorage.getItem('original_token')).toBeNull()
      })
    })

    it('handles error when ending impersonation fails', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, () => {
          return HttpResponse.json(
            { detail: 'No active impersonation session' },
            { status: 400 }
          )
        })
      )

      const { result } = renderHook(() => useEndImpersonationMutation(), {
        wrapper,
      })

      const [endImpersonation] = result.current

      const response = await endImpersonation()

      expect(response.error).toBeDefined()
    })
  })

  describe('clearImpersonation action', () => {
    it('clears impersonation state', () => {
      // Set up impersonation state
      store = createTestStore({
        impersonation: {
          isImpersonating: true,
          originalUser: {
            id: 'admin-123',
            email: 'admin@example.com',
            first_name: 'Admin',
            last_name: 'User',
            organization_id: 'org-123',
            is_admin: true,
          },
          targetUser: {
            id: 'user-456',
            email: 'user@example.com',
            first_name: 'Target',
            last_name: 'User',
            organization_id: 'org-456',
            is_admin: false,
          },
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T00:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      store.dispatch(clearImpersonation())

      const state = store.getState()
      expect(state.impersonation.isImpersonating).toBe(false)
      expect(state.impersonation.sessionId).toBeNull()
      expect(state.impersonation.targetUser).toBeNull()
      expect(state.impersonation.originalUser).toBeNull()
      expect(state.impersonation.originalToken).toBeNull()
      expect(state.impersonation.originalRefreshToken).toBeNull()
    })
  })
})
