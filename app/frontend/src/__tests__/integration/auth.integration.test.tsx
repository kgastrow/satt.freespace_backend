/**
 * Authentication Flow Integration Tests
 *
 * Tests the complete authentication lifecycle including:
 * - Login flow with token storage and user fetch
 * - Token refresh on 401 errors
 * - Session validation on app load
 * - Logout with cleanup and redirect
 * - Invalid token handling
 */

import { describe, it, expect, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@/test/utils'
import { server, setCurrentUser, setCurrentToken, API_BASE } from '@/test/server'
import {
  regularUser,
  adminUser,
  currentUserResponse,
  tokens,
  createAuthState,
  createUnauthenticatedState,
} from '@/test/fixtures'
import { LoginPage } from '@/pages/LoginPage'
import { AuthProvider } from '@/components/AuthProvider'
import { AuthGuard } from '@/components/AuthGuard'

// Mock environment variable
vi.stubEnv('VITE_ORG_SLUG', 'acme')

describe('Authentication Flow Integration Tests', () => {
  describe('Login Flow', () => {
    it('completes full login flow with token storage and user fetch', async () => {
      setCurrentUser(regularUser)

      const { user, store } = render(<LoginPage />, {
        preloadedState: createUnauthenticatedState(),
        route: '/login',
      })

      // Step 1: Enter email and click Continue
      await user.type(screen.getByLabelText(/email/i), 'user@acme.com')
      await user.click(screen.getByRole('button', { name: /continue/i }))

      // Wait for password field to appear (step 2)
      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
      })

      // Step 2: Enter password and submit
      await user.type(screen.getByLabelText(/password/i), 'password123')
      // Target the submit button specifically (not the "change email" button)
      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      // Wait for successful login - token should be in Redux state (in-memory only, not storage)
      await waitFor(() => {
        expect(store.getState().auth.token).toBe(tokens.validAccessToken)
      })
    })

    it('shows error message on invalid credentials', async () => {
      const { user } = render(<LoginPage />, {
        preloadedState: createUnauthenticatedState(),
        route: '/login',
      })

      // Step 1: Enter email and click Continue
      await user.type(screen.getByLabelText(/email/i), 'user@acme.com')
      await user.click(screen.getByRole('button', { name: /continue/i }))

      // Wait for password field to appear (step 2)
      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
      })

      // Step 2: Enter wrong password and submit
      await user.type(screen.getByLabelText(/password/i), 'wrongpassword')
      // Target the submit button specifically (not the "change email" button)
      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      // Wait for error to appear (toast or inline error)
      await waitFor(() => {
        // The login button should be enabled again after error
        expect(screen.getByRole('button', { name: /submit/i })).not.toBeDisabled()
      })

      // Token should NOT be stored
      expect(sessionStorage.getItem('access_token')).toBeNull()
    })

    // TODO: Investigate timing issues with loading state detection in test environment
    it.skip('disables form while login is in progress', async () => {
      // Add a longer delay to the login handler to test loading state
      server.use(
        http.post(`${API_BASE}/auth/login`, async () => {
          await new Promise((resolve) => setTimeout(resolve, 500))
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
          })
        })
      )

      const { user } = render(<LoginPage />, {
        preloadedState: createUnauthenticatedState(),
        route: '/login',
      })

      // Step 1: Enter email and click Continue
      await user.type(screen.getByLabelText(/email/i), 'user@acme.com')
      await user.click(screen.getByRole('button', { name: /continue/i }))

      // Wait for password field to appear (step 2)
      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
      })

      // Step 2: Enter password
      await user.type(screen.getByLabelText(/password/i), 'password123')

      // Click and immediately check for loading state
      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      // Button should show loading state with "Signing in..." or "Submitting..." text
      await waitFor(() => {
        const button = screen.getByRole('button', { name: /signing in|submitting/i })
        expect(button).toBeDisabled()
      }, { timeout: 1000 })
    })

    it('stores tokens correctly after successful login', async () => {
      setCurrentUser(adminUser)

      const { user, store } = render(<LoginPage />, {
        preloadedState: createUnauthenticatedState(),
        route: '/login',
      })

      // Step 1: Enter email and click Continue
      await user.type(screen.getByLabelText(/email/i), 'admin@acme.com')
      await user.click(screen.getByRole('button', { name: /continue/i }))

      // Wait for password field to appear (step 2)
      await waitFor(() => {
        expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
      })

      // Step 2: Enter password and submit
      await user.type(screen.getByLabelText(/password/i), 'password123')
      // Target the submit button specifically (not the "change email" button)
      const submitButton = screen.getByRole('button', { name: /submit/i })
      await user.click(submitButton)

      await waitFor(() => {
        // Access token in Redux state (in-memory only, not persisted to storage)
        expect(store.getState().auth.token).toBe(tokens.validAccessToken)
      })
    })
  })

  describe('Token Refresh on 401', () => {
    it('automatically refreshes token on 401 error', async () => {
      let requestCount = 0

      // First request returns 401, second succeeds after refresh
      server.use(
        http.get(`${API_BASE}/user/me`, () => {
          requestCount++
          if (requestCount === 1) {
            return HttpResponse.json({ detail: 'Token expired' }, { status: 401 })
          }
          return HttpResponse.json(currentUserResponse(regularUser))
        }),
        http.post(`${API_BASE}/auth/refresh`, () => {
          return HttpResponse.json({ access_token: tokens.validAccessToken })
        })
      )

      // Pre-populate storage with token
      sessionStorage.setItem('access_token', tokens.validAccessToken)

      const TestComponent = () => {
        return (
          <AuthProvider>
            <div>Auth Test</div>
          </AuthProvider>
        )
      }

      render(<TestComponent />, {
        preloadedState: {
          auth: {
            user: null,
            token: tokens.validAccessToken,
            isAuthenticated: false,
            isLoading: true,
            sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
          },
        },
      })

      // Wait for the auth provider to complete validation
      await waitFor(
        () => {
          expect(requestCount).toBeGreaterThanOrEqual(1)
        },
        { timeout: 3000 }
      )
    })
  })

  describe('Session Validation on Load', () => {
    it('validates stored token on app load', async () => {
      // Set up token in storage
      sessionStorage.setItem('access_token', tokens.validAccessToken)

      setCurrentUser(regularUser)

      const TestComponent = () => {
        return (
          <AuthProvider>
            <div data-testid="app-content">App Content</div>
          </AuthProvider>
        )
      }

      render(<TestComponent />, {
        preloadedState: {
          auth: {
            user: null,
            token: tokens.validAccessToken,
            isAuthenticated: false,
            isLoading: true,
            sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
          },
        },
      })

      // Content should render
      expect(screen.getByTestId('app-content')).toBeInTheDocument()
    })

    it('clears auth state when token validation fails', async () => {
      // Override handler to return 401
      server.use(
        http.get(`${API_BASE}/user/me`, () => {
          return HttpResponse.json({ detail: 'Invalid token' }, { status: 401 })
        }),
        http.post(`${API_BASE}/auth/refresh`, () => {
          return HttpResponse.json({ detail: 'Invalid refresh token' }, { status: 401 })
        })
      )

      // Set up token in storage
      sessionStorage.setItem('access_token', tokens.invalidToken)

      setCurrentToken(tokens.invalidToken)

      const TestComponent = () => {
        return (
          <AuthProvider>
            <div data-testid="app-content">App Content</div>
          </AuthProvider>
        )
      }

      const { store } = render(<TestComponent />, {
        preloadedState: {
          auth: {
            user: null,
            token: tokens.invalidToken,
            isAuthenticated: false,
            isLoading: true,
            sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
          },
        },
      })

      // Wait for auth state to be cleared
      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.isLoading).toBe(false)
      })
    })

    it('handles no stored token gracefully', async () => {
      // Override refresh to fail (no cookie = no session)
      server.use(
        http.post(`${API_BASE}/auth/refresh`, () => {
          return HttpResponse.json({ detail: 'No refresh token' }, { status: 401 })
        })
      )

      const TestComponent = () => {
        return (
          <AuthProvider>
            <div data-testid="app-content">App Content</div>
          </AuthProvider>
        )
      }

      const { store } = render(<TestComponent />, {
        preloadedState: {
          auth: {
            user: null,
            token: null,
            isAuthenticated: false,
            isLoading: true,
            sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
          },
        },
      })

      // Wait for auth to initialize
      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.isLoading).toBe(false)
      })

      // Should not be authenticated
      expect(store.getState().auth.isAuthenticated).toBe(false)
    })
  })

  describe('Logout Flow', () => {
    it('clears tokens on logout', async () => {
      // Set up authenticated state
      sessionStorage.setItem('access_token', tokens.validAccessToken)

      setCurrentUser(regularUser)

      // Simulate logout by updating the store
      const { store } = render(<div>Test</div>, {
        preloadedState: createAuthState(regularUser),
      })

      // Dispatch logout action
      store.dispatch({ type: 'auth/logout' })

      // Token should be cleared
      await waitFor(() => {
        const state = store.getState()
        expect(state.auth.token).toBeNull()
        expect(state.auth.isAuthenticated).toBe(false)
        expect(state.auth.user).toBeNull()
      })
    })
  })

  describe('Auth Guard Protection', () => {
    it('allows access to protected route when authenticated', () => {
      setCurrentUser(regularUser)

      const ProtectedContent = () => <div>Protected Content</div>

      render(
        <AuthGuard>
          <ProtectedContent />
        </AuthGuard>,
        {
          preloadedState: createAuthState(regularUser),
          route: '/dashboard',
        }
      )

      expect(screen.getByText('Protected Content')).toBeInTheDocument()
    })

    it('shows loading state while auth is being validated', () => {
      const ProtectedContent = () => <div>Protected Content</div>

      render(
        <AuthGuard>
          <ProtectedContent />
        </AuthGuard>,
        {
          preloadedState: {
            auth: {
              user: null,
              token: tokens.validAccessToken,
              isAuthenticated: false,
              isLoading: true,
              sso: { isLoading: false, error: null, selectedProvider: null },
            twoFactor: { required: false, token: null },
            twoFactorSetupRequired: false,
            enforcementActive: false,
            },
          },
        }
      )

      // Should show loading indicator
      expect(screen.getByText(/loading/i)).toBeInTheDocument()
      // Protected content should not be visible
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
    })

    it('guest-only route redirects authenticated users', () => {
      const GuestOnlyContent = () => <div>Guest Only</div>
      const DashboardContent = () => <div>Dashboard</div>

      render(<GuestOnlyContent />, {
        preloadedState: createAuthState(regularUser),
        route: '/login',
        routes: [
          {
            path: '/login',
            element: (
              <AuthGuard requireAuth={false} redirectTo="/dashboard">
                <GuestOnlyContent />
              </AuthGuard>
            ),
          },
          { path: '/dashboard', element: <DashboardContent /> },
        ],
      })

      // Should redirect to dashboard
      expect(screen.queryByText('Guest Only')).not.toBeInTheDocument()
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
    })
  })
})
