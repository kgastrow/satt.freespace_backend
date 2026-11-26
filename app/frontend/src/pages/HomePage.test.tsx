import { describe, it, expect } from 'vitest'
import { render, screen } from '@/test/utils'
import { HomePage } from './HomePage'

describe('HomePage', () => {
  it('renders welcome message when authenticated', () => {
    render(<HomePage />, {
      preloadedState: {
        auth: {
          user: {
            id: '1',
            email: 'test@test.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: '1',
            is_admin: false,
          },
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
      },
    })
    expect(screen.getByText('home.welcome')).toBeInTheDocument()
  })

  it('shows user info when authenticated', () => {
    render(<HomePage />, {
      preloadedState: {
        auth: {
          user: {
            id: '1',
            email: 'test@test.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: '1',
            is_admin: false,
          },
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
      },
    })
    expect(screen.getByText('Test User')).toBeInTheDocument()
    expect(screen.getByText('test@test.com')).toBeInTheDocument()
  })

  it('shows sign out button when authenticated', () => {
    render(<HomePage />, {
      preloadedState: {
        auth: {
          user: {
            id: '1',
            email: 'test@test.com',
            first_name: 'Test',
            last_name: 'User',
            organization_id: '1',
            is_admin: false,
          },
          token: 'test-token',
          isAuthenticated: true,
          isLoading: false,
          sso: { isLoading: false, error: null, selectedProvider: null },
          twoFactor: { required: false, token: null },
          twoFactorSetupRequired: false,
          enforcementActive: false,
        },
      },
    })
    expect(screen.getByRole('button', { name: /navigation.signOut/i })).toBeInTheDocument()
  })
})
