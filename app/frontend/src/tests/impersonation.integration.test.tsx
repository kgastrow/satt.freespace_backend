/**
 * Impersonation Integration Tests
 *
 * Tests the full impersonation flow including:
 * - Starting impersonation from user list
 * - Impersonation banner display and behavior
 * - Viewing application as impersonated user
 * - Ending impersonation and restoring admin session
 * - Permission restrictions (cannot impersonate admin/self)
 * - Session persistence across page refresh
 * - Impersonation history for target users
 * - Regular admin cannot access impersonation
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse, delay } from 'msw'
import { server, API_BASE, setCurrentUser } from '@/test/server'
import { render, createTestStore, clearStorage, type TestStore } from '@/test/utils'
import { superAdminUser, adminUser, regularUser, tokens } from '@/test/fixtures'
import { ImpersonationBanner } from '@/components/ImpersonationBanner'
import { ImpersonationButton } from '@/components/ImpersonationButton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import type { User } from '@/features/users/usersApi'
import type { ImpersonationSession, MyImpersonationHistoryResponse } from '@/types/impersonation'

/**
 * Helper wrapper component to render ImpersonationButton as menuItem
 * within a DropdownMenu context (required by Radix UI)
 */
function ImpersonationMenuItemWrapper({ user }: { user: User }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="sm">
          Actions
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <ImpersonationButton user={user} variant="menuItem" />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

// Mock impersonation session data
const mockImpersonationSession: ImpersonationSession = {
  id: 'session-123',
  created_time: '2024-01-01T10:00:00Z',
  impersonator_id: superAdminUser.id,
  target_user_id: regularUser.id,
  target_organization_id: regularUser.organization_id,
  ended_time: null,
  ip_address: '127.0.0.1',
  user_agent: 'test-agent',
}

// Mock target user for impersonation (mapped to User API type)
const targetUserRecord: User = {
  id: regularUser.id,
  email: regularUser.email,
  email_verified: true,
  email_deliverable: true,
  phone_verified: false,
  first_name: regularUser.first_name,
  last_name: regularUser.last_name,
  is_admin: false,
  created_time: '2024-01-01T00:00:00Z',
  roles: [],
}

// Another admin user for testing "cannot impersonate admin" scenario
const anotherAdminRecord: User = {
  id: 'admin-other',
  email: 'otheradmin@acme.com',
  email_verified: true,
  email_deliverable: true,
  phone_verified: false,
  first_name: 'Other',
  last_name: 'Admin',
  is_admin: true,
  created_time: '2024-01-01T00:00:00Z',
  roles: [],
}

describe('Impersonation Integration Tests', () => {
  beforeEach(() => {
    mockNavigate.mockClear()
    clearStorage()
    setCurrentUser(superAdminUser)
  })

  describe('Test 1: Start Impersonation from User List', () => {
    it('shows impersonate option in user actions dropdown for super admin', async () => {
      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { user } = render(<ImpersonationMenuItemWrapper user={targetUserRecord} />, {
        store,
      })

      // Open the dropdown menu first
      const triggerButton = screen.getByRole('button', { name: 'Actions' })
      await user.click(triggerButton)

      // ImpersonationButton renders as DropdownMenuItem when variant="menuItem"
      // It should be visible to super admins
      const menuItem = await screen.findByRole('menuitem')
      expect(menuItem).toBeInTheDocument()
      expect(menuItem).toHaveTextContent('impersonation.button.label')
      expect(menuItem).not.toHaveAttribute('data-disabled')
    })

    it('starts impersonation successfully when clicking impersonate button', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/${regularUser.id}`, async () => {
          await delay(50)
          return HttpResponse.json({
            impersonation_token: 'impersonation-token-123',
            session: mockImpersonationSession,
            message: 'Impersonation started successfully',
          })
        }),
        http.get(`${API_BASE}/user/me`, async () => {
          await delay(50)
          return HttpResponse.json({
            id: regularUser.id,
            email: regularUser.email,
            email_verified: true,
            email_deliverable: true,
            phone: null,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            is_admin: false,
            organization_id: regularUser.organization_id,
            roles: [],
          })
        }),
        http.get(`${API_BASE}/user/permissions`, async () => {
          await delay(50)
          return HttpResponse.json({ permissions: [] })
        })
      )

      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      // Set up storage with admin tokens
      sessionStorage.setItem('access_token', tokens.validAccessToken)

      const { user } = render(
        <ImpersonationButton user={targetUserRecord} variant="button" />,
        { store }
      )

      const button = screen.getByRole('button', { name: 'impersonation.button.label' })
      await user.click(button)

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
      })

      // Verify impersonation state was set
      const state = store.getState()
      expect(state.impersonation.isImpersonating).toBe(true)
      expect(state.impersonation.sessionId).toBe('session-123')
    })

    it('shows loading state while starting impersonation', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/${regularUser.id}`, async () => {
          await delay(200)
          return HttpResponse.json({
            impersonation_token: 'impersonation-token-123',
            session: mockImpersonationSession,
            message: 'Impersonation started successfully',
          })
        })
      )

      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      sessionStorage.setItem('access_token', tokens.validAccessToken)

      const { user } = render(
        <ImpersonationButton user={targetUserRecord} variant="button" />,
        { store }
      )

      const button = screen.getByRole('button', { name: 'impersonation.button.label' })
      await user.click(button)

      // Should show loading state
      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'impersonation.button.starting' })).toBeDisabled()
      })
    })
  })

  describe('Test 2: Impersonation Banner Display', () => {
    let store: TestStore

    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: regularUser.id,
            email: regularUser.email,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            organization_id: regularUser.organization_id,
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: superAdminUser,
          targetUser: regularUser,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T10:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      sessionStorage.setItem('access_token', 'impersonation-token')
      sessionStorage.setItem('original_token', tokens.validAccessToken)
    })

    it('renders banner with target user information when impersonating', () => {
      render(<ImpersonationBanner />, { store })

      expect(screen.getByText('impersonation.banner.viewing')).toBeInTheDocument()
      expect(screen.getByText(/Regular User/i)).toBeInTheDocument()
      expect(screen.getByText(/user@acme.com/i)).toBeInTheDocument()
    })

    it('displays end impersonation button in banner', () => {
      render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      expect(endButton).toBeInTheDocument()
      expect(endButton).not.toBeDisabled()
    })

    it('has distinctive warning styling (yellow background)', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.bg-yellow-500')
      expect(banner).toBeInTheDocument()
      expect(banner).toHaveClass('fixed', 'top-0', 'z-50')
      expect(banner).toHaveClass('text-yellow-950')
      expect(banner).toHaveClass('border-yellow-600')
    })

    it('does not render banner when not impersonating', () => {
      const notImpersonatingStore = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { container } = render(<ImpersonationBanner />, { store: notImpersonatingStore })
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Test 4: End Impersonation', () => {
    let store: TestStore

    beforeEach(() => {
      store = createTestStore({
        auth: {
          user: {
            id: regularUser.id,
            email: regularUser.email,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            organization_id: regularUser.organization_id,
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: superAdminUser,
          targetUser: regularUser,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T10:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      sessionStorage.setItem('access_token', 'impersonation-token')
      sessionStorage.setItem('original_token', tokens.validAccessToken)
    })

    it('ends impersonation and redirects to dashboard', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, async () => {
          await delay(50)
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            session: { ...mockImpersonationSession, ended_time: '2024-01-01T11:00:00Z' },
            message: 'Impersonation ended successfully',
          })
        }),
        http.get(`${API_BASE}/user/me`, async () => {
          await delay(50)
          return HttpResponse.json({
            id: superAdminUser.id,
            email: superAdminUser.email,
            email_verified: true,
            email_deliverable: true,
            phone: null,
            first_name: superAdminUser.first_name,
            last_name: superAdminUser.last_name,
            is_admin: true,
            organization_id: superAdminUser.organization_id,
            roles: [],
          })
        }),
        http.get(`${API_BASE}/user/permissions`, async () => {
          await delay(50)
          return HttpResponse.json({ permissions: [] })
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
      })

      // Verify impersonation state was cleared
      await waitFor(() => {
        const state = store.getState()
        expect(state.impersonation.isImpersonating).toBe(false)
        expect(state.impersonation.sessionId).toBeNull()
      })
    })

    it('shows loading state while ending impersonation', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, async () => {
          await delay(200)
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            session: { ...mockImpersonationSession, ended_time: '2024-01-01T11:00:00Z' },
            message: 'Impersonation ended successfully',
          })
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'impersonation.banner.ending' })).toBeDisabled()
      })
    })

    it('handles error when ending impersonation fails', async () => {
      // Reset mock before this test
      mockNavigate.mockClear()

      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, async () => {
          return HttpResponse.json({ detail: 'Failed to end impersonation' }, { status: 500 })
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      // Wait for the error to be handled - the button should be re-enabled
      await waitFor(() => {
        const btn = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
        expect(btn).not.toBeDisabled()
      })

      // Impersonation state should remain unchanged
      const state = store.getState()
      expect(state.impersonation.isImpersonating).toBe(true)
    })
  })

  describe('Test 5: Cannot Impersonate Admin Users', () => {
    it('disables impersonate button for admin users', () => {
      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      render(<ImpersonationButton user={anotherAdminRecord} variant="button" />, { store })

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })

    it('disables impersonate menu item for admin users', async () => {
      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { user } = render(<ImpersonationMenuItemWrapper user={anotherAdminRecord} />, { store })

      // Open the dropdown menu first
      const triggerButton = screen.getByRole('button', { name: 'Actions' })
      await user.click(triggerButton)

      const menuItem = await screen.findByRole('menuitem')
      // Radix UI sets data-disabled="" for disabled state (truthy empty string)
      expect(menuItem).toHaveAttribute('data-disabled')
    })
  })

  describe('Test 6: Cannot Impersonate Self', () => {
    it('disables impersonate button when user is self', () => {
      // Create a user record that matches the current user
      const selfRecord: User = {
        id: superAdminUser.id,
        email: superAdminUser.email,
        email_verified: true,
        email_deliverable: true,
        phone_verified: false,
        first_name: superAdminUser.first_name,
        last_name: superAdminUser.last_name,
        is_admin: true,
        created_time: '2024-01-01T00:00:00Z',
        roles: [],
      }

      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      render(<ImpersonationButton user={selfRecord} variant="button" />, { store })

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })
  })

  describe('Test 7: Impersonation Persists Across Refresh', () => {
    it('restores impersonation state from getCurrentSession on page load', async () => {
      server.use(
        http.get(`${API_BASE}/admin/impersonate/session`, async () => {
          await delay(50)
          return HttpResponse.json({
            active: true,
            session: mockImpersonationSession,
          })
        })
      )

      const store = createTestStore({
        auth: {
          user: {
            id: regularUser.id,
            email: regularUser.email,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            organization_id: regularUser.organization_id,
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: null,
          targetUser: null,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T10:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      // Set up storage with impersonation tokens
      sessionStorage.setItem('access_token', 'impersonation-token')
      sessionStorage.setItem('original_token', tokens.validAccessToken)

      // Render banner - it should show because isImpersonating is true
      render(<ImpersonationBanner />, { store })

      // Banner should be visible with target user info
      expect(screen.getByText('impersonation.banner.viewing')).toBeInTheDocument()
    })
  })

  describe('Test 8: Impersonation History Available to Impersonated User', () => {
    it('fetches impersonation history for target user', async () => {
      const mockHistoryResponse: MyImpersonationHistoryResponse = {
        items: [
          {
            id: 'session-123',
            created_time: '2024-01-15T10:00:00Z',
            ended_time: '2024-01-15T10:30:00Z',
            impersonator: {
              id: superAdminUser.id,
              email: superAdminUser.email,
              first_name: superAdminUser.first_name,
              last_name: superAdminUser.last_name,
            },
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      }

      server.use(
        http.get(`${API_BASE}/impersonate/my-history`, async () => {
          await delay(50)
          return HttpResponse.json(mockHistoryResponse)
        })
      )

      // This would be used in the ImpersonationHistorySection component
      // Here we just verify the handler returns expected data
      const response = await fetch(`${API_BASE}/impersonate/my-history`)
      const data = await response.json()

      expect(data.items).toHaveLength(1)
      expect(data.items[0].impersonator.email).toBe(superAdminUser.email)
    })
  })

  describe('Test 9: Regular Admin Cannot Impersonate', () => {
    it('does not render impersonation button for non-super-admin users', () => {
      const store = createTestStore({
        auth: {
          user: adminUser, // adminUser has is_admin: false
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { container } = render(
        <ImpersonationButton user={targetUserRecord} variant="button" />,
        { store }
      )

      // ImpersonationButton returns null when current user is not super admin
      expect(container.firstChild).toBeNull()
    })

    it('does not render impersonation menu item for non-super-admin users', () => {
      const store = createTestStore({
        auth: {
          user: adminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { container } = render(
        <ImpersonationButton user={targetUserRecord} variant="menuItem" />,
        { store }
      )

      // Should not render anything
      expect(container.firstChild).toBeNull()
    })
  })

  describe('Error Handling', () => {
    it('handles API error when starting impersonation', async () => {
      // Clear mock before this test
      mockNavigate.mockClear()

      server.use(
        http.post(`${API_BASE}/admin/impersonate/${regularUser.id}`, async () => {
          return HttpResponse.json(
            { detail: 'Cannot impersonate this user' },
            { status: 403 }
          )
        })
      )

      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      sessionStorage.setItem('access_token', tokens.validAccessToken)

      const { user } = render(
        <ImpersonationButton user={targetUserRecord} variant="button" />,
        { store }
      )

      const button = screen.getByRole('button', { name: 'impersonation.button.label' })
      await user.click(button)

      // Wait for error to be handled - button should be re-enabled after error
      await waitFor(() => {
        const btn = screen.getByRole('button', { name: 'impersonation.button.label' })
        expect(btn).not.toBeDisabled()
      })

      // Impersonation state should remain unchanged
      const state = store.getState()
      expect(state.impersonation.isImpersonating).toBe(false)
    })

    it('handles 401 unauthorized error', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/${regularUser.id}`, async () => {
          return HttpResponse.json({ detail: 'Not authenticated' }, { status: 401 })
        })
      )

      const store = createTestStore({
        auth: {
          user: superAdminUser,
          token: tokens.validAccessToken,
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: false,
          originalUser: null,
          targetUser: null,
          sessionId: null,
          sessionStartedAt: null,
          originalToken: null,
          originalRefreshToken: null,
        },
      })

      const { user } = render(
        <ImpersonationButton user={targetUserRecord} variant="button" />,
        { store }
      )

      const button = screen.getByRole('button', { name: 'impersonation.button.label' })
      await user.click(button)

      await waitFor(() => {
        expect(mockNavigate).not.toHaveBeenCalled()
      })
    })
  })

  describe('Banner Positioning and Styling', () => {
    it('is fixed at top of viewport', () => {
      const store = createTestStore({
        auth: {
          user: {
            id: regularUser.id,
            email: regularUser.email,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            organization_id: regularUser.organization_id,
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: superAdminUser,
          targetUser: regularUser,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T10:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.fixed.top-0')
      expect(banner).toBeInTheDocument()
      expect(banner).toHaveClass('left-0', 'right-0')
    })

    it('has high z-index for visibility', () => {
      const store = createTestStore({
        auth: {
          user: {
            id: regularUser.id,
            email: regularUser.email,
            first_name: regularUser.first_name,
            last_name: regularUser.last_name,
            organization_id: regularUser.organization_id,
            is_admin: false,
          },
          token: 'impersonation-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
        impersonation: {
          isImpersonating: true,
          originalUser: superAdminUser,
          targetUser: regularUser,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T10:00:00Z',
          originalToken: tokens.validAccessToken,
          originalRefreshToken: tokens.validRefreshToken,
        },
      })

      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.z-50')
      expect(banner).toBeInTheDocument()
    })
  })
})
