/**
 * SSO API Unit Tests
 *
 * Tests the SSO RTK Query endpoints and state management
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'
import { createTestStore, type TestStore } from '@/test/utils'
import { Provider } from 'react-redux'
import {
  useGetEnabledSSOProvidersQuery,
  useLazyInitiateSSOLoginQuery,
  useLazyHandleSSOCallbackQuery,
} from '@/features/auth/ssoApi'
import { tokens } from '@/test/fixtures'
import type { ReactNode } from 'react'

describe('SSO API Tests', () => {
  let store: TestStore

  beforeEach(() => {
    store = createTestStore()
  })

  const wrapper = ({ children }: { children: ReactNode }) => (
    <Provider store={store}>{children}</Provider>
  )

  describe('useGetEnabledSSOProvidersQuery', () => {
    it('fetches enabled SSO providers successfully', async () => {
      server.use(
        http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
          return HttpResponse.json({
            providers: ['google'],
          })
        })
      )

      const { result } = renderHook(() => useGetEnabledSSOProvidersQuery({ orgSlug: 'acme' }), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual({
        providers: ['google'],
      })
    })

    it('returns empty array when no providers are enabled', async () => {
      server.use(
        http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
          return HttpResponse.json({
            providers: [],
          })
        })
      )

      const { result } = renderHook(() => useGetEnabledSSOProvidersQuery({ orgSlug: 'acme' }), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.providers).toEqual([])
    })

    it('handles error when fetching enabled providers fails', async () => {
      server.use(
        http.get(`${API_BASE}/organization-sso-settings/enabled-providers`, () => {
          return HttpResponse.json(
            { detail: 'SSO settings not found' },
            { status: 404 }
          )
        })
      )

      const { result } = renderHook(() => useGetEnabledSSOProvidersQuery({ orgSlug: 'acme' }), {
        wrapper,
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })
    })
  })

  describe('useLazyInitiateSSOLoginQuery', () => {
    it('generates Google SSO authorization URL', async () => {
      const authUrl = 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test'

      server.use(
        http.get(`${API_BASE}/sso/google/authorize`, () => {
          return HttpResponse.json({
            authorization_url: authUrl,
          })
        })
      )

      const { result } = renderHook(() => useLazyInitiateSSOLoginQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      const response = await trigger({
        provider: 'google',
        orgSlug: 'acme',
      })

      expect(response.data?.authorization_url).toBe(authUrl)
    })

    it('handles error when SSO provider is not enabled', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/authorize`, () => {
          return HttpResponse.json(
            { detail: 'Google SSO is not enabled for this organization' },
            { status: 403 }
          )
        })
      )

      const { result } = renderHook(() => useLazyInitiateSSOLoginQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      const response = await trigger({
        provider: 'google',
        orgSlug: 'acme',
      })

      expect(response.error).toBeDefined()
    })
  })

  describe('useLazyHandleSSOCallbackQuery', () => {
    it('handles SSO callback and returns tokens', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
          })
        })
      )

      const { result } = renderHook(() => useLazyHandleSSOCallbackQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      const response = await trigger({
        provider: 'google',
        code: 'test-auth-code',
        state: 'test-state-token',
      })

      // Type guard for success response
      expect(response.data).toBeDefined()
      expect('access_token' in response.data!).toBe(true)
      if ('access_token' in response.data!) {
        expect(response.data.access_token).toBe(tokens.validAccessToken)
      }
    })

    it('handles SSO callback error', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () => {
          return HttpResponse.json(
            { detail: 'Invalid authorization code' },
            { status: 400 }
          )
        })
      )

      const { result } = renderHook(() => useLazyHandleSSOCallbackQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      const response = await trigger({
        provider: 'google',
        code: 'invalid-code',
        state: 'test-state-token',
      })

      expect(response.error).toBeDefined()
    })

    it('stores token after successful SSO callback', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
          })
        })
      )

      const { result } = renderHook(() => useLazyHandleSSOCallbackQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      await trigger({
        provider: 'google',
        code: 'test-auth-code',
        state: 'test-state-token',
      })

      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.token).toBe(tokens.validAccessToken)
        expect(state.auth.isAuthenticated).toBe(true)
      })
    })
  })

  describe('SSO State Management', () => {
    it('updates auth state after successful SSO callback', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
          })
        })
      )

      const { result } = renderHook(() => useLazyHandleSSOCallbackQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      await trigger({
        provider: 'google',
        code: 'test-auth-code',
        state: 'test-state-token',
      })

      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.sso.isLoading).toBe(false)
        expect(state.auth.sso.error).toBeNull()
        expect(state.auth.isAuthenticated).toBe(true)
      })
    })

    it('sets error state on SSO callback failure', async () => {
      server.use(
        http.get(`${API_BASE}/sso/google/callback`, () => {
          return HttpResponse.json(
            { detail: 'SSO authentication failed' },
            { status: 400 }
          )
        })
      )

      const { result } = renderHook(() => useLazyHandleSSOCallbackQuery(), {
        wrapper,
      })

      const [trigger] = result.current

      await trigger({
        provider: 'google',
        code: 'invalid-code',
        state: 'test-state-token',
      })

      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.sso.isLoading).toBe(false)
        expect(state.auth.sso.error).toBeDefined()
      })
    })
  })
})
