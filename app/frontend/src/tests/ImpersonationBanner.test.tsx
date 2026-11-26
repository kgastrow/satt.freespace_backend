/**
 * ImpersonationBanner Component Tests
 *
 * Tests the ImpersonationBanner component rendering and behavior
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server, API_BASE } from '@/test/server'
import { render, createTestStore, type TestStore } from '@/test/utils'
import { ImpersonationBanner } from '@/components/ImpersonationBanner'
import { tokens } from '@/test/fixtures'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

describe('ImpersonationBanner', () => {
  let store: TestStore

  beforeEach(() => {
    mockNavigate.mockClear()
    sessionStorage.clear()
    localStorage.clear()
  })

  describe('when NOT impersonating', () => {
    beforeEach(() => {
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
    })

    it('does not render when not impersonating', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      expect(container.firstChild).toBeNull()
      expect(screen.queryByText('impersonation.banner.viewing')).not.toBeInTheDocument()
    })
  })

  describe('when impersonating', () => {
    beforeEach(() => {
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

      sessionStorage.setItem('access_token', 'impersonation-token')
      sessionStorage.setItem('original_token', tokens.validAccessToken)
    })

    it('renders banner with target user information', () => {
      render(<ImpersonationBanner />, { store })

      expect(screen.getByText('impersonation.banner.viewing')).toBeInTheDocument()
      expect(screen.getByText(/Target User/i)).toBeInTheDocument()
      expect(screen.getByText(/user@example.com/i)).toBeInTheDocument()
    })

    it('has distinctive warning styling', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.bg-yellow-500')
      expect(banner).toBeInTheDocument()
      expect(banner).toHaveClass('fixed', 'top-0', 'z-50')
    })

    it('displays end impersonation button', () => {
      render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      expect(endButton).toBeInTheDocument()
      expect(endButton).not.toBeDisabled()
    })

    it('ends impersonation and redirects on button click', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, () => {
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            message: 'Impersonation ended successfully',
          })
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard')
      })
    })

    it('shows loading state while ending impersonation', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, async () => {
          await new Promise((resolve) => setTimeout(resolve, 100))
          return HttpResponse.json({
            access_token: tokens.validAccessToken,
            message: 'Impersonation ended successfully',
          })
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      expect(screen.getByRole('button', { name: 'impersonation.banner.ending' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'impersonation.banner.ending' })).toBeDisabled()
    })

    it('handles error when ending impersonation fails', async () => {
      server.use(
        http.post(`${API_BASE}/admin/impersonate/end`, () => {
          return HttpResponse.json(
            { detail: 'Failed to end impersonation' },
            { status: 500 }
          )
        })
      )

      const { user } = render(<ImpersonationBanner />, { store })

      const endButton = screen.getByRole('button', { name: 'impersonation.banner.endButton' })
      await user.click(endButton)

      await waitFor(() => {
        expect(mockNavigate).not.toHaveBeenCalled()
      })
    })
  })

  describe('when impersonating but user is not loaded', () => {
    beforeEach(() => {
      // Edge case: impersonation state is true but auth user is not yet loaded
      // (targetUser is derived from auth.user when impersonating)
      store = createTestStore({
        auth: {
          user: null,
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
        impersonation: {
          isImpersonating: true,
          originalUser: null,
          targetUser: null,
          sessionId: 'session-123',
          sessionStartedAt: '2024-01-01T00:00:00Z',
          originalToken: null,
          originalRefreshToken: null,
        },
      })
    })

    it('does not render when targetUser is missing', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      expect(container.firstChild).toBeNull()
    })
  })

  describe('banner positioning and styling', () => {
    beforeEach(() => {
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

    it('is fixed at top of viewport', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.fixed.top-0')
      expect(banner).toBeInTheDocument()
      expect(banner).toHaveClass('left-0', 'right-0')
    })

    it('has high z-index for visibility', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.z-50')
      expect(banner).toBeInTheDocument()
    })

    it('uses warning color scheme', () => {
      const { container } = render(<ImpersonationBanner />, { store })

      const banner = container.querySelector('.bg-yellow-500')
      expect(banner).toBeInTheDocument()
      expect(banner).toHaveClass('text-yellow-950')
      expect(banner).toHaveClass('border-yellow-600')
    })
  })
})
